import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .agent import MissingApiKey, get_agent
from .config import registry, settings
from .registry import Provider
from .store import ChatMessage, Conversation, store

logger = logging.getLogger("bean")

app = FastAPI(title="Bean AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    # Omit (or null) to start a new conversation; the id comes back in the `start` event.
    conversation_id: str | None = None
    # One of the enabled ids from /api/models; omit (or null) for the default.
    model: str | None = None

    @field_validator("model")
    @classmethod
    def _known_model(cls, value: str | None) -> str | None:
        if value is not None and registry.get(value) is None:
            raise ValueError(f"Unknown model {value!r}; see /api/models")
        return value


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


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: Provider
    # Whether the provider's API key is set on the server.
    available: bool


class ModelList(BaseModel):
    default: str
    models: list[ModelInfo]


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": registry.default}


@app.get("/api/models")
async def list_models() -> ModelList:
    return ModelList(
        default=registry.default,
        models=[
            ModelInfo(id=m.id, label=m.label, provider=m.provider, available=bool(settings.api_key(m.provider)))
            for m in registry.enabled()
        ],
    )


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
    model_id = req.model or registry.default

    async def events() -> AsyncIterator[str]:
        yield sse("start", {"conversation_id": conv.id, "model": model_id})
        try:
            agent = get_agent(model_id)
            reply = ""
            async with agent.run_stream(req.message, message_history=conv.history) as result:
                async for delta in result.stream_text(delta=True, debounce_by=None):
                    reply += delta
                    yield sse("delta", {"text": delta})
            # Only completed turns are saved; if the client stops mid-reply, nothing is recorded.
            store.record_turn(conv, req.message, reply, result.all_messages(), model_id)
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
