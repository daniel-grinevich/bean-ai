from functools import cache
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.agent.spec import get_capability_registry
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings

from ..config import agents, registry, settings
from .errors import AgentUnavailable
from .instructions import INSTRUCTIONS
from .registry import KEY_ENV_VARS, ModelEntry
from .tools import CAPABILITY_TYPES

# Checked at import, so a misspelled capability or an agent without instructions stops the server
# at startup.
agents.check_capabilities(get_capability_registry(CAPABILITY_TYPES))
agents.check_instructions(INSTRUCTIONS)


class MissingApiKey(AgentUnavailable):
    pass


def build_model(entry: ModelEntry) -> Model:
    key = settings.api_key(entry.provider)
    if not key:
        raise MissingApiKey(
            f"{KEY_ENV_VARS[entry.provider]} is not set, so Bean can't reach {entry.label}."
        )
    model_settings = cast(ModelSettings, entry.settings)
    if entry.provider == "anthropic":
        return AnthropicModel(
            entry.model,
            provider=AnthropicProvider(api_key=key),
            settings=model_settings,
        )
    return OpenRouterModel(
        entry.model,
        provider=OpenRouterProvider(api_key=key, app_title="Bean AI"),
        settings=model_settings,
    )


# One Agent per (agent, model) pair, built on first use so the server can start (and /api/health works)
# without keys. AgentUnavailable (a missing key, an unset REPO_ROOT) raises before caching, so fixing the
# setting and restarting is all it takes.
@cache
def get_agent(agent_id: str, model_id: str) -> Agent[None, str]:
    agent_entry = agents.get(agent_id)
    if agent_entry is None:
        raise KeyError(agent_id)
    model_entry = registry.get(model_id)
    if model_entry is None:
        raise KeyError(model_id)
    model = build_model(model_entry)
    try:
        agent = Agent.from_spec(
            agent_entry,
            model=model,
            name=agent_id,
            instructions=INSTRUCTIONS[agent_id],
            custom_capability_types=CAPABILITY_TYPES,
        )
    except ValueError as e:
        # Pydantic AI wraps errors raised while building a capability; re-raise ours so the user sees the reason.
        if isinstance(e.__cause__, AgentUnavailable):
            raise e.__cause__ from None
        raise
    return cast(Agent[None, str], agent)
