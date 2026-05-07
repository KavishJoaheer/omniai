"""Structured JSON logging for Omni-AI.

Call ``configure_logging()`` once at application startup (in main.py).
Every log record thereafter is emitted as a single-line JSON object, making
it trivially grep-able and parseable by log-aggregation stacks (Loki,
CloudWatch, Datadog, ELK, etc.).

Each line includes:
  ts       — ISO-8601 timestamp (UTC)
  level    — DEBUG / INFO / WARNING / ERROR / CRITICAL
  logger   — dotted module path (e.g. "omniai.application.chat_service")
  msg      — the log message
  **extra  — any extra fields passed via logger.info("...", extra={...})

In development mode (LOG_FORMAT=text) a human-readable format is used instead.
"""
from __future__ import annotations

import json
import logging
import logging.config
import sys
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record on stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Attach any extra keys that callers pass via extra={...}
        skip = {
            "args", "created", "exc_info", "exc_text", "filename", "funcName",
            "levelname", "levelno", "lineno", "message", "module", "msecs",
            "msg", "name", "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName",
        }
        for key, value in record.__dict__.items():
            if key not in skip:
                payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        try:
            return json.dumps(payload, default=str, separators=(",", ":"))
        except Exception:  # never let logging itself crash the app
            return json.dumps({"level": "ERROR", "msg": "failed to serialize log record"})


def configure_logging(
    *,
    level: str = "INFO",
    fmt: str = "json",
    third_party_level: str = "WARNING",
) -> None:
    """Configure root logger.

    Parameters
    ----------
    level:
        Log level for ``omniai.*`` loggers (e.g. "DEBUG", "INFO", "WARNING").
    fmt:
        ``"json"`` for structured output (production default),
        ``"text"`` for human-readable output (dev default).
    third_party_level:
        Log level for all other libraries (uvicorn, sqlalchemy, httpx, …).
        Keeping this at WARNING prevents noise in production logs.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    # Root logger — catch everything at WARNING+ unless overridden below
    root = logging.getLogger()
    root.setLevel(third_party_level)
    root.handlers.clear()
    root.addHandler(handler)

    # First-party loggers get the full verbosity
    logging.getLogger("omniai").setLevel(level)

    # Silence the most chatty third-party loggers regardless of third_party_level
    for noisy in (
        "uvicorn.access",      # every HTTP request at INFO
        "sqlalchemy.engine",   # SQL statements at INFO
        "httpx",               # HTTP client calls
        "httpcore",
        "multipart",
        "passlib",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
