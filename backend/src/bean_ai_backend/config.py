from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .agent.agent_registry import load_agents
from .agent.registry import Provider, load_registry


# Reads values from environment variables or backend/.env (ANTHROPIC_API_KEY=..., OPEN_ROUTER_KEY=...).
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = Field(default="", repr=False)
    open_router_key: str = Field(default="", repr=False)
    # The model list (see models.yaml). Relative paths resolve from the working directory, like .env.
    models_file: Path = Path("models.yaml")
    # Optional override of the default model in models.yaml; must be one of its enabled ids.
    agent_model: str | None = None
    # Optional override of the default agent in agents.yaml; must be one of its ids.
    default_agent: str | None = None
    cors_origins: list[str] = ["http://localhost:5173"]
    # OTLP/HTTP collector for traces, e.g. Phoenix at http://localhost:6006 (/v1/traces is
    # appended). Unset: the server runs normally and sends no traces.
    otel_exporter_otlp_endpoint: str = ""
    # Sent as `Authorization: Bearer <key>`; needed when Phoenix has auth on.
    phoenix_api_key: str = Field(default="", repr=False)
    # Where this server runs; tags every trace.
    environment: Literal["local", "staging", "production"] = "local"

    def api_key(self, provider: Provider) -> str:
        return {
            "anthropic": self.anthropic_api_key,
            "openrouter": self.open_router_key,
        }[provider]


settings = Settings()
# Loaded at import so a bad models or agents file stops the server at startup instead of on the first chat.
registry = load_registry(settings.models_file, settings.agent_model)
agents = load_agents(settings.default_agent)
