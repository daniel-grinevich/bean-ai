from decimal import Decimal
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    return value


# Reads values from environment variables or backend/.env (AGENT_MODEL=..., OPEN_ROUTER_KEY=...).
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Any OpenRouter model id. DeepSeek is the default (and the only model we have a key for).
    agent_model: str = "deepseek/deepseek-v4.1-flash-1017"
    open_router_key: str = Field(default="", repr=False)
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- barista (decisions) / grinder (embeddings) gateway, see gateway/ ---

    # Postgres, e.g. postgresql://bean:...@localhost:5445/bean. Empty = gateway off (chat still works).
    database_url: str = Field(default="", repr=False)
    # Bearer token for /v1/admin/*. Empty = admin endpoints off.
    barista_admin_token: str = Field(default="", repr=False)

    # Hostnames (comma-separated) that only expose one service. Requests for any other host are "bean's own host".
    barista_hosts: Annotated[list[str], NoDecode] = []
    grinder_hosts: Annotated[list[str], NoDecode] = []
    # Whether /v1/decide, /v1/embed and /v1/usage also answer on bean's own host (handy for local dev).
    gateway_on_bean_host: bool = True

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # The Decisions endpoint lives outside /api/v1.
    openrouter_decisions_url: str = "https://openrouter.ai/api/alpha/decisions"
    # Forced onto every upstream gateway request ("deny" = only providers that don't store or train on prompts).
    # Set to "" to stop sending it.
    openrouter_data_collection: str = "deny"
    upstream_timeout_s: float = 60.0
    upstream_max_retries: int = 2
    upstream_backoff_base_s: float = 0.5

    # Model allow-lists (comma-separated); the first entry is the default.
    barista_models: Annotated[list[str], NoDecode] = ["perplexity/pplx-decider-flash-v1.2"]
    grinder_models: Annotated[list[str], NoDecode] = ["qwen/qwen3-embedding-8b"]

    # Global monthly caps per service in USD, protecting the OpenRouter bill. 0 = no cap.
    barista_monthly_cap_usd: Decimal = Decimal(20)
    grinder_monthly_cap_usd: Decimal = Decimal(20)

    # Defaults for new keys.
    default_rpm: int = 30
    default_max_tokens_per_request: int = 8000
    default_monthly_budget_usd: Decimal = Decimal(1)

    # Used when neither OpenRouter's usage.cost nor the model catalogue has a price. Pessimistic on purpose.
    fallback_price_per_mtok_usd: Decimal = Decimal(1)
    pricing_ttl_s: int = 6 * 3600
    max_embed_inputs: int = 256

    @field_validator("barista_hosts", "grinder_hosts", mode="before")
    @classmethod
    def _hosts(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("barista_models", "grinder_models", mode="before")
    @classmethod
    def _models(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()
