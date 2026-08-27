"""Energy-aware scheduler for LLM inference requests on cloud GPUs.

Assigns each request to the GPU that minimizes the *marginal* energy cost
of adding that request — i.e. how much extra energy this GPU would burn
to handle this one request, given its current load, power profile, and
speed. This is pure greedy energy minimization: the most efficient GPUs
absorb the most load, even if that means uneven distribution across the
fleet.
"""

from __future__ import annotations

from services.round_robin_scheduler import (
    BASE_THROUGHPUT_TOKENS_PER_SEC,
    IDLE_POWER_WATTS,
    LOAD_NORMALIZATION_FACTOR,
    POWER_PER_UNIT_LOAD,
    SECONDS_PER_HOUR,
    GPUNode,
    load_trace,
    make_gpus,
    summarize,
)

# How strongly to penalize load imbalance relative to pure energy savings.
#
# 0.0 = pure greedy energy minimization (most efficient GPUs take the most
# load, even if that means overloading them relative to the rest of the
# fleet). This is the current setting — max energy savings, uneven load
# accepted as a tradeoff.
BALANCE_PENALTY_WEIGHT: float = 0.0


def _projected_total_energy_wh(gpu: GPUNode, added_load: int) -> float:
    """Total energy (Wh) this GPU would consume if `added_load` tokens were assigned to it.

    Accounts for both this GPU's power profile (efficiency_factor) and its
    speed (compute_capability) — a fast-but-power-hungry GPU can still win
    over a slow-but-efficient one if it finishes quickly enough.
    """
    projected_load = gpu.current_load + added_load
    power_watts = (
        IDLE_POWER_WATTS + POWER_PER_UNIT_LOAD * projected_load / LOAD_NORMALIZATION_FACTOR
    ) * gpu.efficiency_factor

    throughput = BASE_THROUGHPUT_TOKENS_PER_SEC * gpu.compute_capability
    completion_hours = (projected_load / throughput) / SECONDS_PER_HOUR

    return power_watts * completion_hours


def _cost(gpu: GPUNode, added_load: int, avg_load: float) -> float:
    """Assignment cost: marginal energy this request adds to this GPU.

    Computed as (total energy with the request) - (total energy without
    it), isolating the true incremental cost rather than comparing whole
    -workload totals, which grow quadratically with load and would
    otherwise falsely penalize GPUs that are already carrying work.

    `avg_load` is accepted for interface compatibility (and in case
    BALANCE_PENALTY_WEIGHT is ever raised above 0.0 again) but has no
    effect while the penalty weight is 0.0.
    """
    energy_with_request = _projected_total_energy_wh(gpu, added_load)
    energy_without_request = _projected_total_energy_wh(gpu, 0)
    marginal_energy_wh = energy_with_request - energy_without_request

    imbalance = max(0.0, (gpu.current_load + added_load) - avg_load)
    return marginal_energy_wh + BALANCE_PENALTY_WEIGHT * imbalance


def energy_aware_schedule(
    requests: list[dict],
    num_gpus: int = 4,
    efficiency_factors: list[float] | None = None,
    compute_capabilities: list[float] | None = None,
) -> list[GPUNode]:
    """Assign each request to the GPU with the lowest marginal energy cost."""
    gpus = make_gpus(num_gpus, efficiency_factors, compute_capabilities)

    for request in requests:
        added_load = request["input_tokens"] + request["output_tokens"]
        avg_load = sum(gpu.current_load for gpu in gpus) / len(gpus)
        best_gpu = min(gpus, key=lambda gpu: _cost(gpu, added_load, avg_load))
        best_gpu.assign(request)

    return gpus


if __name__ == "__main__":
    gpus = energy_aware_schedule(load_trace(), num_gpus=4)
    summarize(gpus, title="Energy-Aware Scheduling Summary")