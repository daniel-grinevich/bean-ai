from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    # Which model id answered (assistant messages only).
    model: str | None = None


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
