from uuid import uuid4
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings

app = FastAPI(title="Bean AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    chat_id: str


# Example route. Visit http://localhost:8000/api/health once the server is running,
# and http://localhost:8000/docs for the auto-generated API docs.
@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# TODO 2: Write POST /api/chat.
# Step A (start here): take a ChatRequest, run the agent, return the reply as JSON.
#   Hint: `from .agent import agent`, then `result = await agent.run(req.message)`
#   and `result.output` is the reply text.
#
# Step B (later): remember history per conversation_id.
#   Hint: `result.all_messages()` and `agent.run(..., message_history=...)`.
#
# Step C (later): stream the reply so the Vue UI types it out live.
#   The frontend expects Server-Sent Events: `event: start|delta|done|error`.
#   Hint: look up FastAPI's StreamingResponse and Pydantic AI's `agent.run_stream`.


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, str]:
    chat_id = req.chat_id or uuid4().hex

    result = await agent.run(req.message)

    if result.output:
        return {"message": result.output, "chat_id": chat_id}
    else:
        return {"error": result.error, "chat_id": chat_id}
