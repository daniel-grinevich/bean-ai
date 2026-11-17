import json
import logging

import httpx
import pytest

from bean_ai_backend import prompt_sync
from bean_ai_backend.agent.agent_registry import load_instructions
from bean_ai_backend.config import agents, registry, settings


class FakePhoenix:
    """Just enough of Phoenix's prompt API, in memory: prompts, versions and tags."""

    def __init__(self) -> None:
        self.versions: dict[str, dict] = {}  # version id -> version
        self.tags: dict[tuple[str, str], str] = {}  # (prompt, tag) -> version id

    def handle(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.strip("/").split("/")
        match request.method, parts:
            case "GET", ["v1", "prompts", name, "tags", tag]:
                version_id = self.tags.get((name, tag))
                if version_id is None:
                    return httpx.Response(404, text="Not Found")
                return httpx.Response(200, json={"data": self.versions[version_id]})
            case "POST", ["v1", "prompts"]:
                body = json.loads(request.content)
                version_id = f"v{len(self.versions) + 1}"
                self.versions[version_id] = {
                    **body["version"],
                    "id": version_id,
                    "prompt": body["prompt"]["name"],
                }
                return httpx.Response(200, json={"data": {"id": version_id}})
            case "POST", ["v1", "prompt_versions", version_id, "tags"]:
                tag = json.loads(request.content)["name"]
                self.tags[(self.versions[version_id]["prompt"], tag)] = version_id
                return httpx.Response(204)
        return httpx.Response(404, text="Not Found")

    def tagged_text(self, name: str, tag: str) -> str:
        [message] = self.versions[self.tags[(name, tag)]]["template"]["messages"]
        return message["content"]


@pytest.fixture
def phoenix() -> FakePhoenix:
    return FakePhoenix()


@pytest.fixture
def client(phoenix: FakePhoenix) -> httpx.Client:
    # No network: every request goes to the fake.
    return httpx.Client(
        base_url="http://phoenix", transport=httpx.MockTransport(phoenix.handle)
    )


def test_creates_a_tagged_prompt_per_agent_from_its_instructions_file(
    phoenix: FakePhoenix, client: httpx.Client
) -> None:
    assert prompt_sync.sync_prompts(client, "local")

    instructions = load_instructions(agents.agents)
    for agent_id, text in instructions.items():
        assert phoenix.tagged_text(agent_id, "local") == text
    default_model = registry.get(registry.default)
    [version, *_] = phoenix.versions.values()
    assert version["model_name"] == default_model.model
    assert version["template_format"] == "NONE"


def test_a_second_sync_with_no_changes_adds_no_versions(
    phoenix: FakePhoenix, client: httpx.Client
) -> None:
    prompt_sync.sync_prompts(client, "local")
    count = len(phoenix.versions)

    assert prompt_sync.sync_prompts(client, "local")
    assert len(phoenix.versions) == count


def test_changed_text_adds_a_version_and_moves_the_tag(
    phoenix: FakePhoenix, client: httpx.Client
) -> None:
    model = registry.get(registry.default)
    assert prompt_sync.sync_prompt(client, "bean", "v1", model, "local") == "created"
    assert prompt_sync.sync_prompt(client, "bean", "v2", model, "local") == "updated"
    assert prompt_sync.sync_prompt(client, "bean", "v2", model, "local") == "unchanged"

    assert phoenix.tagged_text("bean", "local") == "v2"
    assert len(phoenix.versions) == 2


def test_each_environment_has_its_own_tag(
    phoenix: FakePhoenix, client: httpx.Client
) -> None:
    model = registry.get(registry.default)
    prompt_sync.sync_prompt(client, "bean", "old", model, "production")
    prompt_sync.sync_prompt(client, "bean", "new", model, "local")

    assert phoenix.tagged_text("bean", "production") == "old"
    assert phoenix.tagged_text("bean", "local") == "new"


def test_fails_and_logs_each_agent_when_phoenix_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = httpx.Client(
        base_url="http://phoenix",
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    )

    with caplog.at_level(logging.ERROR, logger="bean.prompt_sync"):
        assert not prompt_sync.sync_prompts(broken, "local")

    failed = {r.getMessage().split(":")[0] for r in caplog.records}
    assert failed == {f"Prompt {agent_id}" for agent_id in agents.agents}


def test_exits_1_without_a_phoenix_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "phoenix_url", "")

    with caplog.at_level(logging.ERROR, logger="bean.prompt_sync"):
        assert prompt_sync.main() == 1
    assert "PHOENIX_URL is not set" in caplog.text
