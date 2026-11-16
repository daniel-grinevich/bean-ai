import logging

from fastapi import FastAPI
from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
from openinference.semconv.resource import ResourceAttributes
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai import Agent, InstrumentationSettings

from .config import settings

logger = logging.getLogger("bean")


def build_tracer_provider(endpoint: str, api_key: str = "") -> TracerProvider:
    """Traces that export over OTLP/HTTP to `endpoint` (e.g. Phoenix at http://localhost:6006)."""
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "bean-ai",
                "deployment.environment.name": settings.environment,
                # The Phoenix project the traces land in: one per environment (bean-local, ...).
                ResourceAttributes.PROJECT_NAME: f"bean-{settings.environment}",
            }
        )
    )
    # Rewrites Pydantic AI's OTel GenAI spans into OpenInference attributes, which is what
    # Phoenix reads to show agent, model and tool spans with their messages and token counts.
    provider.add_span_processor(OpenInferenceSpanProcessor())
    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
    )
    # Exports from a background thread: a down collector logs an error, it never blocks a request.
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def setup_tracing(app: FastAPI) -> TracerProvider | None:
    """Trace HTTP requests and every agent run. Call once, when the app is built.

    Fails open: without OTEL_EXPORTER_OTLP_ENDPOINT the app runs normally and sends nothing.
    """
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        logger.warning(
            "Tracing is off: OTEL_EXPORTER_OTLP_ENDPOINT is not set, so no traces are sent."
        )
        return None
    provider = build_tracer_provider(endpoint, settings.phoenix_api_key)
    # Prompts, instructions, outputs and tool data are recorded: the collector is self-hosted.
    Agent.instrument_all(
        InstrumentationSettings(tracer_provider=provider, include_content=True)
    )
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/api/health",
        # One span per request, not one per streamed SSE chunk.
        exclude_spans=["send", "receive"],
    )
    return provider
