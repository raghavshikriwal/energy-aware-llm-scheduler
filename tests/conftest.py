"""Shared pytest fixtures for the scheduler and API test suites."""

from __future__ import annotations

import pytest

from app import app as flask_app


@pytest.fixture
def app():
    """A Flask app configured for testing (propagates exceptions, etc.)."""
    flask_app.config.update(TESTING=True)
    yield flask_app


@pytest.fixture
def client(app):
    """A Flask test client — hits the app in-process, no live server needed.

    This is what test_api.py should have been from the start: the old
    version at the repo root required `flask run` in another terminal and
    made real HTTP calls, so it never ran in CI and nobody could tell if it
    still passed.
    """
    return app.test_client()


@pytest.fixture
def sample_requests():
    """A small, hand-built request trace — deliberately not sample_trace.json.

    Using a fixed, tiny trace (rather than the real 100-request file) makes
    test assertions easy to reason about by hand and keeps tests independent
    of that file's contents ever changing.
    """
    return [
        {"request_id": "r0", "input_tokens": 100, "output_tokens": 50},
        {"request_id": "r1", "input_tokens": 200, "output_tokens": 100},
        {"request_id": "r2", "input_tokens": 50, "output_tokens": 25},
        {"request_id": "r3", "input_tokens": 300, "output_tokens": 150},
    ]