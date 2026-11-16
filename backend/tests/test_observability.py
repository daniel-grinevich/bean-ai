import logging
import socket
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent, InstrumentationSettings
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from bean_ai_backend import main
from bean_ai_backend.agent.factory import get_agent
from bean_ai_backend.config import agents, registry, settings
from bean_ai_backend.observability import build_tracer_provider, setup_tracing


async def echo(messages: list[ModelMessage], info: AgentInfo):
    yield "hi"


def test_app_starts_and_serves_a_chat_without_an_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    assert main.tracer_provider is None

    agent = get_agent(agents.default, registry.default)
    with (
        TestClient(main.app) as client,
        agent.override(model=FunctionModel(stream_function=echo)),
    ):
        res = client.post("/api/chat", json={"message": "hello"})

    assert res.status_code == 200
    assert res.text.rstrip().endswith("event: done\ndata: {}")


def test_warns_once_that_tracing_is_off(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="bean"):
        assert setup_tracing(FastAPI()) is None

    [warning] = [r.getMessage() for r in caplog.records if r.name == "bean"]
    assert warning.startswith("Tracing is off: OTEL_EXPORTER_OTLP_ENDPOINT is not set")


@pytest.mark.parametrize("environment", ["local", "staging", "production"])
def test_traces_go_to_the_phoenix_project_for_the_environment(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", environment)
    # Nothing listens here and no span is created, so nothing is sent.
    provider = build_tracer_provider("http://127.0.0.1:9")
    try:
        attributes = provider.resource.attributes
        assert attributes["openinference.project.name"] == f"bean-{environment}"
        assert attributes["deployment.environment.name"] == environment
    finally:
        provider.shutdown()


def test_runs_finish_and_export_errors_are_logged_when_the_collector_is_down(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A local port nothing listens on, so the export is refused and nothing is sent.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
    # Give up retrying after 1s.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "1")
    provider = build_tracer_provider(f"http://127.0.0.1:{closed_port}")
    agent = Agent(
        FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])),
        capabilities=[
            Instrumentation(InstrumentationSettings(tracer_provider=provider))
        ],
    )

    start = time.monotonic()
    assert agent.run_sync("hello").output == "ok"
    assert time.monotonic() - start < 0.5  # the export doesn't run on the request path

    with caplog.at_level(logging.WARNING):
        provider.shutdown()  # flushes the batch: the export fails here, in the background thread
    assert any(
        r.levelno == logging.ERROR and "Failed to export" in r.getMessage()
        for r in caplog.records
    )
