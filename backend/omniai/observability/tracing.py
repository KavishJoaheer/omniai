"""M16 — OpenTelemetry tracing setup.

Call ``configure_tracing(settings)`` once at application startup (in
``create_app``).  When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set the traces are
exported via OTLP/gRPC; otherwise a ``NoOpTracerProvider`` is installed so
the instrumentation decorators are zero-cost no-ops in development.

FastAPI and SQLAlchemy instrumentation are applied automatically — every HTTP
request gets a root span and every DB query gets a child span with the SQL
statement attached.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def configure_tracing(settings) -> None:
    """Wire up OTel tracing.  Safe to call multiple times (idempotent)."""
    endpoint = getattr(settings, "otel_exporter_otlp_endpoint", None)
    service_name = getattr(settings, "otel_service_name", "omniai-api")

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("OTel OTLP exporter → %s", endpoint)
            except Exception as exc:
                # ImportError: package not installed
                # TypeError/RuntimeError: protobuf version mismatch (gRPC exporter
                #   requires protobuf < 4.x; downgrade or use the HTTP exporter)
                logger.warning(
                    "OTel OTLP exporter could not be initialised (%s: %s). "
                    "Traces will not be exported. "
                    "If using gRPC exporter, ensure protobuf<4 is installed or "
                    "switch to opentelemetry-exporter-otlp-proto-http.",
                    type(exc).__name__, exc,
                )
        else:
            logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set; OTel tracing is no-op")

        trace.set_tracer_provider(provider)

    except ImportError:
        logger.warning("opentelemetry-sdk not installed; tracing disabled")
        return

    # Instrument SQLAlchemy (must be done before engines are created)
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
    except (ImportError, Exception) as exc:
        logger.debug("SQLAlchemy OTel instrumentation skipped: %s", exc)


def instrument_app(app) -> None:
    """Attach FastAPI instrumentation to the already-created app instance.

    Must be called AFTER ``configure_tracing`` and AFTER the FastAPI app
    object is created so the middleware is registered correctly.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.debug("FastAPI OTel instrumentation applied")
    except (ImportError, Exception) as exc:
        logger.debug("FastAPI OTel instrumentation skipped: %s", exc)
