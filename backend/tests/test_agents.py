from pathlib import Path

import pytest
from pydantic_ai.agent.spec import get_capability_registry
from pydantic_ai.models.test import TestModel

from bean_ai_backend.agent.agent_registry import AgentsFileError, load_agents
from bean_ai_backend.agent.errors import AgentUnavailable
from bean_ai_backend.agent.factory import get_agent
from bean_ai_backend.agent.tools import CAPABILITY_TYPES
from bean_ai_backend.config import settings

CLAUDE = "claude-sonnet-5"

GOOD = """\
default: ops
agents:
  ops:
    instructions: Help with ops.
  eng:
    instructions: Help with code.
    capabilities: [RepoFiles]
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "agents.yaml"
    path.write_text(text)
    return path


def test_bundled_file_is_valid() -> None:
    agents = load_agents(Path(__file__).parents[1] / "agents.yaml")
    assert agents.default == "bean"
    assert set(agents.agents) == {"bean", "engineering"}
    agents.check_capabilities(get_capability_registry(CAPABILITY_TYPES))


def test_default_override(tmp_path: Path) -> None:
    assert load_agents(write(tmp_path, GOOD), default_override="eng").default == "eng"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (GOOD.replace("default: ops", "default: nope"), "default agent 'nope'"),
        (
            GOOD.replace("    instructions: Help with ops.\n", "    model: x\n"),
            "`model` can't be set here",
        ),
        (
            GOOD.replace(
                "    instructions: Help with ops.\n", "    instructionz: typo\n"
            ),
            "instructionz",
        ),
        ("default: x\nagents: {}\n", "agents"),
        ("- just\n- a list\n", "must be a mapping"),
    ],
)
def test_bad_files_fail_with_a_clear_error(
    tmp_path: Path, text: str, message: str
) -> None:
    with pytest.raises(AgentsFileError) as exc:
        load_agents(write(tmp_path, text))
    assert message in str(exc.value)


def test_unknown_capability_is_named(tmp_path: Path) -> None:
    agents = load_agents(write(tmp_path, GOOD.replace("[RepoFiles]", "[RepoFile]")))
    with pytest.raises(AgentsFileError, match="eng: RepoFile"):
        agents.check_capabilities(get_capability_registry(CAPABILITY_TYPES))


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
