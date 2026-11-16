from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol


class RepoError(Exception):
    """A read that failed because of the path asked for. The message says what to pass instead."""


@dataclass(frozen=True)
class RepoFile:
    data: bytes  # at most the max_bytes asked for
    size: int  # the whole file's size in bytes


class RepoSource(Protocol):
    """A repository agents can read: a local checkout now, a Forgejo repo later."""

    async def read_file(self, path: str, max_bytes: int) -> RepoFile:
        """Read up to `max_bytes` of `path` (relative to the repo root). Raises RepoError."""
        ...


def repo_path(path: str) -> PurePosixPath:
    """Normalize a path relative to the repo root, rejecting absolute paths and `..` above the root.

    Every RepoSource calls this first, so a forge backend gets the same rules as a local checkout.
    """
    if PurePosixPath(path).is_absolute():
        raise RepoError(
            f"{path!r} is absolute. Pass a path relative to the repository root."
        )
    parts: list[str] = []
    for part in PurePosixPath(path).parts:
        if part == "..":
            if not parts:
                raise RepoError(
                    f"{path!r} is outside the repository. Pass a path inside the repository root."
                )
            parts.pop()
        elif part != ".":
            parts.append(part)
    return PurePosixPath(*parts)
