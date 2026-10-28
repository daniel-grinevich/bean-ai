from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Reads values from environment variables or backend/.env (AGENT_MODEL=..., OPEN_ROUTER_KEY=...).
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Any OpenRouter model id. DeepSeek is the default (and the only model we have a key for).
    agent_model: str = "deepseek/deepseek-v4.1-flash-1017"
    open_router_key: str = Field(default="", repr=False)
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
