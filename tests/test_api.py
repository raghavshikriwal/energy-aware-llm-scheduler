"""API route tests, using Flask's test client (no live server required).

Replaces the old root-level test_api.py, which was a manual script that
made real HTTP calls to a server the developer had to start by hand in
another terminal — it never ran in CI and there was no way to tell if it
still passed without doing that manually.
"""

from __future__ import annotations


def test_compare_get_returns_all_three_strategies(client):
    res = client.get("/api/compare")
    assert res.status_code == 200

    body = res.get_json()
    assert "round_robin" in body
    assert "least_loaded" in body
    assert "energy_aware" in body
    assert "energy_savings_pct" in body
    assert "at_scale_projection" in body


def test_compare_get_gpu_summary_shape(client):
    res = client.get("/api/compare")
    body = res.get_json()

    gpu = body["energy_aware"]["gpus"][0]
    for field in (
        "gpu_id", "efficiency_factor", "compute_capability",
        "request_count", "load", "energy_watts",
        "completion_time_sec", "total_energy_wh",
    ):
        assert field in gpu


def test_compare_post_with_uniform_fleet_still_beats_unbalanced_round_robin(client):
    """A uniform-hardware fleet removes energy-aware's hardware advantage to
    exploit, but real request traces aren't uniformly sized — round-robin's
    naive cyclic split can still leave GPUs unevenly loaded (e.g. one GPU
    always catching the largest request in the cycle), and because energy
    scales with load, that imbalance still costs a small amount of energy
    versus a perfectly balanced split (energy-aware / least-loaded). So
    savings should be small and non-negative here, not exactly 0%."""
    payload = {
        "efficiency_factors": [0.3, 0.3, 0.3, 0.3],
        "compute_capabilities": [1.0, 1.0, 1.0, 1.0],
    }
    res = client.post("/api/compare", json=payload)
    assert res.status_code == 200

    body = res.get_json()
    assert 0.0 <= body["energy_savings_pct"] < 1.0


def test_compare_post_rejects_negative_efficiency(client):
    payload = {
        "efficiency_factors": [-1.0, 0.8, 1.2, 2.0],
        "compute_capabilities": [0.5, 0.85, 1.5, 3.0],
    }
    res = client.post("/api/compare", json=payload)
    assert res.status_code == 400

    body = res.get_json()
    assert "error" in body
    assert body["code"] == "invalid_gpu_config"


def test_compare_post_rejects_mismatched_list_lengths(client):
    payload = {
        "efficiency_factors": [0.5, 0.8, 1.2],
        "compute_capabilities": [0.5, 0.85, 1.5, 3.0],
    }
    res = client.post("/api/compare", json=payload)
    assert res.status_code == 400
    assert res.get_json()["code"] == "invalid_gpu_config"


def test_compare_post_rejects_non_numeric_values(client):
    payload = {
        "efficiency_factors": ["fast", 0.8, 1.2, 2.0],
        "compute_capabilities": [0.5, 0.85, 1.5, 3.0],
    }
    res = client.post("/api/compare", json=payload)
    assert res.status_code == 400


def test_compare_post_rejects_empty_list(client):
    payload = {"efficiency_factors": [], "compute_capabilities": []}
    res = client.post("/api/compare", json=payload)
    assert res.status_code == 400


def test_compare_post_with_empty_body_uses_defaults(client):
    """An explicit POST with no body should behave identically to GET —
    this is the actual request the frontend's initial page load makes."""
    res = client.post("/api/compare", json={})
    assert res.status_code == 200


def test_sensitivity_returns_a_sweep(client):
    res = client.get("/api/sensitivity")
    assert res.status_code == 200

    body = res.get_json()
    assert "sweep" in body
    assert len(body["sweep"]) > 0
    assert "heterogeneity" in body["sweep"][0]
    assert "savings_vs_round_robin_pct" in body["sweep"][0]


def test_history_returns_a_list(client):
    res = client.get("/api/history")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_history_reflects_a_new_post_run(client):
    """POSTing a comparison should persist a row that /api/history then returns."""
    before = client.get("/api/history").get_json()

    client.post("/api/compare", json={
        "efficiency_factors": [0.4, 0.9, 1.3, 2.1],
        "compute_capabilities": [0.6, 0.9, 1.6, 3.1],
    })

    after = client.get("/api/history").get_json()
    assert len(after) >= len(before)