"""ASGI entrypoint for uvicorn.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 9380 --reload

Or using the factory directly (no module-level side-effects):
    uvicorn main:create_app --factory --host 0.0.0.0 --port 9380 --reload
"""
import os

from omniai.observability.logging_config import configure_logging

# Configure structured logging before anything else imports `logging`.
configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    fmt=os.getenv("LOG_FORMAT", "json"),
    third_party_level=os.getenv("LOG_THIRD_PARTY_LEVEL", "WARNING"),
)

from omniai.interfaces.http.app import create_app  # noqa: E402

app = create_app()
