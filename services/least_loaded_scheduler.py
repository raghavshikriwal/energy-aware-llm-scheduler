"""Least-loaded baseline scheduler for LLM inference requests on cloud GPUs.

Unlike round-robin (which ignores load entirely), this assigns each request
to whichever GPU currently has the *least* accumulated token load. It is a
realistic, non-naive baseline — real-world load balancers commonly use this
exact strategy — and it deliberately has nothing to do with energy or
efficiency, only raw load balance.

Beating round-robin alone is a weak claim, since round-robin is a strawman.
Beating least-loaded too is a much stronger one: it shows the energy-aware
scheduler isn't just "better than doing nothing," it's better than a
sensible load-balancing baseline that engineers would actually reach for.
"""

from __future__ import annotations

from services.round_robin_scheduler import GPUNode, make_gpus


def least_loaded_schedule(
    requests: list[dict],
    num_gpus: int = 4,
    efficiency_factors: list[float] | None = None,
    compute_capabilities: list[float] | None = None,
) -> list[GPUNode]:
    """Assign each request to whichever GPU currently has the least load.

    Ties are broken by GPU id (lowest first) for determinism.
    """
    gpus = make_gpus(num_gpus, efficiency_factors, compute_capabilities)

    for request in requests:
        best_gpu = min(gpus, key=lambda gpu: (gpu.current_load, gpu.gpu_id))
        best_gpu.assign(request)

    return gpus


if __name__ == "__main__":
    from services.round_robin_scheduler import load_trace, summarize

    gpus = least_loaded_schedule(load_trace(), num_gpus=4)
    summarize(gpus, title="Least-Loaded Scheduling Summary")