"""Runs a real AnthropicModel request through Pydantic AI's message mapping and the anthropic SDK,
with the HTTP layer faked. Catches SDK/Pydantic AI version mismatches (like anthropic 2.4 turning
BetaMessageParam into a Union that pydantic-ai 2.59 tried to instantiate) without a network call."""

import json

import httpx2
import pytest
from anthropic import AsyncAnthropic
from pydantic_ai import Agent, models
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from bean_ai_backend.agent import INSTRUCTIONS
from bean_ai_backend.config import registry


def sse_body(text: str) -> bytes:
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
        *[
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": f"{word} "}},
            )
            for word in text.split()
        ],
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


# Async tests run on the anyio pytest plugin (anyio is already a dependency).
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def requests_seen(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    return []


async def test_claude_turns_round_trip_through_the_sdk(requests_seen: list[dict]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        requests_seen.append(json.loads(request.content))
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse_body("hello from claude")
        )

    client = AsyncAnthropic(
        api_key="test-key", http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)), max_retries=0
    )
    entry = registry.get("claude-sonnet-5")
    model = AnthropicModel(entry.model, provider=AnthropicProvider(anthropic_client=client), settings=entry.settings)
    agent = Agent(model, instructions=INSTRUCTIONS)

    # Same calls as /api/chat; the second turn sends history, so assistant messages get mapped too.
    history = []
    for prompt in ["hi", "and again"]:
        reply = ""
        async with agent.run_stream(prompt, message_history=history) as result:
            async for delta in result.stream_text(delta=True, debounce_by=None):
                reply += delta
        history = result.all_messages()
        assert reply.strip() == "hello from claude"

    assert len(requests_seen) == 2
    body = requests_seen[1]
    assert body["model"] == "claude-sonnet-5"
    assert body["stream"] is True
    assert body["max_tokens"] == 8192
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
