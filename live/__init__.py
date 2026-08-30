"""Live Demo package: real GPU telemetry, real inference, real scheduling.

Two entrypoints live here:
  - worker.py runs standalone, ON the GPU machine (python -m live.worker).
  - The main Flask app (routes/live_api.py) only ever talks to the worker
    over HTTP; it never imports gpu_monitor/inference directly, since the
    Render app itself has no GPU.
"""