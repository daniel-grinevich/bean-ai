from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    cors_origins: list[str] = ["http://localhost:5173"]

    def api_key(self, provider: Provider) -> str:
        return {"anthropic": self.anthropic_api_key, "openrouter": self.open_router_key}[provider]


settings = Settings()
# Loaded at import so a bad models file stops the server at startup instead of on the first chat.
registry = load_registry(settings.models_file, settings.agent_model)
