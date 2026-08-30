"""Proxy endpoints for the Live Demo (/api/live/*).

This blueprint runs inside the main Render app, which has NO GPU. It only
ever forwards requests to the separate GPU Worker Server (live/worker.py)
over HTTPS and relays back what the worker actually measured.

If the worker is unreachable, slow, or errors, these routes report that
honestly (`"online": false`, `"error": "..."`) instead of ever inventing
telemetry or inference results. This is a deliberate, separate file from
routes/api.py so the existing simulator API is never touched by this work.
"""

from __future__ import annotations

import os

import requests
from flask import Blueprint, jsonify, request

from extensions import limiter

live_api = Blueprint("live_api", __name__, url_prefix="/api/live")

# Short timeouts: a slow/unreachable worker should fail fast so the UI can
# show "GPU server offline" quickly rather than hanging a request.
STATUS_TIMEOUT_SEC = 4
INFERENCE_TIMEOUT_SEC = 120


def _worker_url() -> str | None:
    return os.environ.get("LIVE_WORKER_URL")


def _worker_headers() -> dict:
    api_key = os.environ.get("LIVE_WORKER_API_KEY")
    return {"X-API-Key": api_key} if api_key else {}


def _offline_response(reason: str, status: int = 200):
    return jsonify({"online": False, "reason": reason}), status


@live_api.route("/status")
def status():
    base_url = _worker_url()
    if not base_url:
        return _offline_response("LIVE_WORKER_URL is not configured on the server.")

    try:
        resp = requests.get(
            f"{base_url}/health",
            headers=_worker_headers(),
            timeout=STATUS_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()
        data["online"] = True
        return jsonify(data)
    except requests.exceptions.RequestException:
        return _offline_response("GPU worker unreachable.")


@live_api.route("/gpus")
def gpus():
    base_url = _worker_url()
    if not base_url:
        return _offline_response("LIVE_WORKER_URL is not configured on the server.")

    try:
        resp = requests.get(
            f"{base_url}/gpus",
            headers=_worker_headers(),
            timeout=STATUS_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except requests.exceptions.RequestException:
        return _offline_response("GPU worker unreachable.")


@live_api.route("/inference", methods=["POST"])
@limiter.limit("6 per minute")
def inference():
    base_url = _worker_url()
    if not base_url:
        return jsonify({"error": "GPU server offline", "code": "worker_unconfigured"}), 503

    body = request.get_json(silent=True) or {}

    try:
        resp = requests.post(
            f"{base_url}/inference",
            json=body,
            headers=_worker_headers(),
            timeout=INFERENCE_TIMEOUT_SEC,
        )
    except requests.exceptions.Timeout:
        return jsonify({"error": "GPU worker timed out", "code": "worker_timeout"}), 504
    except requests.exceptions.RequestException:
        return jsonify({"error": "GPU server offline", "code": "worker_unreachable"}), 503

    # Relay the worker's real status code and body as-is (success or error)
    # rather than reinterpreting it — the worker is the source of truth.
    return jsonify(resp.json()), resp.status_code


@live_api.route("/benchmark", methods=["POST"])
@limiter.limit("10 per minute")
def benchmark():
    base_url = _worker_url()
    if not base_url:
        return jsonify({"error": "GPU server offline", "code": "worker_unconfigured"}), 503

    try:
        resp = requests.post(
            f"{base_url}/benchmark",
            headers=_worker_headers(),
            timeout=STATUS_TIMEOUT_SEC,
        )
    except requests.exceptions.RequestException:
        return jsonify({"error": "GPU server offline", "code": "worker_unreachable"}), 503

    return jsonify(resp.json()), resp.status_code