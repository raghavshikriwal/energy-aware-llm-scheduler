"""GPU Worker Server — runs on the machine with the actual NVIDIA GPU.

This is a SEPARATE process/deployment from the main Render app (Render
itself is not assumed to provide a GPU — see project plan section 6).
Run this on your local PC, a lab machine, or a rented GPU box, then point
the main app at it via LIVE_WORKER_URL.

Endpoints:
  GET  /health              -> {"online": true, "gpu_available": bool, "reason": str|null}
  GET  /gpus                -> real NVML telemetry for every visible GPU
  POST /benchmark           -> idle telemetry snapshot (no workload yet)
  POST /inference           -> {prompt, max_new_tokens?, strategy?} -> real
                                inference measurements, or a clear error if
                                inference isn't configured yet (Phase 5)

Safety (per project plan rule set):
  - Every route requires header `X-API-Key` matching LIVE_WORKER_API_KEY.
    If that env var is unset, the worker refuses to start in non-debug
    mode, so it can never accidentally sit open on the internet.
  - Rate limiting via Flask-Limiter.
  - Request timeouts / input bounds on prompt length and max_new_tokens.
  - No route ever executes arbitrary shell commands or file paths from
    the request body.
"""

from __future__ import annotations

import os
import sys

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from live import gpu_benchmark, gpu_monitor, live_scheduler
from live import inference as inference_module
from live.inference import run_inference

MAX_PROMPT_CHARS = 4000
MAX_NEW_TOKENS_CEILING = 512

app = Flask(__name__)
limiter = Limiter(get_remote_address, default_limits=["30 per minute"])
limiter.init_app(app)

API_KEY = os.environ.get("LIVE_WORKER_API_KEY")
DEBUG_MODE = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

if not API_KEY and not DEBUG_MODE:
    sys.exit(
        "LIVE_WORKER_API_KEY is not set. Refusing to start the GPU worker "
        "without an API key outside of debug mode (see project plan rule 7)."
    )


@app.before_request
def _require_api_key():
    if not API_KEY:
        return  # only reachable in debug mode, e.g. local dev without a key
    provided = request.headers.get("X-API-Key")
    if provided != API_KEY:
        return jsonify({"error": "invalid or missing API key", "code": "unauthorized"}), 401


@app.errorhandler(Exception)
def _handle_unexpected(exc):
    # Never leak stack traces / internals; never claim a fake result was real.
    app.logger.exception("Unhandled error in GPU worker")
    return jsonify({"error": "internal worker error", "code": "worker_error"}), 500


@app.route("/health")
def health():
    available = gpu_monitor.is_available()
    return jsonify({
        "online": True,
        "gpu_available": available,
        "reason": None if available else gpu_monitor.unavailable_reason(),
        "inference_backend": os.environ.get("LIVE_INFERENCE_BACKEND", "none"),
    })


@app.route("/gpus")
def gpus():
    return jsonify({"gpus": gpu_monitor.list_gpus()})


@app.route("/benchmark", methods=["POST"])
@limiter.limit("10 per minute")
def benchmark():
    """Idle telemetry snapshot — no synthetic workload is run here.

    Once Phase 5 wires up real inference, /inference is the endpoint that
    produces genuine load-bearing latency/power/energy numbers. This route
    exists so the frontend can show *current* real GPU state on demand
    without submitting an inference job.
    """
    return jsonify({"gpus": gpu_monitor.list_gpus()})


@app.route("/inference", methods=["POST"])
@limiter.limit("6 per minute")
def inference():
    body = request.get_json(silent=True) or {}

    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "prompt is required", "code": "invalid_input"}), 400
    if len(prompt) > MAX_PROMPT_CHARS:
        return jsonify({
            "error": f"prompt exceeds {MAX_PROMPT_CHARS} characters",
            "code": "invalid_input",
        }), 400

    max_new_tokens = body.get("max_new_tokens", 128)
    if not isinstance(max_new_tokens, int) or not (1 <= max_new_tokens <= MAX_NEW_TOKENS_CEILING):
        return jsonify({
            "error": f"max_new_tokens must be an int between 1 and {MAX_NEW_TOKENS_CEILING}",
            "code": "invalid_input",
        }), 400

    strategy = body.get("strategy", "energy_aware")
    if strategy not in live_scheduler.VALID_STRATEGIES:
        return jsonify({
            "error": f"strategy must be one of {live_scheduler.VALID_STRATEGIES}",
            "code": "invalid_input",
        }), 400

    if not inference_module.is_configured():
        return jsonify({
            "error": (
                "No inference backend is configured on this GPU worker yet. "
                "Set LIVE_INFERENCE_BACKEND and LIVE_MODEL_NAME (Phase 5)."
            ),
            "code": "inference_not_configured",
        }), 501

    available_gpus = gpu_monitor.list_gpus()
    if not available_gpus:
        return jsonify({
            "error": "no GPU currently visible to this worker",
            "code": "gpu_unavailable",
        }), 503

    try:
        selected = live_scheduler.choose_gpu(strategy, available_gpus)
    except live_scheduler.NoGPUAvailableError as exc:
        return jsonify({"error": str(exc), "code": "gpu_unavailable"}), 503

    def _do_inference():
        return run_inference(prompt, max_new_tokens=max_new_tokens)

    try:
        bench = gpu_benchmark.measure(_do_inference, gpu_index=selected["index"])
    except Exception as exc:  # pragma: no cover - safety net
        return jsonify({"error": str(exc), "code": "inference_failed"}), 500

    if bench.error is not None:
        return jsonify({"error": bench.error, "code": "inference_failed"}), 500

    result = bench.result  # InferenceResult
    throughput_tok_s = (
        result.output_tokens / bench.elapsed_sec if bench.elapsed_sec > 0 else None
    )
    energy_per_token_wh = (
        bench.energy_wh / result.output_tokens
        if bench.energy_wh is not None and result.output_tokens > 0
        else None
    )

    return jsonify({
        "selected_gpu": selected,
        "scheduler_strategy": strategy,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "text": result.text,
        "measurement": bench.to_dict(),
        "throughput_tokens_per_sec": (
            round(throughput_tok_s, 2) if throughput_tok_s is not None else None
        ),
        "energy_per_token_wh": (
            round(energy_per_token_wh, 8) if energy_per_token_wh is not None else None
        ),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8800))
    app.run(host="0.0.0.0", port=port, debug=DEBUG_MODE)