import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..config import registry
from ..deps import StoreDep
from ..schemas.chat import ChatRequest
from ..services.chat import open_conversation, run_turn
from ..services.store import ConversationNotFound

router = APIRouter()


def sse(event: str, data: dict) -> str:
    """Format one server-sent event: `event: <name>` plus a JSON `data:` line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# Streams the reply as server-sent events (see services.chat.run_turn for the sequence).
@router.post("/chat")
async def chat(req: ChatRequest, store: StoreDep) -> StreamingResponse:
    try:
        conv = open_conversation(store, req.conversation_id, req.message)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    turn = run_turn(store, conv, req.message, req.model or registry.default)
    return StreamingResponse(
        (sse(event, data) async for event, data in turn),
        media_type="text/event-stream",
        # Stop proxies (nginx, etc.) from buffering the stream.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
