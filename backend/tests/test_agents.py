from pathlib import Path

import pytest
from pydantic_ai.agent.spec import get_capability_registry
from pydantic_ai.models.test import TestModel

from bean_ai_backend.agent import agent_registry
from bean_ai_backend.agent.agent_registry import (
    AgentsFileError,
    load_agents,
    load_instructions,
)
from bean_ai_backend.agent.deps import AgentDeps
from bean_ai_backend.agent.errors import AgentUnavailable
from bean_ai_backend.agent.factory import get_agent
from bean_ai_backend.agent.tools import CAPABILITY_TYPES
from bean_ai_backend.config import settings
from bean_ai_backend.repos import LocalRepoSource

CLAUDE = "claude-sonnet-5"

GOOD = """\
default: ops
agents:
  ops:
    description: Helps with ops.
  eng:
    description: Helps with code.
    capabilities: [RepoFiles]
"""


@pytest.fixture
def agents_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point load_agents at a temporary agents.yaml; tests write their YAML into it."""
    path = tmp_path / "agents.yaml"
    monkeypatch.setattr(agent_registry, "AGENTS_FILE", path)
    return path


def test_bundled_file_is_valid() -> None:
    agents = load_agents()
    assert agents.default == "bean"
    assert set(agents.agents) == {"bean", "senior-dev-daniel"}
    agents.check_capabilities(get_capability_registry(CAPABILITY_TYPES))
    assert set(load_instructions(agents.agents)) == {"bean", "senior-dev-daniel"}


def test_default_override(agents_file: Path) -> None:
    agents_file.write_text(GOOD)
    assert load_agents(default_override="eng").default == "eng"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (GOOD.replace("default: ops", "default: nope"), "default agent 'nope'"),
        (
            GOOD.replace("    description: Helps with ops.\n", "    model: x\n"),
            "`model` can't be set here",
        ),
        (
            GOOD.replace("    description: Helps with ops.\n", "    instructions: x\n"),
            "`instructions` can't be set here",
        ),
        (
            GOOD.replace(
                "    description: Helps with ops.\n", "    descriptionz: typo\n"
            ),
            "descriptionz",
        ),
        ("default: x\nagents: {}\n", "agents"),
        ("- just\n- a list\n", "must be a mapping"),
    ],
)
def test_bad_files_fail_with_a_clear_error(
    agents_file: Path, text: str, message: str
) -> None:
    agents_file.write_text(text)
    with pytest.raises(AgentsFileError) as exc:
        load_agents()
    assert message in str(exc.value)


def test_unknown_capability_is_named(agents_file: Path) -> None:
    agents_file.write_text(GOOD.replace("[RepoFiles]", "[RepoFile]"))
    agents = load_agents()
    with pytest.raises(AgentsFileError, match="eng: RepoFile"):
        agents.check_capabilities(get_capability_registry(CAPABILITY_TYPES))


def test_agent_without_instructions_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_registry, "INSTRUCTIONS_DIR", tmp_path)
    (tmp_path / "ops.md").write_text("Help with ops.")
    (tmp_path / "eng.md").write_text("  \n")
    (tmp_path / "other.md").write_text("Not an agent.")

    with pytest.raises(AgentsFileError, match=r"instructions in .*: eng\.md, new\.md$"):
        load_instructions(["ops", "eng", "new"])


def test_senior_dev_daniel_refuses_to_run_without_a_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    agent = get_agent("senior-dev-daniel", CLAUDE)
    with (
        agent.override(model=TestModel()),
        pytest.raises(AgentUnavailable, match="No repository is selected"),
    ):
        agent.run_sync("hi", deps=AgentDeps())


def test_senior_dev_daniel_gets_the_repo_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    model = TestModel(call_tools=[])
    agent = get_agent("senior-dev-daniel", CLAUDE)

    with agent.override(model=model):
        agent.run_sync("hi", deps=AgentDeps(repo=LocalRepoSource(tmp_path)))

    assert [t.name for t in model.last_model_request_parameters.function_tools] == [
        "read_repo_file"
    ]


def test_bean_agent_has_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    model = TestModel(call_tools=[])

    with get_agent("bean", CLAUDE).override(model=model):
        get_agent("bean", CLAUDE).run_sync("hi", deps=AgentDeps())

    assert model.last_model_request_parameters.function_tools == []
