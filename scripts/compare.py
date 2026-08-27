"""Compare round-robin vs energy-aware scheduling on the same trace."""

from __future__ import annotations

from services.round_robin_scheduler import round_robin_schedule, load_trace, summarize
from services.energy_aware_scheduler import energy_aware_schedule


def compare(trace_path: str = "sample_trace.json", num_gpus: int = 4) -> None:
    requests = load_trace(trace_path)

    rr_gpus = round_robin_schedule(requests, num_gpus=num_gpus)
    ea_gpus = energy_aware_schedule(requests, num_gpus=num_gpus)

    summarize(rr_gpus, title="Round-Robin")
    summarize(ea_gpus, title="Energy-Aware")

    rr_total = sum(gpu.energy_watts for gpu in rr_gpus)
    ea_total = sum(gpu.energy_watts for gpu in ea_gpus)
    savings_pct = (rr_total - ea_total) / rr_total * 100

    print(f"\n--- Comparison ---")
    print(f"Round-Robin Total Energy: {rr_total:.2f}W")
    print(f"Energy-Aware Total Energy: {ea_total:.2f}W")
    print(f"Energy Savings: {savings_pct:.2f}%")


if __name__ == "__main__":
    compare()