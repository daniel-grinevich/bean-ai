from pydantic import BaseModel, Field, field_validator

from ..config import agents, registry


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    # Omit (or null) to start a new conversation; the id comes back in the `start` event.
    conversation_id: str | None = None
    # One of the enabled ids from /api/models; omit (or null) for the default.
    model: str | None = None
    # One of the ids from /api/agents; omit (or null) for the default.
    agent: str | None = None

    @field_validator("model")
    @classmethod
    def _known_model(cls, value: str | None) -> str | None:
        if value is not None and registry.get(value) is None:
            raise ValueError(f"Unknown model {value!r}; see /api/models")
        return value

    @field_validator("agent")
    @classmethod
    def _known_agent(cls, value: str | None) -> str | None:
        if value is not None and agents.get(value) is None:
            raise ValueError(f"Unknown agent {value!r}; see /api/agents")
        return value
