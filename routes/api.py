"""API routes exposing scheduler comparison results as JSON."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from models.database import get_recent_runs, save_comparison_run
from services.energy_aware_scheduler import energy_aware_schedule
from services.round_robin_scheduler import (
    DEFAULT_COMPUTE_CAPABILITIES,
    DEFAULT_EFFICIENCY_FACTORS,
    load_trace,
    round_robin_schedule,
)

api = Blueprint("api", __name__, url_prefix="/api")


def _gpu_summary(gpus) -> list[dict]:
    return [
        {
            "gpu_id": gpu.gpu_id,
            "efficiency_factor": gpu.efficiency_factor,
            "compute_capability": gpu.compute_capability,
            "request_count": gpu.request_count,
            "load": gpu.current_load,
            "energy_watts": round(gpu.energy_watts, 2),
            "completion_time_sec": round(gpu.completion_time_hours * 3600, 1),
            "total_energy_wh": round(gpu.total_energy_wh, 4),
        }
        for gpu in gpus
    ]


def _parse_custom_gpu_config():
    """Read optional custom GPU parameters from the POST JSON body.

    Falls back to the module defaults for anything not provided, so this
    endpoint keeps working exactly as before if the caller sends nothing.
    Returns (efficiency_factors, compute_capabilities, num_gpus).
    """
    body = request.get_json(silent=True) or {}

    efficiency_factors = body.get("efficiency_factors") or DEFAULT_EFFICIENCY_FACTORS
    compute_capabilities = body.get("compute_capabilities") or DEFAULT_COMPUTE_CAPABILITIES

    # Basic validation — reject obviously broken input rather than letting
    # it silently produce nonsense (e.g. divide-by-zero speed).
    if not isinstance(efficiency_factors, list) or not all(
        isinstance(x, (int, float)) and x > 0 for x in efficiency_factors
    ):
        raise ValueError("efficiency_factors must be a list of positive numbers")

    if not isinstance(compute_capabilities, list) or not all(
        isinstance(x, (int, float)) and x > 0 for x in compute_capabilities
    ):
        raise ValueError("compute_capabilities must be a list of positive numbers")

    if len(efficiency_factors) != len(compute_capabilities):
        raise ValueError("efficiency_factors and compute_capabilities must be the same length")

    num_gpus = body.get("num_gpus") or len(efficiency_factors)

    return efficiency_factors, compute_capabilities, num_gpus


@api.route("/compare", methods=["GET", "POST"])
def compare():
    try:
        requests_trace = load_trace()
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    try:
        efficiency_factors, compute_capabilities, num_gpus = _parse_custom_gpu_config()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    rr_gpus = round_robin_schedule(
        requests_trace,
        num_gpus=num_gpus,
        efficiency_factors=efficiency_factors,
        compute_capabilities=compute_capabilities,
    )
    ea_gpus = energy_aware_schedule(
        requests_trace,
        num_gpus=num_gpus,
        efficiency_factors=efficiency_factors,
        compute_capabilities=compute_capabilities,
    )

    # Instantaneous power snapshot (kept for the "current load" view)
    rr_power_total = sum(gpu.energy_watts for gpu in rr_gpus)
    ea_power_total = sum(gpu.energy_watts for gpu in ea_gpus)

    # Total energy to finish the workload — the physically meaningful metric
    rr_energy_total = sum(gpu.total_energy_wh for gpu in rr_gpus)
    ea_energy_total = sum(gpu.total_energy_wh for gpu in ea_gpus)

    savings_pct = (
        (rr_energy_total - ea_energy_total) / rr_energy_total * 100
        if rr_energy_total
        else 0.0
    )

    rr_gpu_summary = _gpu_summary(rr_gpus)
    ea_gpu_summary = _gpu_summary(ea_gpus)

    # Persist this run so it shows up in /api/history.
    # Only save on POST (an explicit user-triggered "Run Comparison"),
    # not on every GET page-load, to avoid flooding the DB with duplicate
    # rows from the dashboard's initial fetch.
    if request.method == "POST":
        save_comparison_run(
            energy_savings_pct=round(savings_pct, 2),
            round_robin_total_wh=round(rr_energy_total, 4),
            energy_aware_total_wh=round(ea_energy_total, 4),
            round_robin_gpus=rr_gpu_summary,
            energy_aware_gpus=ea_gpu_summary,
        )

    return jsonify({
        "round_robin": {
            "gpus": rr_gpu_summary,
            "total_energy_watts": round(rr_power_total, 2),
            "total_energy_wh": round(rr_energy_total, 4),
        },
        "energy_aware": {
            "gpus": ea_gpu_summary,
            "total_energy_watts": round(ea_power_total, 2),
            "total_energy_wh": round(ea_energy_total, 4),
        },
        "energy_savings_pct": round(savings_pct, 2),
    })


@api.route("/history")
def history():
    """Return the most recent stored comparison runs, newest first."""
    runs = get_recent_runs(limit=20)
    return jsonify([
        {
            "id": run.id,
            "created_at": run.created_at,
            "energy_savings_pct": run.energy_savings_pct,
            "round_robin_total_wh": run.round_robin_total_wh,
            "energy_aware_total_wh": run.energy_aware_total_wh,
        }
        for run in runs
    ])