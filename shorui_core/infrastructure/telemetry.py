"""
Telemetry infrastructure for Shorui AI.

This module provides a singleton TelemetryService that configures OpenTelemetry
tracing and metrics. It supports auto-instrumentation for common libraries
and provides hooks for manual instrumentation.
"""

from __future__ import annotations

import logging
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider

from shorui_core.config import settings

logger = logging.getLogger(__name__)


class TelemetryService:
    """Singleton service for configuring and managing OpenTelemetry."""

    _instance: Optional[TelemetryService] = None

    def __new__(cls) -> TelemetryService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.tracer_provider: Optional[TracerProvider] = None
        self.meter_provider: Optional[MeterProvider] = None

    def setup(self) -> None:
        """
        Initialize OpenTelemetry providers and instrumentations.
        Safe to call multiple times (idempotent).
        """
        if not settings.ENABLE_TELEMETRY:
            logger.info("Telemetry disabled via configuration.")
            return

        if self.tracer_provider is not None:
            logger.warning("Telemetry already initialized.")
            return

        resource = Resource.create({
            "service.name": settings.SERVICE_NAME,
            "service.instance.id": settings.OTEL_SERVICE_NAME or "shorui-ai-instance",
        })

        # 1. Configure Tracing
        self.tracer_provider = TracerProvider(resource=resource)
        
        # Add Exporter (OTLP or Console)
        if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            otlp_exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
            span_processor = BatchSpanProcessor(otlp_exporter)
            self.tracer_provider.add_span_processor(span_processor)
            logger.info(f"OTLP Tracing enabled -> {settings.OTEL_EXPORTER_OTLP_ENDPOINT}")
        else:
            # Fallback to console in dev if enabled but no endpoint (debug mode)
            # useful for verifying traces locally without a collector
            self.tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OTLP Endpoint not set. Tracing to console (Debug).")

        trace.set_tracer_provider(self.tracer_provider)

        trace.set_tracer_provider(self.tracer_provider)

        # 2. Configure Metrics
        # We use PrometheusMetricReader which exposes metrics for scraping
        # The actual exposition happens when we mount the app or use start_http_server
        # But here we just attach the reader to the provider.
        reader = PrometheusMetricReader()
        self.meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(self.meter_provider)

        # 3. Auto-Instrumentation
        self._instrument_libraries()
        logger.info("Telemetry initialized successfully.")

    def _instrument_libraries(self) -> None:
        """Instrument standard libraries used in the stack."""
        
        # HTTP Client (httpx) - outgoing requests
        HTTPXClientInstrumentor().instrument()
        
        # Redis
        RedisInstrumentor().instrument()
        
        # Celery (instrumentation must happen in worker too)
        CeleryInstrumentor().instrument()
        
        # Note: FastAPI instrumentation usually happens at app creation
        # calling TelemetryService.instrument_app(app)

    def instrument_app(self, app) -> None:
        """Instrument a FastAPI application."""
        if not settings.ENABLE_TELEMETRY:
            return
            
        # OTel Tracing
        FastAPIInstrumentor.instrument_app(app, tracer_provider=self.tracer_provider)
        
        # Prometheus Metrics (Standard HTTP metrics)
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app)


# Global helper
def setup_telemetry() -> None:
    TelemetryService().setup()
