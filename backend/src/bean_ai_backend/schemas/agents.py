from pydantic import BaseModel


class AgentInfo(BaseModel):
    id: str
    # What the agent is for, from agents.yaml; for people picking an agent.
    description: str | None


class AgentList(BaseModel):
    default: str
    agents: list[AgentInfo]
