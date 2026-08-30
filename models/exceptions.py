"""Custom exception types and a shared Flask error handler.

Routes raise these instead of returning ad-hoc (jsonify(...), status_code)
tuples inline, so every error response has the same JSON shape
({"error": "...", "code": "..."}) regardless of which route or which
validation layer (Pydantic vs. application logic) produced it.
"""

from __future__ import annotations

from flask import Flask, jsonify


class AppError(Exception):
    """Base class for application errors that should become a JSON response.

    `status_code` controls the HTTP response code; `code` is a short,
    machine-readable string (stable across message wording changes) that
    API consumers can branch on instead of parsing the human-readable text.
    """

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidGPUConfigError(AppError):
    """Raised when the caller-supplied GPU fleet configuration is invalid."""

    status_code = 400
    code = "invalid_gpu_config"


class TraceNotFoundError(AppError):
    """Raised when the synthetic request trace file is missing on disk."""

    status_code = 404
    code = "trace_not_found"


def register_error_handlers(app: Flask) -> None:
    """Attach a single handler that converts any AppError into a JSON body.

    Call this once from app.py at startup. Keeping it here (rather than
    scattering @app.errorhandler calls across route files) means adding a
    new AppError subclass automatically gets consistent handling with zero
    extra wiring.
    """

    @app.errorhandler(AppError)
    def _handle_app_error(err: AppError):
        return jsonify({"error": err.message, "code": err.code}), err.status_code