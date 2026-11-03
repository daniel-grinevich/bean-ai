from functools import cache
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings

from ..config import registry, settings
from .instructions import INSTRUCTIONS
from .registry import KEY_ENV_VARS, ModelEntry


class MissingApiKey(RuntimeError):
    pass


def build_model(entry: ModelEntry) -> Model:
    key = settings.api_key(entry.provider)
    if not key:
        raise MissingApiKey(f"{KEY_ENV_VARS[entry.provider]} is not set, so Bean can't reach {entry.label}.")
    model_settings = cast(ModelSettings, entry.settings)
    if entry.provider == "anthropic":
        return AnthropicModel(entry.model, provider=AnthropicProvider(api_key=key), settings=model_settings)
    return OpenRouterModel(
        entry.model,
        provider=OpenRouterProvider(api_key=key, app_title="Bean AI"),
        settings=model_settings,
    )


# One agent per model, built on first use so the server can start (and /api/health works) without keys.
# A missing key raises before caching, so setting it later and restarting is all it takes.
@cache
def get_agent(model_id: str) -> Agent[None, str]:
    entry = registry.get(model_id)
    if entry is None:
        raise KeyError(model_id)
    # Tools go here later, e.g. `@agent.tool_plain` functions that call the Navi MCP server.
    return Agent(build_model(entry), instructions=INSTRUCTIONS)
