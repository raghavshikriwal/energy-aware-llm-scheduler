# Live GPU Lab — Setup

Two separate processes, two separate machines:

1. **Main app** (unchanged Render deployment) — serves `/` (simulator) and
   the new `/live` page. Has no GPU. Only talks to the worker over HTTPS.
2. **GPU worker** (`live/worker.py`) — runs on a machine with a real
   NVIDIA GPU. Reads NVML telemetry, runs inference, measures results.

## 1. Run the GPU worker

On the machine with the GPU:

```bash
pip install -r requirements-live.txt

export LIVE_WORKER_API_KEY="pick-a-long-random-string"
export PORT=8800

python -m live.worker
```

Check it's alive: `curl http://localhost:8800/health` (needs the
`X-API-Key` header — this returns 401 without it).

To expose it to your Render app, either:
- put it behind a reverse proxy with TLS (e.g. Caddy/nginx) and a real
  domain/subdomain, or
- tunnel it (e.g. `cloudflared tunnel` or `ngrok`) for testing.

Either way, the URL Render talks to must be `https://...`, not a bare LAN
IP, unless you're testing locally with both processes on one machine.

## 2. Point the main app at the worker

On Render (or your `.env` locally), set:

```
LIVE_WORKER_URL=https://your-worker-domain-or-tunnel
LIVE_WORKER_API_KEY=same-string-as-above
```

If `LIVE_WORKER_URL` is unset, `/live` correctly shows "GPU SERVER
OFFLINE" — the simulator keeps working either way (rule 5 in the plan).

## 3. (Phase 5) Turn on real inference

On the **worker** machine only:

```bash
pip install torch transformers   # match torch to your CUDA version
export LIVE_INFERENCE_BACKEND=transformers
export LIVE_MODEL_NAME=Qwen/Qwen2.5-0.5B-Instruct   # pick something that fits your VRAM
```

Until these are set, `/api/live/inference` correctly returns a
`501 inference_not_configured` error instead of fabricating a result —
telemetry and GPU cards work fine without this step.

## What's new / changed

New:
- `live/` package (`gpu_monitor.py`, `gpu_benchmark.py`, `inference.py`,
  `live_scheduler.py`, `worker.py`)
- `routes/live_api.py` — proxy blueprint, kept separate from
  `routes/api.py` so the existing simulator API file is untouched
- `templates/live.html`, `static/live.js`, `static/live.css`
- `requirements-live.txt` (worker-only deps)

Modified:
- `app.py` — registers `live_api` blueprint, adds `/live` route
- `templates/dashboard.html` — one new "Live" nav link
- `requirements.txt` — added `requests` (main app needs it to call the
  worker)

Untouched (per the plan's "keep unchanged initially" list):
- `services/*.py`, `models/*.py`, `static/dashboard.js`,
  `static/simulation.js`, `static/chart.umd.min.js`,
  `tests/test_schedulers.py`, `routes/api.py`

## Safety notes already built in

- Worker refuses to start without `LIVE_WORKER_API_KEY` (outside debug mode)
- Every worker route requires `X-API-Key`
- Rate limiting on both the worker and the proxy blueprint
- Prompt length and `max_new_tokens` are bounded server-side
- Short timeouts on the proxy so an unreachable worker fails fast into
  "offline" instead of hanging
- No route executes shell commands or accepts file paths from the request