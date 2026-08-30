"""Shared Flask extension instances.

Kept separate from app.py so routes/api.py can import `limiter` to apply
per-route limits without creating a circular import (app.py imports the
`api` blueprint, so the blueprint can't import back from app.py).
"""

from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, default_limits=["60 per minute"])