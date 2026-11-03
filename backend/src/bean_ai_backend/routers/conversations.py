from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response

from ..deps import StoreDep
from ..schemas.conversations import ChatMessage, ConversationDetail, ConversationSummary
from ..services.store import ConversationNotFound

router = APIRouter()


@router.get("/conversations")
async def list_conversations(store: StoreDep) -> list[ConversationSummary]:
    return [
        ConversationSummary(id=c.id, title=c.title, updated_at=c.updated_at, message_count=len(c.messages))
        for c in store.all()
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, store: StoreDep) -> ConversationDetail:
    try:
        c = store.require(conversation_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    messages = [ChatMessage(**asdict(m)) for m in c.messages]
    return ConversationDetail(id=c.id, title=c.title, updated_at=c.updated_at, messages=messages)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, store: StoreDep) -> Response:
    if not store.delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)
