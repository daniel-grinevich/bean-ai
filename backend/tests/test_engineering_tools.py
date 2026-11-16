from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequestPart,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from bean_ai_backend.agent.deps import AgentDeps
from bean_ai_backend.agent.errors import AgentUnavailable
from bean_ai_backend.agent.tools.engineering import MAX_BYTES, RepoFiles
from bean_ai_backend.repos import LocalRepoSource

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def call_read_repo_file(root: Path, path: str) -> ModelRequestPart:
    """Run an agent whose model calls read_repo_file(path) once, and return what the tool sent back."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("read_repo_file", {"path": path})])
        return ModelResponse(parts=[TextPart("done")])

    agent = Agent(FunctionModel(model), deps_type=AgentDeps, capabilities=[RepoFiles()])
    result = await agent.run(
        "read the file", deps=AgentDeps(repo=LocalRepoSource(root))
    )
    # messages: [user prompt, tool call, tool result, final text]
    return result.all_messages()[2].parts[0]


async def test_model_sees_docstring_as_tool_description(tmp_path: Path) -> None:
    model = TestModel(call_tools=[])
    agent = Agent(model, deps_type=AgentDeps, capabilities=[RepoFiles()])
    await agent.run("hi", deps=AgentDeps(repo=LocalRepoSource(tmp_path)))

    [tool] = model.last_model_request_parameters.function_tools
    assert tool.name == "read_repo_file"
    assert tool.description.startswith("Read a UTF-8 text file")
    assert (
        "relative to the repository root"
        in tool.parameters_json_schema["properties"]["path"]["description"]
    )


async def test_refuses_to_run_without_a_repository() -> None:
    model = TestModel(call_tools=[])
    agent = Agent(model, deps_type=AgentDeps, capabilities=[RepoFiles()])

    with pytest.raises(AgentUnavailable, match="No repository is selected"):
        await agent.run("hi", deps=AgentDeps())
    assert (
        model.last_model_request_parameters is None
    )  # refused before any model request


async def test_reads_a_file(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n")

    part = await call_read_repo_file(tmp_path, "src/app.py")

    assert isinstance(part, ToolReturnPart)
    assert part.content == "print('hi')\n"


async def test_refuses_to_escape_the_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "secret").write_text("hunter2")

    part = await call_read_repo_file(root, "../secret")

    # A ModelRetry comes back to the model as a tool result marked 'retried', not as file content.
    assert isinstance(part, ToolReturnPart)
    assert part.outcome == "retried"
    assert "outside the repository" in part.content
    assert "hunter2" not in part.content


async def test_truncates_large_files(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("x" * (MAX_BYTES + 500))

    part = await call_read_repo_file(tmp_path, "big.txt")

    assert isinstance(part, ToolReturnPart)
    assert part.content.startswith("x" * MAX_BYTES)
    assert part.content.endswith(
        f"[truncated: file is {MAX_BYTES + 500} bytes, only the first {MAX_BYTES} were read]"
    )
