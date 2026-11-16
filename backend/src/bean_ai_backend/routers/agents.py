from fastapi import APIRouter

from ..config import agents
from ..schemas.agents import AgentInfo, AgentList

router = APIRouter()


@router.get("/agents")
async def list_agents() -> AgentList:
    return AgentList(
        default=agents.default,
        agents=[
            AgentInfo(
                id=agent_id,
                description=str(entry.description) if entry.description else None,
            )
            for agent_id, entry in agents.agents.items()
        ],
    )
