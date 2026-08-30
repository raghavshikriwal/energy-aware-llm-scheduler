"""Unit tests for the three scheduling strategies.

Covers: empty input, single-GPU, uniform-fleet (no scheduler should be able
to beat any other), and the real heterogeneous-fleet behavior each
scheduler is supposed to produce.
"""

from __future__ import annotations

import pytest

from services.energy_aware_scheduler import energy_aware_schedule
from services.least_loaded_scheduler import least_loaded_schedule
from services.round_robin_scheduler import GPUNode, round_robin_schedule


# --- Empty / trivial input --------------------------------------------------

@pytest.mark.parametrize(
    "schedule_fn",
    [round_robin_schedule, least_loaded_schedule, energy_aware_schedule],
)
def test_empty_trace_returns_idle_gpus(schedule_fn):
    """No requests in, every GPU should come back at zero load and zero energy."""
    gpus = schedule_fn([], num_gpus=4)

    assert len(gpus) == 4
    assert all(gpu.current_load == 0 for gpu in gpus)
    assert all(gpu.total_energy_wh == 0.0 for gpu in gpus)
    assert all(gpu.request_count == 0 for gpu in gpus)


@pytest.mark.parametrize(
    "schedule_fn",
    [round_robin_schedule, least_loaded_schedule, energy_aware_schedule],
)
def test_single_gpu_gets_everything(schedule_fn, sample_requests):
    """With only one GPU, every scheduler has no choice — all load lands there."""
    gpus = schedule_fn(sample_requests, num_gpus=1)

    assert len(gpus) == 1
    expected_load = sum(r["input_tokens"] + r["output_tokens"] for r in sample_requests)
    assert gpus[0].current_load == expected_load
    assert gpus[0].request_count == len(sample_requests)


# --- Round-robin -------------------------------------------------------------

def test_round_robin_ignores_load_and_efficiency(sample_requests):
    """Round-robin must assign strictly by request index % num_gpus,
    regardless of how much load or how efficient each GPU is."""
    gpus = round_robin_schedule(sample_requests, num_gpus=2)

    # r0, r2 -> gpu 0 ; r1, r3 -> gpu 1
    assert gpus[0].request_count == 2
    assert gpus[1].request_count == 2
    assert gpus[0].current_load == (100 + 50) + (50 + 25)
    assert gpus[1].current_load == (200 + 100) + (300 + 150)


def test_round_robin_uniform_fleet_balances_request_count_evenly(sample_requests):
    """Round-robin balances by request COUNT, not by token load — with a
    perfectly divisible request count it should distribute requests evenly
    across GPUs, even though per-GPU token load may differ depending on
    which requests happen to land where (e.g. repeating a fixed-size batch
    means the same GPU can always catch the biggest request in the batch)."""
    gpus = round_robin_schedule(
        sample_requests * 4,  # 16 requests, evenly divisible by 4 GPUs
        num_gpus=4,
        efficiency_factors=[1.0, 1.0, 1.0, 1.0],
        compute_capabilities=[1.0, 1.0, 1.0, 1.0],
    )
    counts = [gpu.request_count for gpu in gpus]
    assert max(counts) == min(counts) == 4


# --- Least-loaded ------------------------------------------------------------

def test_least_loaded_always_picks_minimum_load_gpu():
    """Each request should go to whichever GPU has the least load *right now*,
    which for identical-size requests means it stays perfectly balanced."""
    requests = [
        {"request_id": f"r{i}", "input_tokens": 100, "output_tokens": 0}
        for i in range(8)
    ]
    gpus = least_loaded_schedule(requests, num_gpus=4)

    loads = [gpu.current_load for gpu in gpus]
    assert max(loads) == min(loads) == 200  # 8 requests * 100 tokens / 4 GPUs


def test_least_loaded_breaks_ties_by_gpu_id():
    """All GPUs start at load 0 — the very first request is a tie across all
    of them, and the tie-break rule (lowest gpu_id first) must be deterministic."""
    gpus = least_loaded_schedule(
        [{"request_id": "r0", "input_tokens": 10, "output_tokens": 0}],
        num_gpus=4,
    )
    assert gpus[0].request_count == 1
    assert all(gpu.request_count == 0 for gpu in gpus[1:])


