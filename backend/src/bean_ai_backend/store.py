from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


@dataclass
class Conversation:
    id: str
    title: str
    updated_at: datetime
    # What the agent needs to continue the conversation (includes tool calls, etc.).
    history: list[ModelMessage] = field(default_factory=list)
    # What the UI shows: just the user/assistant text.
    messages: list[ChatMessage] = field(default_factory=list)


def _title(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 60 else text[:57] + "…"


# In-memory only: everything is lost when the process restarts. Swap for a database later.
class ConversationStore:
    def __init__(self) -> None:
        self._items: dict[str, Conversation] = {}

    def create(self, first_message: str) -> Conversation:
        conv = Conversation(id=uuid4().hex, title=_title(first_message), updated_at=datetime.now(UTC))
        self._items[conv.id] = conv
        return conv

    def get(self, conversation_id: str) -> Conversation | None:
        return self._items.get(conversation_id)

    def all(self) -> list[Conversation]:
        return sorted(self._items.values(), key=lambda c: c.updated_at, reverse=True)

    def delete(self, conversation_id: str) -> bool:
        return self._items.pop(conversation_id, None) is not None

    def record_turn(self, conv: Conversation, user: str, reply: str, history: list[ModelMessage]) -> None:
        conv.history = history
        conv.messages += [ChatMessage(role="user", content=user), ChatMessage(role="assistant", content=reply)]
        conv.updated_at = datetime.now(UTC)


store = ConversationStore()
