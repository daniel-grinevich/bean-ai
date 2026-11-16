import codecs
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import FunctionToolset, ModelRetry
from pydantic_ai.capabilities import AbstractCapability

from ...config import settings
from ..errors import AgentUnavailable

MAX_BYTES = 100_000


@dataclass
class RepoFiles(AbstractCapability[None]):
    """Read-only access to one repository checkout. In agents.yaml: `capabilities: [RepoFiles]`."""

    root: Path
    _toolset: FunctionToolset[None] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._toolset = repo_file_toolset(self.root)

    @classmethod
    def from_spec(cls) -> "RepoFiles":
        # Fail closed: no REPO_ROOT means no file access. Defaulting to the working directory would expose
        # the whole container filesystem in the deployed image, which has no repository checkout.
        root = settings.repo_root
        if root is None:
            raise AgentUnavailable(
                "REPO_ROOT is not set, so this agent can't read the repository."
            )
        if not root.is_dir():
            raise AgentUnavailable(
                f"REPO_ROOT ({root}) is not a directory, so this agent can't read the repository."
            )
        return cls(root)

    def get_toolset(self) -> FunctionToolset[None]:
        return self._toolset


def repo_file_toolset(root: Path) -> FunctionToolset[None]:
    """Tools that read files inside `root`. Attach with `Agent(..., toolsets=[repo_file_toolset(root)])`."""
    root = root.resolve()
    toolset: FunctionToolset[None] = FunctionToolset()

    @toolset.tool_plain
    def read_repo_file(path: str) -> str:
        """Read a UTF-8 text file from the repository.

        Output over 100 KB is cut off, with a note at the end saying so.

        Args:
            path: File path relative to the repository root, e.g. `backend/pyproject.toml`.
        """
        if Path(path).is_absolute():
            raise ModelRetry(
                f"{path!r} is absolute. Pass a path relative to the repository root."
            )
        # resolve() follows symlinks and collapses `..`, so this also catches links pointing outside.
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise ModelRetry(
                f"{path!r} is outside the repository. Pass a path inside the repository root."
            )
        if not target.is_file():
            what = "a directory" if target.is_dir() else "not found"
            raise ModelRetry(f"{path!r} is {what}. Pass the path of an existing file.")

        with target.open("rb") as f:
            data = f.read(MAX_BYTES + 1)
        truncated = len(data) > MAX_BYTES
        try:
            # final=False drops a multi-byte character split by the cut instead of raising on it.
            text = codecs.getincrementaldecoder("utf-8")().decode(
                data[:MAX_BYTES], final=not truncated
            )
        except UnicodeDecodeError:
            raise ModelRetry(
                f"{path!r} is not UTF-8 text (probably binary). Read a text file instead."
            ) from None

        if truncated:
            size = target.stat().st_size
            text += f"\n\n[truncated: file is {size} bytes, only the first {MAX_BYTES} were read]"
        return text

    return toolset
