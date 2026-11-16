from dataclasses import dataclass

from ..repos import RepoSource


@dataclass
class AgentDeps:
    """What one run brings with it, as `ctx.deps` in tools. Built per chat turn, not per server.

    The cached agents are shared by everyone, so anything that differs per user or conversation
    (which repository, later who is asking) goes here rather than into the agent.
    """

    repo: RepoSource | None = None
