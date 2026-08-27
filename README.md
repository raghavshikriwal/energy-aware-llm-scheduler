# Energy-Aware Task Scheduling for LLM Inference on Cloud GPUs

A Cloud Computing course project comparing a naive round-robin scheduler against a smarter energy-aware scheduler for routing LLM inference requests across a simulated, heterogeneous GPU fleet.

**Live demo:** _[Render link — pending deployment]_

---

## Problem

Cloud data centers running LLM inference workloads face a resource-scheduling problem: which GPU should handle each incoming request? A naive approach (round-robin) distributes requests evenly without regard to hardware differences. But real GPU fleets are heterogeneous — mixing older, power-hungry cards with newer, efficient ones — so blind distribution leaves real energy savings on the table.

This project simulates that scenario and measures whether a scheduler that's aware of each GPU's power and speed characteristics can meaningfully reduce total energy consumption versus round-robin, without sacrificing fairness or overloading any single GPU.

## Approach

Two schedulers are implemented and compared on the same synthetic request trace:

- **Round-Robin (baseline):** cycles requests across GPUs in strict order, ignoring load, power, or speed.
- **Energy-Aware:** for each request, selects the GPU that minimizes a cost function combining (a) projected *total* energy required to finish the workload and (b) a light penalty for pushing any GPU's load far above the fleet average, to prevent overloading the most efficient GPU into a bottleneck.

### GPU heterogeneity model

Each simulated GPU has two independent hardware traits:

| Trait | What it represents |
|---|---|
| `efficiency_factor` | Power drawn per unit of load (lower = more power-efficient) |
| `compute_capability` | Relative processing speed (higher = faster) |

Because power draw and processing time both matter, the scheduler evaluates GPUs on **total energy (Wh)** — power integrated over completion time — rather than instantaneous wattage alone. This distinction matters: a GPU with low instantaneous power draw but poor compute capability can end up consuming *more* total energy than a power-hungry-but-fast GPU, because it stays busy (and drawing power) for longer.

## Results

Energy-aware scheduling reduces total energy consumption by **~3% relative to round-robin** on the evaluated trace.

### Key finding: gains are naturally bounded by a convex cost curve

The energy-aware scheduler consistently routes more load toward the most efficient GPUs — but the improvement doesn't scale linearly with how much better those GPUs are. As any single GPU accumulates more load, both its power draw *and* its processing time increase, so its total energy cost grows faster than linearly (roughly quadratically). This discourages unlimited request concentration on even the most efficient hardware, and self-limits how much any scheduler — however smart — can gain by redistribution alone.

This was confirmed empirically: widening the efficiency/speed gap between the best and worst GPU by more than 2x only moved savings from ~2.4% to ~3.0%, well below what a naive linear-scaling assumption would predict. The modest, single-digit savings figure is a genuine result of this dynamic, not a limitation of the scheduling logic.

## Architecture


`energy_aware_scheduler.py` imports its `GPUNode` dataclass and shared utilities directly from `round_robin_scheduler.py` — there is no duplicated scheduling infrastructure between the two schedulers.

## Data persistence

Every comparison run is saved to a local SQLite database (`scheduler_runs.db`), so results aren't lost between requests. Past runs are retrievable via `GET /api/history`.

## Tech stack

- **Backend:** Python, Flask
- **Persistence:** SQLite
- **Frontend:** HTML, CSS, vanilla JavaScript, Chart.js (served locally)
- **Visualization:** Canvas-based particle animation, scroll-reveal via `IntersectionObserver`

## Running locally

```bash
# 1. Activate the virtual environment
.\venv\Scripts\Activate.ps1        # Windows PowerShell

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate a sample trace (if not already present)
python -m utils.trace_generator

# 4. Run the app
python app.py
```

Then open `http://127.0.0.1:5000`.

## API

| Endpoint | Description |
|---|---|
| `GET /api/compare` | Runs both schedulers on the current trace, returns per-GPU breakdown and savings %, and persists the run |
| `GET /api/history` | Returns the 20 most recent saved comparison runs |

## What this project deliberately does not include

- No real GPU cluster or live LLM deployment — synthetic/simulated traces only, by design
- No reinforcement-learning-based scheduler — heuristic-based, chosen deliberately for scope and interpretability

## Author

Raghav Shikriwal — BTech IT, NSUT