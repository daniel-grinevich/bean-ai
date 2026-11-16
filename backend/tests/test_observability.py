import logging

import logfire
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from bean_ai_backend.agent.factory import get_agent
from bean_ai_backend.config import agents, registry, settings
from bean_ai_backend.main import app
from bean_ai_backend.observability import setup_observability


async def echo(messages: list[ModelMessage], info: AgentInfo):
    yield "hi"


def test_app_starts_and_serves_a_chat_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    assert logfire.DEFAULT_LOGFIRE_INSTANCE.config.send_to_logfire is False

    agent = get_agent(agents.default, registry.default)
    with (
        TestClient(app) as client,
        agent.override(model=FunctionModel(stream_function=echo)),
    ):
        res = client.post("/api/chat", json={"message": "hello"})

    assert res.status_code == 200
    assert res.text.rstrip().endswith("event: done\ndata: {}")


def test_warns_once_that_traces_are_off(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="bean"):
        setup_observability(FastAPI())

    [warning] = [r.getMessage() for r in caplog.records if r.name == "bean"]
    assert warning.startswith(
        "Traces are off: neither LOGFIRE_TOKEN nor OTEL_EXPORTER_OTLP"
    )
