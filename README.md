# Bean AI

An agent built with FastAPI + [Pydantic AI](https://ai.pydantic.dev) and a Vue 3 + TypeScript frontend.

```
backend/   FastAPI app, Pydantic AI agent (uv)
frontend/  Vue 3 + Vite chat UI
```

## Run it

**Backend** (port 8000):

```sh
cd backend
cp .env.example .env   # add your ANTHROPIC_API_KEY
uv run uvicorn bean_ai_backend.main:app --reload --app-dir src
```

**Frontend** (port 5173, proxies `/api` to the backend):

```sh
cd frontend
npm run dev
```

## Where things live

- `backend/src/bean_ai_backend/agent.py`: the agent's instructions and tools. Add tools with `@agent.tool_plain` (or `@agent.tool` if a tool needs `RunContext`).
- `backend/src/bean_ai_backend/main.py`: `POST /api/chat` streams the reply as server-sent events (`start`, `delta`, `done`, `error`). Conversation history is kept in memory.
- `frontend/src/api.ts`: client for the SSE stream.
- `frontend/src/App.vue`: chat UI.

The model is set by `AGENT_MODEL` (default `anthropic:claude-opus-5`). Any Pydantic AI model string works.
