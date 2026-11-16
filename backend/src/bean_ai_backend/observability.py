import logging
import os

import logfire
from fastapi import FastAPI

from .config import settings

logger = logging.getLogger("bean")


def setup_observability(app: FastAPI) -> None:
    """Trace HTTP requests and agent runs. Call once, when the app is built.

    Traces go to Logfire when LOGFIRE_TOKEN is set, and to any OpenTelemetry backend named by
    OTEL_EXPORTER_OTLP_ENDPOINT; both can be on. Fails open: with neither, the app runs normally
    and sends nothing.
    """
    token = settings.logfire_token
    logfire.configure(
        # Only LOGFIRE_TOKEN turns on sending to Logfire. 'if-token-present' would also pick up a .logfire/
        # credentials file or LOGFIRE_API_KEY, so "no token" wouldn't reliably mean "nothing sent".
        send_to_logfire=bool(token),
        token=token or None,
        service_name="bean-ai",
        environment=settings.environment,
        # uvicorn already logs requests; don't also print every span to stdout.
        console=False,
    )
    # configure() must come before the instrument_* calls, or their spans go nowhere.
    logfire.instrument_pydantic_ai()
    logfire.instrument_fastapi(app, excluded_urls="/api/health")
    # configure() also exports to any OTLP backend named by the standard OTel env vars.
    otlp = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    if not token and not otlp:
        logger.warning(
            "Traces are off: neither LOGFIRE_TOKEN nor OTEL_EXPORTER_OTLP_ENDPOINT is set, "
            "so nothing is sent."
        )
