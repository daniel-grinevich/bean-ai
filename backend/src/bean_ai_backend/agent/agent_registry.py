from collections.abc import Container, Iterable
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
        if self.instructions is not None:
            raise ValueError(
                "`instructions` can't be set here: they live in agent/instructions/<id>.md"
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


# Ships inside the package, so it's the same file in a checkout and in the image.
AGENTS_FILE = Path(__file__).with_name("agents.yaml")


def load_agents(default_override: str | None = None) -> AgentRegistry:
    """Read and validate agents.yaml. Raises AgentsFileError with a readable message on any problem."""
    try:
        raw = yaml.safe_load(AGENTS_FILE.read_text())
    except OSError as e:
        raise AgentsFileError(f"Can't read agents file {AGENTS_FILE}: {e}") from e
    except yaml.YAMLError as e:
        raise AgentsFileError(
            f"Agents file {AGENTS_FILE} is not valid YAML: {e}"
        ) from e
    if not isinstance(raw, dict):
        raise AgentsFileError(
            f"Agents file {AGENTS_FILE} must be a mapping with `default` and `agents`."
        )
    if default_override:
        raw["default"] = default_override
    try:
        return AgentRegistry.model_validate(raw)
    except ValidationError as e:
        source = (
            f"{AGENTS_FILE} (default from DEFAULT_AGENT)"
            if default_override
            else AGENTS_FILE
        )
        raise AgentsFileError(f"Invalid agents file {source}:\n{e}") from e


# One file per agent, named by its id: instructions/bean.md, instructions/senior-dev-daniel.md, ...
INSTRUCTIONS_DIR = Path(__file__).with_name("instructions")


def load_instructions(agent_ids: Iterable[str]) -> dict[str, str]:
    """Read each agent's instructions file. Raises AgentsFileError naming any that are missing or empty."""
    instructions: dict[str, str] = {}
    missing: list[str] = []
    for agent_id in agent_ids:
        path = INSTRUCTIONS_DIR / f"{agent_id}.md"
        text = path.read_text() if path.is_file() else ""
        if text.strip():
            instructions[agent_id] = text
        else:
            missing.append(f"{agent_id}.md")
    if missing:
        raise AgentsFileError(
            f"Missing or empty instructions in {INSTRUCTIONS_DIR}: {', '.join(missing)}"
        )
    return instructions
