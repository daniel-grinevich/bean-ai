import logging
from collections.abc import AsyncIterator
from typing import Any

from ..agent.factory import MissingApiKey, get_agent
from .store import Conversation, ConversationStore

logger = logging.getLogger("bean")

# One streamed event: its name (start, delta, done or error) and its JSON payload.
Event = tuple[str, dict[str, Any]]


def open_conversation(store: ConversationStore, conversation_id: str | None, message: str) -> Conversation:
    """The conversation to continue, or a new one titled from the first message. Raises ConversationNotFound."""
    return store.require(conversation_id) if conversation_id else store.create(message)


# Runs one turn: start → delta… → done, or error.
async def run_turn(store: ConversationStore, conv: Conversation, message: str, model_id: str) -> AsyncIterator[Event]:
    yield "start", {"conversation_id": conv.id, "model": model_id}
    try:
        agent = get_agent(model_id)
        reply = ""
        async with agent.run_stream(message, message_history=conv.history) as result:
            async for delta in result.stream_text(delta=True, debounce_by=None):
                reply += delta
                yield "delta", {"text": delta}
        # Only completed turns are saved; if the client stops mid-reply, nothing is recorded.
        store.record_turn(conv, message, reply, result.all_messages(), model_id)
        yield "done", {}
    except MissingApiKey as e:
        yield "error", {"message": str(e)}
    except Exception:
        logger.exception("chat run failed (conversation %s)", conv.id)
        yield "error", {"message": "The model request failed. Check the server logs and try again."}
