from pathlib import Path

import pytest

from bean_ai_backend.repos import LocalRepoSource, RepoError, repo_path

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize(
    ("path", "expected"),
    [("src/app.py", "src/app.py"), ("./src/../README.md", "README.md"), ("", ".")],
)
def test_repo_path_normalizes(path: str, expected: str) -> None:
    assert str(repo_path(path)) == expected


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/etc/passwd", "is absolute"),
        ("../secret", "outside"),
        ("a/../../b", "outside"),
    ],
)
def test_repo_path_rejects_paths_leaving_the_root(path: str, message: str) -> None:
    with pytest.raises(RepoError, match=message):
        repo_path(path)


async def test_local_source_refuses_symlinks_out_of_the_checkout(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "secret").write_text("hunter2")
    (root / "link").symlink_to(tmp_path / "secret")

    with pytest.raises(RepoError, match="outside"):
        await LocalRepoSource(root).read_file("link", 100)


async def test_local_source_reports_directories_and_missing_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "sub").mkdir()
    source = LocalRepoSource(tmp_path)
    with pytest.raises(RepoError, match="is a directory"):
        await source.read_file("sub", 100)
    with pytest.raises(RepoError, match="is not found"):
        await source.read_file("nope.txt", 100)
