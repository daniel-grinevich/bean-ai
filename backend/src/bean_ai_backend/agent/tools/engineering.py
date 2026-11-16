import codecs
from dataclasses import dataclass

from pydantic_ai import FunctionToolset, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability

from ...repos import RepoError
from ..deps import AgentDeps
from ..errors import AgentUnavailable

MAX_BYTES = 100_000

repo_files: FunctionToolset[AgentDeps] = FunctionToolset()


@repo_files.tool
async def read_repo_file(ctx: RunContext[AgentDeps], path: str) -> str:
    """Read a UTF-8 text file from the repository.

    Output over 100 KB is cut off, with a note at the end saying so.

    Args:
        path: File path relative to the repository root, e.g. `backend/pyproject.toml`.
    """
    repo = ctx.deps.repo
    assert repo is not None  # RepoFiles.before_run refuses runs without one
    try:
        file = await repo.read_file(path, MAX_BYTES)
    except RepoError as e:
        raise ModelRetry(str(e)) from None

    truncated = file.size > MAX_BYTES
    try:
        # final=False drops a multi-byte character split by the cut instead of raising on it.
        text = codecs.getincrementaldecoder("utf-8")().decode(
            file.data, final=not truncated
        )
    except UnicodeDecodeError:
        raise ModelRetry(
            f"{path!r} is not UTF-8 text (probably binary). Read a text file instead."
        ) from None
    if truncated:
        text += f"\n\n[truncated: file is {file.size} bytes, only the first {MAX_BYTES} were read]"
    return text


@dataclass
class RepoFiles(AbstractCapability[AgentDeps]):
    """Read-only access to the run's repository (`deps.repo`). In agents.yaml: `capabilities: [RepoFiles]`."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return repo_files

    async def before_run(self, ctx: RunContext[AgentDeps]) -> None:
        # Fail closed, before any model request: no repository means this agent doesn't run.
        if ctx.deps.repo is None:
            raise AgentUnavailable(
                "No repository is selected, so this agent can't read code."
            )
