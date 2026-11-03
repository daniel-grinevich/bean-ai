from pathlib import Path

import pytest

from bean_ai_backend.registry import ModelsFileError, load_registry

GOOD = """\
default: claude-sonnet-5
models:
  - id: claude-sonnet-5
    label: Claude Sonnet 5
    provider: anthropic
    model: claude-sonnet-5
    settings: {max_tokens: 8192}
  - id: glm
    label: GLM
    provider: openrouter
    model: z-ai/glm-5.3
  - id: old
    label: Old
    provider: openrouter
    model: old/model
    enabled: false
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(text)
    return path


def test_bundled_file_is_valid() -> None:
    registry = load_registry(Path(__file__).parents[1] / "models.yaml")
    assert registry.default == "claude-sonnet-5"
    assert [m.id for m in registry.enabled()] == [
        "claude-sonnet-5",
        "claude-opus-5-5",
        "deepseek/deepseek-v4.1-flash-1017",
        "z-ai/glm-5.3",
    ]


def test_loads_entries_and_skips_disabled(tmp_path: Path) -> None:
    registry = load_registry(write(tmp_path, GOOD))
    assert [m.id for m in registry.enabled()] == ["claude-sonnet-5", "glm"]
    assert registry.get("claude-sonnet-5").settings == {"max_tokens": 8192}
    assert registry.get("glm").enabled is True
    assert registry.get("old") is None


def test_default_override(tmp_path: Path) -> None:
    assert load_registry(write(tmp_path, GOOD), default_override="glm").default == "glm"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (GOOD.replace("provider: anthropic", "provider: openai"), "provider"),
        (GOOD.replace("id: glm", "id: claude-sonnet-5"), "duplicate model id(s): claude-sonnet-5"),
        (GOOD.replace("default: claude-sonnet-5", "default: nope"), "default model 'nope'"),
        (GOOD.replace("default: claude-sonnet-5", "default: old"), "default model 'old'"),
        (GOOD.replace("    model: z-ai/glm-5.3\n", "    model: z-ai/glm-5.3\n    api_key: sk-123\n"), "api_key"),
        ("default: x\nmodels: []\n", "models"),
        ("- just\n- a list\n", "must be a mapping"),
        ("default: [unclosed\n", "not valid YAML"),
    ],
)
def test_bad_files_fail_with_a_clear_error(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ModelsFileError, match="models") as exc:
        load_registry(write(tmp_path, text))
    assert message in str(exc.value)


def test_bad_default_override(tmp_path: Path) -> None:
    with pytest.raises(ModelsFileError, match="AGENT_MODEL"):
        load_registry(write(tmp_path, GOOD), default_override="nope")


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ModelsFileError, match="Can't read models file"):
        load_registry(tmp_path / "missing.yaml")
