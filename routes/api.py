"""API routes exposing scheduler comparison results as JSON."""

from __future__ import annotations

from pydantic import ValidationError

from flask import Blueprint, jsonify, request

from models.database import get_recent_runs, save_comparison_run
from models.exceptions import InvalidGPUConfigError, TraceNotFoundError
from models.schemas import GPUFleetConfig
from services.energy_aware_scheduler import energy_aware_schedule
from services.least_loaded_scheduler import least_loaded_schedule
from services.round_robin_scheduler import (
    DEFAULT_COMPUTE_CAPABILITIES,
    DEFAULT_EFFICIENCY_FACTORS,
    load_trace,
    round_robin_schedule,
)
from services.sensitivity import run_sensitivity_sweep

api = Blueprint("api", __name__, url_prefix="/api")

# --- Illustrative cost/carbon conversion ------------------------------------
# These are rough, clearly-labeled reference figures (US average grid), used
# only to make an abstract Wh number tangible. They are NOT a claim about any
# specific data center's actual electricity contract or grid mix.
USD_PER_KWH: float = 0.12
KG_CO2_PER_KWH: float = 0.417

# How many times larger a real production fleet might be than this demo's
# 4-GPU / 100-request trace, purely for the "at scale" projection shown in
# the UI. Labeled explicitly as an extrapolation, not a measurement.
SCALE_PROJECTION_MULTIPLIER: float = 10_000


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
    Validation itself lives in models.schemas.GPUFleetConfig — this function
    just parses the body against that schema and translates a Pydantic
    ValidationError into our own InvalidGPUConfigError so every route
    returns errors in the same shape (see models/exceptions.py).

    Returns (efficiency_factors, compute_capabilities, num_gpus).
    """
    body = request.get_json(silent=True) or {}

    try:
        config = GPUFleetConfig.model_validate(body)
    except ValidationError as e:
        # Pydantic's default message is multi-line and implementation-y;
        # collapse it to one readable sentence per error for the API caller.
        first_error = e.errors()[0]
        field = ".".join(str(loc) for loc in first_error["loc"]) or "body"
        raise InvalidGPUConfigError(f"{field}: {first_error['msg']}") from e

    efficiency_factors = config.efficiency_factors or DEFAULT_EFFICIENCY_FACTORS
    compute_capabilities = config.compute_capabilities or DEFAULT_COMPUTE_CAPABILITIES

    if len(efficiency_factors) != len(compute_capabilities):
        raise InvalidGPUConfigError(
            "efficiency_factors and compute_capabilities must be the same length"
        )

    num_gpus = config.num_gpus or len(efficiency_factors)

    return efficiency_factors, compute_capabilities, num_gpus


@api.route("/compare", methods=["GET", "POST"])
def compare():
    try:
        requests_trace = load_trace()
    except FileNotFoundError as e:
        raise TraceNotFoundError(str(e)) from e

    efficiency_factors, compute_capabilities, num_gpus = _parse_custom_gpu_config()

    rr_gpus = round_robin_schedule(
        requests_trace,
        num_gpus=num_gpus,
        efficiency_factors=efficiency_factors,
        compute_capabilities=compute_capabilities,
    )
    ll_gpus = least_loaded_schedule(
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
    ll_power_total = sum(gpu.energy_watts for gpu in ll_gpus)
    ea_power_total = sum(gpu.energy_watts for gpu in ea_gpus)

    # Total energy to finish the workload — the physically meaningful metric
    rr_energy_total = sum(gpu.total_energy_wh for gpu in rr_gpus)
    ll_energy_total = sum(gpu.total_energy_wh for gpu in ll_gpus)
    ea_energy_total = sum(gpu.total_energy_wh for gpu in ea_gpus)

    savings_pct = (
        (rr_energy_total - ea_energy_total) / rr_energy_total * 100
        if rr_energy_total
        else 0.0
    )
    savings_vs_least_loaded_pct = (
        (ll_energy_total - ea_energy_total) / ll_energy_total * 100
        if ll_energy_total
        else 0.0
    )

    rr_gpu_summary = _gpu_summary(rr_gpus)
    ll_gpu_summary = _gpu_summary(ll_gpus)
    ea_gpu_summary = _gpu_summary(ea_gpus)

    # Illustrative cost/carbon framing at a hypothetical production scale.
    # Explicitly labeled as a linear extrapolation of this demo trace, not a
    # measurement of any real deployment.
    wh_saved_vs_rr = rr_energy_total - ea_energy_total
    projected_kwh_saved = (wh_saved_vs_rr * SCALE_PROJECTION_MULTIPLIER) / 1000
    projected_usd_saved = projected_kwh_saved * USD_PER_KWH
    projected_kg_co2_saved = projected_kwh_saved * KG_CO2_PER_KWH

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
        "least_loaded": {
            "gpus": ll_gpu_summary,
            "total_energy_watts": round(ll_power_total, 2),
            "total_energy_wh": round(ll_energy_total, 4),
        },
        "energy_aware": {
            "gpus": ea_gpu_summary,
            "total_energy_watts": round(ea_power_total, 2),
            "total_energy_wh": round(ea_energy_total, 4),
        },
        "energy_savings_pct": round(savings_pct, 2),
        "energy_savings_vs_least_loaded_pct": round(savings_vs_least_loaded_pct, 2),
        "at_scale_projection": {
            "note": (
                f"Illustrative only: linearly scales this trace's Wh savings "
                f"by {SCALE_PROJECTION_MULTIPLIER:,}x to approximate a "
                f"production-sized fleet. Not a measurement of any real "
                f"deployment."
            ),
            "multiplier": SCALE_PROJECTION_MULTIPLIER,
            "kwh_saved": round(projected_kwh_saved, 2),
            "usd_saved": round(projected_usd_saved, 2),
            "kg_co2_saved": round(projected_kg_co2_saved, 2),
        },
    })


@api.route("/sensitivity")
def sensitivity():
    """Sweep fleet heterogeneity and return savings % at each level.

    This is the data behind the "savings scale with heterogeneity" chart —
    the strongest evidence that the 3% headline number isn't a cherry-picked
    single point, but part of a consistent, explainable trend.
    """
    try:
        requests_trace = load_trace()
    except FileNotFoundError as e:
        raise TraceNotFoundError(str(e)) from e

    efficiency_factors, compute_capabilities, num_gpus = _parse_custom_gpu_config()

    results = run_sensitivity_sweep(
        requests_trace,
        num_gpus=num_gpus,
        base_efficiency_factors=efficiency_factors,
        base_compute_capabilities=compute_capabilities,
    )
    return jsonify({"sweep": results})


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