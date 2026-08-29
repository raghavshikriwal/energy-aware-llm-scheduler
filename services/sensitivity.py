"""Sensitivity analysis: how energy savings scale with fleet heterogeneity.

A single savings percentage for one fixed fleet is a weak result — it
invites the question "is that number cherry-picked?" This module answers
a stronger question instead: as the GPU fleet becomes more heterogeneous
(bigger spread between old/inefficient and new/efficient hardware), how
does the energy-aware scheduler's advantage over the baselines change?

We interpolate linearly between a *uniform* fleet (every GPU identical,
efficiency_factor == compute_capability == 1.0, where no scheduler can
possibly beat any other) and the configured fleet profile, then push a
bit beyond it to show the trend continuing. `t=0.0` is uniform hardware;
`t=1.0` is the configured fleet; `t=1.5` is a 50% more extreme spread.
"""

from __future__ import annotations

from services.energy_aware_scheduler import energy_aware_schedule
from services.least_loaded_scheduler import least_loaded_schedule
from services.round_robin_scheduler import (
    DEFAULT_COMPUTE_CAPABILITIES,
    DEFAULT_EFFICIENCY_FACTORS,
    round_robin_schedule,
)

# How far past the configured fleet's spread to push the sweep, to make the
# trend visible beyond just "0 to current".
DEFAULT_SWEEP_POINTS: list[float] = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

_MIN_FACTOR: float = 0.05  # floor so extrapolation (t>1) never hits zero/negative


def _interpolate(values: list[float], t: float) -> list[float]:
    """Blend `values` toward uniform (1.0) at t=0, exact `values` at t=1,
    and linearly extrapolate beyond `values` for t>1.

    Clamped to a small positive floor: efficiency_factor and
    compute_capability must stay > 0 (compute_capability appears in a
    denominator), and pushing the extrapolation far enough (e.g. a GPU
    whose base value is 0.5 at t=2.0) would otherwise cross zero.
    """
    return [max(_MIN_FACTOR, 1.0 + t * (v - 1.0)) for v in values]


def _total_energy_wh(gpus) -> float:
    return sum(gpu.total_energy_wh for gpu in gpus)


def run_sensitivity_sweep(
    requests: list[dict],
    num_gpus: int | None = None,
    base_efficiency_factors: list[float] | None = None,
    base_compute_capabilities: list[float] | None = None,
    sweep_points: list[float] | None = None,
) -> list[dict]:
    """Run round-robin, least-loaded, and energy-aware at each heterogeneity level.

    Returns a list of dicts, one per sweep point, each containing the
    savings % of energy-aware scheduling over both baselines at that level
    of fleet heterogeneity — this is the data behind the "savings vs
    heterogeneity" chart.
    """
    base_eff = base_efficiency_factors or DEFAULT_EFFICIENCY_FACTORS
    base_cap = base_compute_capabilities or DEFAULT_COMPUTE_CAPABILITIES
    n = num_gpus or len(base_eff)
    points = sweep_points or DEFAULT_SWEEP_POINTS

    results = []
    for t in points:
        eff = _interpolate(base_eff, t)
        cap = _interpolate(base_cap, t)

        rr_energy = _total_energy_wh(
            round_robin_schedule(requests, num_gpus=n, efficiency_factors=eff, compute_capabilities=cap)
        )
        ll_energy = _total_energy_wh(
            least_loaded_schedule(requests, num_gpus=n, efficiency_factors=eff, compute_capabilities=cap)
        )
        ea_energy = _total_energy_wh(
            energy_aware_schedule(requests, num_gpus=n, efficiency_factors=eff, compute_capabilities=cap)
        )

        savings_vs_rr = (rr_energy - ea_energy) / rr_energy * 100 if rr_energy else 0.0
        savings_vs_ll = (ll_energy - ea_energy) / ll_energy * 100 if ll_energy else 0.0

        results.append({
            "heterogeneity": t,
            "round_robin_wh": round(rr_energy, 4),
            "least_loaded_wh": round(ll_energy, 4),
            "energy_aware_wh": round(ea_energy, 4),
            "savings_vs_round_robin_pct": round(savings_vs_rr, 3),
            "savings_vs_least_loaded_pct": round(savings_vs_ll, 3),
        })

    return results