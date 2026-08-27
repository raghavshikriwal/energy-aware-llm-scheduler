"""Round-robin baseline scheduler for LLM inference requests on cloud GPUs.

Assigns requests to GPUs in strict cyclic order, ignoring both current
load and per-GPU efficiency or speed. Serves as the naive baseline against
which the energy-aware scheduler (energy_aware_scheduler.py) is evaluated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# --- Power model constants ------------------------------------------------

IDLE_POWER_WATTS: float = 50.0
POWER_PER_UNIT_LOAD: float = 2.0
LOAD_NORMALIZATION_FACTOR: float = 100.0

# --- Throughput model constants --------------------------------------------

# Baseline tokens/sec a GPU with compute_capability == 1.0 processes.
# Used with each GPU's compute_capability to derive completion time, which
# in turn determines *total* energy consumed (power draw x time), not just
# instantaneous wattage.
BASE_THROUGHPUT_TOKENS_PER_SEC: float = 500.0

# Simulates a mixed-generation, heterogeneous GPU fleet spanning older,
# power-hungry hardware alongside modern, efficient cards. Each index below
# represents one "class" of GPU, pairing a power profile with a speed
# profile:
#
#   GPU class 0: old, power-hungry, slow      (worst energy-per-token)
#   GPU class 1: mid-tier, balanced
#   GPU class 2: modern, efficient, fast
#   GPU class 3: latest-gen, most efficient, fastest (best energy-per-token)
#
# < 1.0 efficiency_factor = more power-efficient than baseline, > 1.0 = less.
# compute_capability is a relative throughput multiplier on BASE_THROUGHPUT.
#
# These are deliberately spread apart (not scaled proportionally) so that
# energy-per-token differs meaningfully across the fleet — giving the
# energy-aware scheduler a real, non-trivial gap to optimize over.
DEFAULT_EFFICIENCY_FACTORS: list[float] = [0.5, 0.8, 1.2, 2.0]
DEFAULT_COMPUTE_CAPABILITIES: list[float] = [0.5, 0.85, 1.5, 3.0]

SECONDS_PER_HOUR: float = 3600.0


@dataclass
class GPUNode:
    """A simulated GPU that accumulates load and reports estimated power draw.

    Two independent hardware traits drive heterogeneity:
      - efficiency_factor: how much power this GPU draws per unit of load
      - compute_capability: how fast this GPU processes that load

    Together they determine *total* energy consumed to finish a workload,
    not just instantaneous power draw.
    """

    gpu_id: int
    current_load: int = 0
    assigned_requests: list[str] = field(default_factory=list)
    efficiency_factor: float = 1.0
    compute_capability: float = 1.0

    def assign(self, request: dict) -> None:
        self.current_load += request["input_tokens"] + request["output_tokens"]
        self.assigned_requests.append(request["request_id"])

    @property
    def energy_watts(self) -> float:
        """Instantaneous power draw (W), scaling with load and this GPU's efficiency."""
        base = IDLE_POWER_WATTS + POWER_PER_UNIT_LOAD * self.current_load / LOAD_NORMALIZATION_FACTOR
        return base * self.efficiency_factor

    @property
    def completion_time_hours(self) -> float:
        """Time to process this GPU's current load, given its compute capability."""
        if self.current_load == 0:
            return 0.0
        throughput = BASE_THROUGHPUT_TOKENS_PER_SEC * self.compute_capability
        seconds = self.current_load / throughput
        return seconds / SECONDS_PER_HOUR

    @property
    def total_energy_wh(self) -> float:
        """Total energy (Wh) consumed to finish this GPU's assigned workload.

        This is the physically meaningful metric: power draw (W) integrated
        over the time (h) actually spent processing. A GPU with low
        instantaneous wattage but poor compute_capability can end up
        consuming *more* total energy than a power-hungry but fast GPU,
        because it stays busy — and drawing power — for longer.
        """
        return self.energy_watts * self.completion_time_hours

    @property
    def request_count(self) -> int:
        return len(self.assigned_requests)


def make_gpus(
    num_gpus: int,
    efficiency_factors: list[float] | None = None,
    compute_capabilities: list[float] | None = None,
) -> list[GPUNode]:
    """Create `num_gpus` GPUNodes, cycling through the given hardware profiles."""
    efficiencies = efficiency_factors or DEFAULT_EFFICIENCY_FACTORS
    capabilities = compute_capabilities or DEFAULT_COMPUTE_CAPABILITIES
    return [
        GPUNode(
            gpu_id=i,
            efficiency_factor=efficiencies[i % len(efficiencies)],
            compute_capability=capabilities[i % len(capabilities)],
        )
        for i in range(num_gpus)
    ]


def round_robin_schedule(
    requests: list[dict],
    num_gpus: int = 4,
    efficiency_factors: list[float] | None = None,
    compute_capabilities: list[float] | None = None,
) -> list[GPUNode]:
    """Assign requests to GPUs in cyclic order, ignoring load, efficiency, and speed."""
    gpus = make_gpus(num_gpus, efficiency_factors, compute_capabilities)
    for i, request in enumerate(requests):
        gpus[i % num_gpus].assign(request)
    return gpus


def summarize(gpus: list[GPUNode], title: str = "Scheduling Summary") -> None:
    """Print a per-GPU and fleet-wide breakdown of load, power, time, and total energy."""
    total_energy_wh = sum(gpu.total_energy_wh for gpu in gpus)
    avg_load = sum(gpu.current_load for gpu in gpus) / len(gpus)

    print(f"\n--- {title} ---")
    for gpu in gpus:
        print(
            f"GPU {gpu.gpu_id} (eff {gpu.efficiency_factor}, speed {gpu.compute_capability}x): "
            f"{gpu.request_count} requests | Load: {gpu.current_load} | "
            f"Power: {gpu.energy_watts:.2f}W | Time: {gpu.completion_time_hours * SECONDS_PER_HOUR:.1f}s | "
            f"Total Energy: {gpu.total_energy_wh:.4f}Wh"
        )
    print(f"\nTotal Energy Consumed: {total_energy_wh:.4f}Wh")
    print(f"Average Load per GPU: {avg_load:.2f}")


def load_trace(path: str | Path = "sample_trace.json") -> list[dict]:
    """Load a synthetic request trace generated by utils/trace_generator.py."""
    trace_path = Path(path)
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {path}. Run trace_generator.py first.")
    return json.loads(trace_path.read_text())


if __name__ == "__main__":
    gpus = round_robin_schedule(load_trace(), num_gpus=4)
    summarize(gpus, title="Round-Robin Scheduling Summary")