"""Measure real latency, power and energy around an actual piece of work.

`measure()` wraps a callable (e.g. a real inference call) and returns the
wall-clock time plus a power-sampling-derived energy estimate — computed
from real NVML power readings taken during execution, never a guessed or
hardcoded number. If NVML can't supply power on this GPU/driver, the energy
fields come back as `None` instead of being invented.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

from live import gpu_monitor

T = TypeVar("T")

# How often to sample power while the wrapped call is running.
_SAMPLE_INTERVAL_SEC = 0.05


@dataclass
class BenchmarkResult:
    elapsed_sec: float
    avg_power_w: Optional[float]
    sample_count: int
    energy_wh: Optional[float]
    result: object = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "elapsed_sec": round(self.elapsed_sec, 4),
            "avg_power_w": round(self.avg_power_w, 2) if self.avg_power_w is not None else None,
            "sample_count": self.sample_count,
            "energy_wh": round(self.energy_wh, 6) if self.energy_wh is not None else None,
            "error": self.error,
        }


class _PowerSampler:
    """Background thread that repeatedly reads real power draw for one GPU."""

    def __init__(self, gpu_index: int):
        self.gpu_index = gpu_index
        self._samples: list[float] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run(self) -> None:
        while not self._stop.is_set():
            reading = gpu_monitor.read_gpu(self.gpu_index)
            if reading is not None and reading.power_draw_w is not None:
                self._samples.append(reading.power_draw_w)
            self._stop.wait(_SAMPLE_INTERVAL_SEC)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> list[float]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        return self._samples


def measure(fn: Callable[[], T], gpu_index: int) -> BenchmarkResult:
    """Run `fn`, sampling real GPU power throughout. Never fabricates data.

    If power sampling yields no real samples (e.g. NVML power readout
    unsupported on this card), `avg_power_w` and `energy_wh` are None —
    elapsed time is still real and always reported.
    """
    sampler = _PowerSampler(gpu_index)
    sampler.start()

    start = time.perf_counter()
    error: Optional[str] = None
    result: object = None
    try:
        result = fn()
    except Exception as exc:
        error = str(exc)
    elapsed = time.perf_counter() - start

    samples = sampler.stop()

    avg_power = (sum(samples) / len(samples)) if samples else None
    energy_wh = (avg_power * (elapsed / 3600.0)) if avg_power is not None else None

    return BenchmarkResult(
        elapsed_sec=elapsed,
        avg_power_w=avg_power,
        sample_count=len(samples),
        energy_wh=energy_wh,
        result=result,
        error=error,
    )