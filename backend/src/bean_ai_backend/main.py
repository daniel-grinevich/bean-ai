import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import MissingApiKey, get_agent
from .config import settings
from .db import Database
from .gateway.core import Gateway, set_gateway
from .gateway.errors import install_handlers
from .gateway.hosts import HostRoutingMiddleware
from .gateway.routes import router as gateway_router
from .store import ChatMessage, Conversation, store

logger = logging.getLogger("bean")


# The barista/grinder gateway needs Postgres; without DATABASE_URL bean runs as before and /v1/* answers 503.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    gateway = Gateway(settings, Database(settings.database_url)) if settings.database_url else None
    app.state.gateway = gateway
    set_gateway(gateway)
    try:
        yield
    finally:
        set_gateway(None)
        if gateway is not None:
            await gateway.aclose()


app = FastAPI(title="Bean AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added last so it runs first: barista/grinder hostnames never reach bean's chat API.
app.add_middleware(HostRoutingMiddleware, settings=settings)
install_handlers(app)
app.include_router(gateway_router)


# Plain liveness check, also the only non-/v1 path on the barista and grinder hostnames.
@app.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    # Omit (or null) to start a new conversation; the id comes back in the `start` event.
    conversation_id: str | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime
    message_count: int


class ConversationDetail(BaseModel):
    id: str
    title: str
    updated_at: datetime
    messages: list[ChatMessage]


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.agent_model}


@app.get("/api/conversations")
async def list_conversations() -> list[ConversationSummary]:
    return [
        ConversationSummary(id=c.id, title=c.title, updated_at=c.updated_at, message_count=len(c.messages))
        for c in store.all()
    ]


def _get_or_404(conversation_id: str) -> Conversation:
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> ConversationDetail:
    c = _get_or_404(conversation_id)
    return ConversationDetail(id=c.id, title=c.title, updated_at=c.updated_at, messages=c.messages)


@app.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str) -> Response:
    if not store.delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)


def sse(event: str, data: dict) -> str:
    """Format one server-sent event: `event: <name>` plus a JSON `data:` line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# Streams the reply as server-sent events: start → delta… → done, or error.
@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    conv = _get_or_404(req.conversation_id) if req.conversation_id else store.create(req.message)

    async def events() -> AsyncIterator[str]:
        yield sse("start", {"conversation_id": conv.id})
        try:
            agent = get_agent()
            reply = ""
            async with agent.run_stream(req.message, message_history=conv.history) as result:
                async for delta in result.stream_text(delta=True, debounce_by=None):
                    reply += delta
                    yield sse("delta", {"text": delta})
            # Only completed turns are saved; if the client stops mid-reply, nothing is recorded.
            store.record_turn(conv, req.message, reply, result.all_messages())
            yield sse("done", {})
        except MissingApiKey as e:
            yield sse("error", {"message": str(e)})
        except Exception:
            logger.exception("chat run failed (conversation %s)", conv.id)
            yield sse("error", {"message": "The model request failed. Check the server logs and try again."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Stop proxies (nginx, etc.) from buffering the stream.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
