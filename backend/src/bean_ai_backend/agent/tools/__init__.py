from pydantic_ai.capabilities import AbstractCapability

from ..deps import AgentDeps
from .engineering import RepoFiles

# Our capabilities that agents.yaml can name, on top of Pydantic AI's built-ins.
CAPABILITY_TYPES: list[type[AbstractCapability[AgentDeps]]] = [RepoFiles]
