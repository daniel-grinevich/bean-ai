from pathlib import Path

import pytest
from pydantic_ai.agent.spec import get_capability_registry
from pydantic_ai.models.test import TestModel

from bean_ai_backend.agent import agent_registry
from bean_ai_backend.agent.agent_registry import AgentsFileError, load_agents
from bean_ai_backend.agent.errors import AgentUnavailable
from bean_ai_backend.agent.factory import get_agent
from bean_ai_backend.agent.instructions import INSTRUCTIONS
from bean_ai_backend.agent.tools import CAPABILITY_TYPES
from bean_ai_backend.config import settings

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
    assert set(agents.agents) == {"bean", "engineering"}
    agents.check_capabilities(get_capability_registry(CAPABILITY_TYPES))
    agents.check_instructions(INSTRUCTIONS)


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


def test_agent_without_instructions_is_named(agents_file: Path) -> None:
    agents_file.write_text(GOOD)
    with pytest.raises(AgentsFileError, match="for: ops, eng"):
        load_agents().check_instructions(INSTRUCTIONS)


def test_engineering_agent_refuses_to_run_without_repo_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    with pytest.raises(AgentUnavailable, match="REPO_ROOT is not set"):
        get_agent("engineering", CLAUDE)


def test_engineering_agent_gets_the_repo_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "repo_root", tmp_path)
    model = TestModel(call_tools=[])

    with get_agent("engineering", CLAUDE).override(model=model):
        get_agent("engineering", CLAUDE).run_sync("hi")

    assert [t.name for t in model.last_model_request_parameters.function_tools] == [
        "read_repo_file"
    ]


def test_bean_agent_has_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    model = TestModel(call_tools=[])

    with get_agent("bean", CLAUDE).override(model=model):
        get_agent("bean", CLAUDE).run_sync("hi")

    assert model.last_model_request_parameters.function_tools == []
