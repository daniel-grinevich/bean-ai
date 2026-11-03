import pytest
from fastapi.testclient import TestClient
from pydantic_ai import models

from bean_ai_backend.agent import get_agent
from bean_ai_backend.config import settings
from bean_ai_backend.main import app

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
    return TestClient(app)
