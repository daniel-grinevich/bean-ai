from pydantic import BaseModel

from ..agent.registry import Provider


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: Provider
    # Whether the provider's API key is set on the server.
    available: bool


class ModelList(BaseModel):
    default: str
    models: list[ModelInfo]
