from dataclasses import dataclass
from pathlib import Path

from .base import RepoError, RepoFile, repo_path


@dataclass(frozen=True)
class LocalRepoSource:
    """A repository checked out on this machine."""

    root: Path

    async def read_file(self, path: str, max_bytes: int) -> RepoFile:
        root = self.root.resolve()
        target = (root / repo_path(path)).resolve()
        # resolve() follows symlinks, so this catches a link inside the checkout pointing outside it.
        if not target.is_relative_to(root):
            raise RepoError(
                f"{path!r} is outside the repository. Pass a path inside the repository root."
            )
        if not target.is_file():
            what = "a directory" if target.is_dir() else "not found"
            raise RepoError(f"{path!r} is {what}. Pass the path of an existing file.")
        with target.open("rb") as f:
            data = f.read(max_bytes)
        return RepoFile(data=data, size=target.stat().st_size)
