from pydantic_ai.capabilities import AbstractCapability

from .engineering import RepoFiles

# Our capabilities that agents.yaml can name, on top of Pydantic AI's built-ins.
CAPABILITY_TYPES: list[type[AbstractCapability[None]]] = [RepoFiles]
