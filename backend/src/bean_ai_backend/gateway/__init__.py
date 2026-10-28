"""barista (decisions) and grinder (embeddings): OpenRouter endpoints that friends and internal apps call with their
own per-service API keys. Bean's agents can call them in-process with `get_gateway()`."""

from .core import Gateway, Result, get_gateway
from .keys import Service

__all__ = ["Gateway", "Result", "Service", "get_gateway"]
