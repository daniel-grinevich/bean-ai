from typing import Annotated

from fastapi import Depends

from .services.store import ConversationStore, store


def get_store() -> ConversationStore:
    return store


StoreDep = Annotated[ConversationStore, Depends(get_store)]
