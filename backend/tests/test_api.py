import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openrouter import OpenRouterModel

from bean_ai_backend.agent.factory import MissingApiKey, build_model, get_agent
from bean_ai_backend.config import registry, settings
from bean_ai_backend.services.store import store

CLAUDE = "claude-sonnet-5"
DEEPSEEK = "deepseek/deepseek-v4.1-flash-1017"


def events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n")
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


async def echo(messages: list[ModelMessage], info: AgentInfo):
    yield "hi "
    yield "there"


def test_health_reports_default_model(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "model": registry.default}


def test_models_availability_follows_keys(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    body = client.get("/api/models").json()
    assert body["default"] == "claude-sonnet-5"
    assert [m["id"] for m in body["models"]] == [CLAUDE, "claude-opus-5-5", DEEPSEEK, "z-ai/glm-5.3"]
    assert body["models"][0] == {"id": CLAUDE, "label": "Claude Sonnet 5", "provider": "anthropic", "available": False}
    assert not any(m["available"] for m in body["models"])

    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    available = {m["id"]: m["available"] for m in client.get("/api/models").json()["models"]}
    assert available == {CLAUDE: True, "claude-opus-5-5": True, DEEPSEEK: False, "z-ai/glm-5.3": False}


def test_build_model_routes_by_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "open_router_key", "test-key")
    claude = build_model(registry.get(CLAUDE))
    assert isinstance(claude, AnthropicModel)
    assert claude.model_name == "claude-sonnet-5"
    assert claude.settings == {"max_tokens": 8192}
    glm = build_model(registry.get("z-ai/glm-5.3"))
    assert isinstance(glm, OpenRouterModel)
    assert glm.model_name == "z-ai/glm-5.3"


@pytest.mark.parametrize(("model_id", "env_var"), [(CLAUDE, "ANTHROPIC_API_KEY"), (DEEPSEEK, "OPEN_ROUTER_KEY")])
def test_missing_key_names_the_right_variable(model_id: str, env_var: str, client: TestClient) -> None:
    with pytest.raises(MissingApiKey, match=env_var):
        get_agent(model_id)
    res = client.post("/api/chat", json={"message": "hello", "model": model_id})
    assert events(res.text)[-1] == (
        "error",
        {"message": f"{env_var} is not set, so Bean can't reach {registry.get(model_id).label}."},
    )


def test_unknown_model_is_422(client: TestClient) -> None:
    res = client.post("/api/chat", json={"message": "hello", "model": "gpt-9"})
    assert res.status_code == 422
    assert "Unknown model" in res.text


@pytest.mark.parametrize("model_id", [None, DEEPSEEK])
def test_chat_uses_requested_model_and_records_it(
    model_id: str | None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "open_router_key", "test-key")
    expected = model_id or registry.default
    # Fail if the wrong agent is used: only the expected one gets the fake model.
    with get_agent(expected).override(model=FunctionModel(stream_function=echo)):
        res = client.post("/api/chat", json={"message": "hello", "model": model_id})
    evs = events(res.text)
    assert evs[0][1]["model"] == expected
    assert [e for e in evs if e[0] == "delta"] == [("delta", {"text": "hi "}), ("delta", {"text": "there"})]
    assert evs[-1] == ("done", {})

    conv = store.get(evs[0][1]["conversation_id"])
    assert [(m.role, m.content, m.model) for m in conv.messages] == [
        ("user", "hello", None),
        ("assistant", "hi there", expected),
    ]
