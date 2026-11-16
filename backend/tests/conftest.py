import os

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import models

from bean_ai_backend.agent.factory import get_agent
from bean_ai_backend.config import settings

# Tests never send traces anywhere, even with LOGFIRE_TOKEN in the shell or backend/.env, or an
# OTLP endpoint in the shell. This runs before any test module imports bean_ai_backend.main,
# which is where tracing is configured.
settings.logfire_token = ""
for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
    os.environ.pop(name, None)
# Tests never reach a real model; anything that tries fails loudly.
models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture(autouse=True)
def no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no API keys (ignoring any local .env) and no cached agents."""
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "open_router_key", "")
    get_agent.cache_clear()
    yield
    get_agent.cache_clear()


@pytest.fixture
def client() -> TestClient:
    from bean_ai_backend.main import app

    return TestClient(app)
