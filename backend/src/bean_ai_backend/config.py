from pydantic_settings import BaseSettings, SettingsConfigDict


# Reads values from environment variables or backend/.env (AGENT_MODEL=..., etc.)
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    agent_model: str = "deepseek/deepseek-v4.1-flash-1017"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
