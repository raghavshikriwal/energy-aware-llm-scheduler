"""Scheduling strategies for the Live Demo.

Unlike services/*_scheduler.py (which simulate a synthetic trace), these
functions choose among GPUs described by *real* telemetry dicts, as
produced by live.gpu_monitor.list_gpus(). If a needed field is missing
(None) for a GPU, that GPU is treated as the least attractive candidate
for strategies that depend on it, rather than assuming a default value.
"""

from __future__ import annotations

import itertools
from typing import Optional

VALID_STRATEGIES = ("round_robin", "least_loaded", "energy_aware")

_round_robin_counter = itertools.count()


class NoGPUAvailableError(RuntimeError):
    pass


def _round_robin(gpus: list[dict]) -> dict:
    n = next(_round_robin_counter) % len(gpus)
    return gpus[n]


def _least_loaded(gpus: list[dict]) -> dict:
    # Missing utilization reads as "unknown load" -> sort last, not as 0%.
    def key(g: dict):
        util = g.get("utilization_pct")
        return (util is None, util if util is not None else 0.0)

    return sorted(gpus, key=key)[0]


def _energy_aware(gpus: list[dict]) -> dict:
    """Pick the GPU with the lowest real marginal energy signal.

    Marginal energy proxy = current power draw scaled by (1 + utilization),
    so a GPU that is both drawing less power AND less busy right now is
    preferred. GPUs missing power or utilization data are ranked last
    rather than assumed cheap to run on.
    """

    def key(g: dict):
        power = g.get("power_draw_w")
        util = g.get("utilization_pct")
        missing = power is None or util is None
        score = (power or 0.0) * (1.0 + (util or 0.0) / 100.0)
        return (missing, score)

    return sorted(gpus, key=key)[0]


_STRATEGY_FUNCS = {
    "round_robin": _round_robin,
    "least_loaded": _least_loaded,
    "energy_aware": _energy_aware,
}


def choose_gpu(strategy: str, gpus: list[dict]) -> dict:
    """Select one GPU dict from `gpus` (real telemetry) using `strategy`."""
    if not gpus:
        raise NoGPUAvailableError("No GPUs are visible to the worker.")

    fn = _STRATEGY_FUNCS.get(strategy)
    if fn is None:
        raise ValueError(
            f"Unknown strategy '{strategy}'. Valid: {', '.join(VALID_STRATEGIES)}"
        )

    return fn(gpus)