from collections.abc import Container
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_ai import AgentSpec


class AgentsFileError(RuntimeError):
    pass


class AgentEntry(AgentSpec):
    """One agent in agents.yaml: Pydantic AI's own agent spec, without `model` (models.yaml has those)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _no_model(self) -> "AgentEntry":
        if self.model is not None:
            raise ValueError(
                "`model` can't be set here: the model is picked per chat from models.yaml"
            )
        return self


class AgentRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str
    agents: dict[str, AgentEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "AgentRegistry":
        if self.default not in self.agents:
            raise ValueError(
                f"default agent {self.default!r} is not one of: {', '.join(self.agents)}"
            )
        return self

    def get(self, agent_id: str) -> AgentEntry | None:
        return self.agents.get(agent_id)

    def check_capabilities(self, known: Container[str]) -> None:
        """Raise AgentsFileError if an agent names a capability that isn't in `known`."""
        unknown = [
            f"{agent_id}: {cap.name}"
            for agent_id, entry in self.agents.items()
            for cap in entry.capabilities
            if cap.name not in known
        ]
        if unknown:
            raise AgentsFileError(
                f"Unknown capabilities in the agents file: {', '.join(unknown)}"
            )


def load_agents(path: Path, default_override: str | None = None) -> AgentRegistry:
    """Read and validate agents.yaml. Raises AgentsFileError with a readable message on any problem."""
    try:
        raw = yaml.safe_load(path.read_text())
    except OSError as e:
        raise AgentsFileError(f"Can't read agents file {path}: {e}") from e
    except yaml.YAMLError as e:
        raise AgentsFileError(f"Agents file {path} is not valid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise AgentsFileError(
            f"Agents file {path} must be a mapping with `default` and `agents`."
        )
    if default_override:
        raw["default"] = default_override
    try:
        return AgentRegistry.model_validate(raw)
    except ValidationError as e:
        source = (
            f"{path} (default from DEFAULT_AGENT)" if default_override else str(path)
        )
        raise AgentsFileError(f"Invalid agents file {source}:\n{e}") from e
