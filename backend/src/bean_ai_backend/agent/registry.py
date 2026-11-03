from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Provider = Literal["anthropic", "openrouter"]

# Which env var holds each provider's API key. models.yaml never holds secrets.
KEY_ENV_VARS: dict[Provider, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPEN_ROUTER_KEY",
}


class ModelsFileError(RuntimeError):
    pass


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    provider: Provider
    # The provider's own model name (often the same as `id`).
    model: str = Field(min_length=1)
    enabled: bool = True
    # Passed to Pydantic AI as model settings, e.g. {max_tokens: 8192}.
    settings: dict[str, Any] = Field(default_factory=dict)


class ModelRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str
    models: list[ModelEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "ModelRegistry":
        ids = [m.id for m in self.models]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate model id(s): {', '.join(duplicates)}")
        if self.get(self.default) is None:
            raise ValueError(f"default model {self.default!r} is not an enabled model in the list")
        return self

    def enabled(self) -> list[ModelEntry]:
        return [m for m in self.models if m.enabled]

    def get(self, model_id: str) -> ModelEntry | None:
        """The enabled model with this id, or None."""
        return next((m for m in self.enabled() if m.id == model_id), None)


def load_registry(path: Path, default_override: str | None = None) -> ModelRegistry:
    """Read and validate models.yaml. Raises ModelsFileError with a readable message on any problem."""
    try:
        raw = yaml.safe_load(path.read_text())
    except OSError as e:
        raise ModelsFileError(f"Can't read models file {path}: {e}") from e
    except yaml.YAMLError as e:
        raise ModelsFileError(f"Models file {path} is not valid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ModelsFileError(f"Models file {path} must be a mapping with `default` and `models`.")
    if default_override:
        raw["default"] = default_override
    try:
        return ModelRegistry.model_validate(raw)
    except ValidationError as e:
        source = f"{path} (default from AGENT_MODEL)" if default_override else str(path)
        raise ModelsFileError(f"Invalid models file {source}:\n{e}") from e
