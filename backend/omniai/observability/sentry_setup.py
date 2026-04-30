"""M16 — Sentry error reporting setup.

Call ``configure_sentry(settings)`` once at app startup.
When ``SENTRY_DSN`` is unset this is a no-op so dev/test environments are
never affected.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def configure_sentry(settings) -> None:
    """Initialise Sentry SDK.  No-op if SENTRY_DSN is not configured."""
    dsn = getattr(settings, "sentry_dsn", None)
    if not dsn:
        logger.debug("SENTRY_DSN not configured; Sentry disabled")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        import logging as _logging

        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=getattr(settings, "sentry_traces_sample_rate", 0.1),
            environment=getattr(settings, "app_env", "production"),
            release=f"omniai@{getattr(settings, 'app_version', '0.1.0')}",
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=_logging.WARNING,        # Breadcrumbs from WARNING+
                    event_level=_logging.ERROR,    # Send events for ERROR+
                ),
            ],
        )
        logger.info("Sentry initialised (env=%s)", settings.app_env)
    except ImportError:
        logger.warning("sentry-sdk not installed; error reporting disabled")
    except Exception as exc:
        logger.warning("Sentry init failed: %s", exc)
