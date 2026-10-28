from functools import cache

from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from .config import settings

INSTRUCTIONS = """\
You are Bean, the operations assistant for Navi, a platform that runs a fleet of smart coffee machines.
You help ops staff with machine status, sales, maintenance and locations.

You are not connected to live Navi data yet (the Navi MCP server and the crumb analytics warehouse come later).
Never invent machine names, numbers or statuses. If a question needs live data, say so plainly and explain
what you would look up once connected; you can still help with general questions, SQL, and explanations.

Format replies in Markdown. Use tables for tabular data and fenced code blocks with a language tag for code.
Keep answers short and practical.
"""


class MissingApiKey(RuntimeError):
    pass


# Built on first use so the server can start (and /api/health works) before a key is configured.
@cache
def get_agent() -> Agent[None, str]:
    if not settings.open_router_key:
        raise MissingApiKey("OPEN_ROUTER_KEY is not set, so Bean can't reach the model.")
    model = OpenRouterModel(
        settings.agent_model,
        provider=OpenRouterProvider(api_key=settings.open_router_key, app_title="Bean AI"),
    )
    # Tools go here later, e.g. `@agent.tool_plain` functions that call the Navi MCP server.
    return Agent(model, instructions=INSTRUCTIONS)
