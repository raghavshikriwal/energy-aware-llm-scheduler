"""Real NVIDIA GPU telemetry via NVML.

This module NEVER invents numbers. If NVML isn't installed, no NVIDIA
driver is present, or a specific counter isn't exposed by the card/driver,
the affected field comes back as `None` rather than a guessed value, and
`is_available()` reports the true state of the machine this process is
running on.

Import this only inside the GPU worker process (`live/worker.py`), which is
meant to run on a machine with an actual NVIDIA GPU. It must never be
imported by the main web app.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

try:
    import pynvml
    _NVML_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - depends on host environment
    pynvml = None
    _NVML_IMPORT_ERROR = exc

_lock = threading.Lock()
_initialized = False
_init_error: Optional[str] = None


@dataclass
class GPUReading:
    index: int
    name: str
    utilization_pct: Optional[float] = None
    memory_used_mb: Optional[float] = None
    memory_total_mb: Optional[float] = None
    temperature_c: Optional[float] = None
    power_draw_w: Optional[float] = None
    power_limit_w: Optional[float] = None
    sm_clock_mhz: Optional[float] = None
    mem_clock_mhz: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "utilization_pct": self.utilization_pct,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "temperature_c": self.temperature_c,
            "power_draw_w": self.power_draw_w,
            "power_limit_w": self.power_limit_w,
            "sm_clock_mhz": self.sm_clock_mhz,
            "mem_clock_mhz": self.mem_clock_mhz,
        }


def _ensure_init() -> bool:
    """Lazily initialize NVML once per process. Returns True on success."""
    global _initialized, _init_error

    if _initialized:
        return True

    with _lock:
        if _initialized:
            return True

        if pynvml is None:
            _init_error = f"pynvml not installed: {_NVML_IMPORT_ERROR}"
            return False

        try:
            pynvml.nvmlInit()
            _initialized = True
            _init_error = None
            return True
        except Exception as exc:  # pragma: no cover - depends on host
            _init_error = f"nvmlInit() failed: {exc}"
            return False


def is_available() -> bool:
    """True only if NVML initialized and at least one GPU is visible."""
    if not _ensure_init():
        return False
    try:
        return pynvml.nvmlDeviceGetCount() > 0
    except Exception:
        return False


def unavailable_reason() -> Optional[str]:
    """Human-readable reason telemetry is unavailable, or None if it is."""
    if is_available():
        return None
    return _init_error or "No NVIDIA GPU detected on this worker."


def _safe(fn, *args):
    """Call an NVML getter; return None instead of raising if unsupported."""
    try:
        return fn(*args)
    except Exception:
        return None


def read_gpu(index: int) -> Optional[GPUReading]:
    """Read one GPU's real telemetry. Returns None if it can't be read."""
    if not _ensure_init():
        return None

    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)
    except Exception:
        return None

    name = _safe(pynvml.nvmlDeviceGetName, handle)
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")

    util = _safe(pynvml.nvmlDeviceGetUtilizationRates, handle)
    mem = _safe(pynvml.nvmlDeviceGetMemoryInfo, handle)
    temp = _safe(pynvml.nvmlDeviceGetTemperature, handle, pynvml.NVML_TEMPERATURE_GPU)
    power = _safe(pynvml.nvmlDeviceGetPowerUsage, handle)  # milliwatts
    power_limit = _safe(pynvml.nvmlDeviceGetEnforcedPowerLimit, handle)  # mW
    sm_clock = _safe(pynvml.nvmlDeviceGetClockInfo, handle, pynvml.NVML_CLOCK_SM)
    mem_clock = _safe(pynvml.nvmlDeviceGetClockInfo, handle, pynvml.NVML_CLOCK_MEM)

    return GPUReading(
        index=index,
        name=name or f"GPU {index}",
        utilization_pct=float(util.gpu) if util is not None else None,
        memory_used_mb=(mem.used / (1024 ** 2)) if mem is not None else None,
        memory_total_mb=(mem.total / (1024 ** 2)) if mem is not None else None,
        temperature_c=float(temp) if temp is not None else None,
        power_draw_w=(power / 1000.0) if power is not None else None,
        power_limit_w=(power_limit / 1000.0) if power_limit is not None else None,
        sm_clock_mhz=float(sm_clock) if sm_clock is not None else None,
        mem_clock_mhz=float(mem_clock) if mem_clock is not None else None,
    )


def list_gpus() -> list[dict]:
    """Read real telemetry for every visible GPU. Empty list if none/offline."""
    if not _ensure_init():
        return []

    try:
        count = pynvml.nvmlDeviceGetCount()
    except Exception:
        return []

    readings = []
    for i in range(count):
        reading = read_gpu(i)
        if reading is not None:
            readings.append(reading.to_dict())
    return readings


def shutdown() -> None:
    """Release NVML. Call on worker process exit if you want a clean stop."""
    global _initialized
    if _initialized and pynvml is not None:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    _initialized = False