# --- Energy-aware ------------------------------------------------------------

def test_energy_aware_uniform_fleet_matches_least_loaded():
    """The whole premise of the project: with a uniform fleet (no efficiency
    or speed spread), the energy-aware scheduler has no gap to exploit and
    should behave identically to least-loaded — this is the "0% savings"
    point at the left edge of the heterogeneity sweep chart on the site."""
    requests = [
        {"request_id": f"r{i}", "input_tokens": 80, "output_tokens": 40}
        for i in range(12)
    ]
    uniform = [1.0, 1.0, 1.0, 1.0]

    ea_gpus = energy_aware_schedule(
        requests, num_gpus=4, efficiency_factors=uniform, compute_capabilities=uniform
    )
    ll_gpus = least_loaded_schedule(
        requests, num_gpus=4, efficiency_factors=uniform, compute_capabilities=uniform
    )

    ea_total = sum(g.total_energy_wh for g in ea_gpus)
    ll_total = sum(g.total_energy_wh for g in ll_gpus)
    assert ea_total == pytest.approx(ll_total, rel=1e-9)


def test_energy_aware_favors_efficient_gpu_on_heterogeneous_fleet(sample_requests):
    """With a real efficiency/speed spread, the energy-aware scheduler should
    route more load to the more efficient GPU than round-robin would."""
    efficiency_factors = [2.0, 0.5]  # GPU 0 = power-hungry, GPU 1 = efficient
    compute_capabilities = [1.0, 1.0]

    ea_gpus = energy_aware_schedule(
        sample_requests * 5,
        num_gpus=2,
        efficiency_factors=efficiency_factors,
        compute_capabilities=compute_capabilities,
    )

    # GPU 1 (efficient) should end up carrying at least as much load as
    # GPU 0 (power-hungry) — the scheduler shouldn't favor the expensive one.
    assert ea_gpus[1].current_load >= ea_gpus[0].current_load


def test_energy_aware_beats_or_matches_round_robin_on_heterogeneous_fleet(sample_requests):
    """The core claim of the project, as a regression test: on a heterogeneous
    fleet, total energy under energy-aware scheduling should never be worse
    than round-robin. If this ever fails, the headline "% saved" stat on the
    site would go negative."""
    trace = sample_requests * 10
    efficiency_factors = [0.5, 0.8, 1.2, 2.0]
    compute_capabilities = [0.5, 0.85, 1.5, 3.0]

    rr_gpus = round_robin_schedule(
        trace, num_gpus=4, efficiency_factors=efficiency_factors,
        compute_capabilities=compute_capabilities,
    )
    ea_gpus = energy_aware_schedule(
        trace, num_gpus=4, efficiency_factors=efficiency_factors,
        compute_capabilities=compute_capabilities,
    )

    rr_total = sum(g.total_energy_wh for g in rr_gpus)
    ea_total = sum(g.total_energy_wh for g in ea_gpus)
    assert ea_total <= rr_total


def test_gpu_node_total_energy_is_power_times_time():
    """Sanity-check the physical model directly: total_energy_wh must equal
    energy_watts * completion_time_hours, not some other combination."""
    gpu = GPUNode(gpu_id=0, efficiency_factor=1.5, compute_capability=2.0)
    gpu.assign({"request_id": "r0", "input_tokens": 500, "output_tokens": 500})

    assert gpu.total_energy_wh == pytest.approx(
        gpu.energy_watts * gpu.completion_time_hours, rel=1e-9
    )


def test_gpu_node_idle_gpu_has_zero_completion_time_and_energy():
    """An untouched GPU should report zero time and zero total energy, even
    though it still has nonzero *instantaneous* idle power draw."""
    gpu = GPUNode(gpu_id=0)
    assert gpu.completion_time_hours == 0.0
    assert gpu.total_energy_wh == 0.0
    assert gpu.energy_watts > 0  # idle draw is still nonzero