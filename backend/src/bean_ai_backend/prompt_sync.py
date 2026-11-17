"""Push each agent's instructions to Phoenix as a prompt, so they can be viewed and tried there.

Git is the source of truth: agent/instructions/<id>.md becomes the Phoenix prompt <id>. The
version tagged with ENVIRONMENT (local, production, ...) is the one that environment runs. When the
file's text or the default model differs from that version, a new version is added and the tag
moves to it; otherwise nothing changes. The app itself never reads prompts from Phoenix.

Run on deploy, or by hand: `uv run python -m bean_ai_backend.prompt_sync`.
Fails closed: any agent that can't be synced is logged and the exit code is 1.
"""

import logging
import sys
from typing import Any, Literal

import httpx

from .agent.agent_registry import load_instructions
from .agent.registry import ModelEntry, Provider
from .config import agents, registry, settings

logger = logging.getLogger("bean.prompt_sync")

Outcome = Literal["created", "updated", "unchanged"]

# Phoenix's name for each provider and the invocation parameters it expects. OpenRouter speaks
# the OpenAI API, so its models are recorded as OpenAI models.
PHOENIX_PROVIDERS: dict[Provider, str] = {
    "anthropic": "ANTHROPIC",
    "openrouter": "OPENAI",
}


def _invocation_parameters(model: ModelEntry) -> dict[str, Any]:
    if model.provider == "anthropic":
        # Phoenix requires max_tokens for Anthropic.
        max_tokens = model.settings.get("max_tokens", 8192)
        return {"type": "anthropic", "anthropic": {"max_tokens": max_tokens}}
    return {"type": "openai", "openai": {}}


def sync_prompt(
    client: httpx.Client, agent_id: str, text: str, model: ModelEntry, tag: str
) -> Outcome:
    """Make the version of prompt `agent_id` tagged `tag` hold `text` and `model`."""
    res = client.get(f"/v1/prompts/{agent_id}/tags/{tag}")
    # 404: there's no such prompt yet, or no version has this tag yet.
    if res.status_code == 404:
        current = None
    else:
        res.raise_for_status()
        current = res.json()["data"]
        [message] = current["template"]["messages"]
        if message["content"] == text and current["model_name"] == model.model:
            return "unchanged"

    # Creates the prompt, or adds a version to it if it exists.
    res = client.post(
        "/v1/prompts",
        json={
            "prompt": {"name": agent_id},
            "version": {
                "model_provider": PHOENIX_PROVIDERS[model.provider],
                "model_name": model.model,
                "template_type": "CHAT",
                # NONE: braces in the instructions are text, not template variables.
                "template_format": "NONE",
                "template": {
                    "type": "chat",
                    "messages": [{"role": "system", "content": text}],
                },
                "invocation_parameters": _invocation_parameters(model),
            },
        },
    )
    res.raise_for_status()
    version_id = res.json()["data"]["id"]
    # Adding the tag moves it off the version that had it.
    client.post(
        f"/v1/prompt_versions/{version_id}/tags", json={"name": tag}
    ).raise_for_status()
    return "created" if current is None else "updated"


def sync_prompts(client: httpx.Client, tag: str) -> bool:
    """Sync every agent in agents.yaml. Returns False if any agent failed."""
    model = registry.get(registry.default)
    assert model is not None  # the registry checks its default at load
    ok = True
    for agent_id, text in load_instructions(agents.agents).items():
        try:
            outcome = sync_prompt(client, agent_id, text, model, tag)
        except httpx.HTTPError as e:
            logger.error("Prompt %s: sync failed: %r", agent_id, e)
            ok = False
        else:
            logger.info("Prompt %s (tag %s): %s", agent_id, tag, outcome)
    return ok


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not settings.phoenix_url:
        logger.error("PHOENIX_URL is not set, so there is nowhere to sync prompts to.")
        return 1
    headers = (
        {"Authorization": f"Bearer {settings.phoenix_api_key}"}
        if settings.phoenix_api_key
        else None
    )
    with httpx.Client(
        base_url=settings.phoenix_url, headers=headers, timeout=10
    ) as client:
        return 0 if sync_prompts(client, settings.environment) else 1


if __name__ == "__main__":
    sys.exit(main())
