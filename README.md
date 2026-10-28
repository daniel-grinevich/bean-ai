# Bean AI

Bean is the ops assistant for the Navi coffee-machine platform. It's a FastAPI + [Pydantic AI](https://ai.pydantic.dev)
backend talking to **DeepSeek via OpenRouter**, plus a Vue 3 chat UI. Later it will connect to the Navi MCP server
(live operations) and to crumb (the ETL/analytics warehouse). For now it has no live data and says so.

```
backend/   FastAPI app + Pydantic AI agent (uv, Python 3.13)
frontend/  Vue 3 + Vite + TypeScript chat UI (npm)
```

> The hand-written learning version of the backend is preserved in the initial commit (`60935c7`) for reference:
> `git show 60935c7:backend/src/bean_ai_backend/main.py`.

## Run it

**Backend** (port 8000):

```sh
cd backend
cp .env.example .env          # set OPEN_ROUTER_KEY
uv run uvicorn bean_ai_backend.main:app --reload --app-dir src
```

**Frontend** (port 5173, proxies `/api` to the backend):

```sh
cd frontend
npm install
npm run dev
```

Use other ports with env vars, e.g. backend on 8010 and UI on 5197:

```sh
uv run uvicorn bean_ai_backend.main:app --reload --app-dir src --port 8010
VITE_API_TARGET=http://localhost:8010 VITE_PORT=5197 npm run dev
```

**No API key?** `npm run mock` starts a fake backend on :8010 that streams canned replies (with a table and code;
include the word "error" in a message to see the error state). Point the UI at it with `VITE_API_TARGET`.

## Containers

| Image                                      | Built from            | Serves                                                         |
| ------------------------------------------ | --------------------- | -------------------------------------------------------------- |
| `ghcr.io/daniel-grinevich/bean-ai-backend`  | `backend/Dockerfile`  | uvicorn on **:8000** as non-root uid 10001; health at `/api/health` |
| `ghcr.io/daniel-grinevich/bean-ai-frontend` | `frontend/Dockerfile` | nginx on **:80**: the static build, SPA fallback, `/api` proxied to `BACKEND_URL` |

```sh
docker build -t ghcr.io/daniel-grinevich/bean-ai-backend:dev backend
docker build -t ghcr.io/daniel-grinevich/bean-ai-frontend:dev frontend

docker network create bean
docker run -d --network bean --network-alias bean-backend \
  -e OPEN_ROUTER_KEY=... -e AGENT_MODEL=deepseek/deepseek-v4.1-flash-1017 \
  ghcr.io/daniel-grinevich/bean-ai-backend:dev
docker run -d --network bean -p 8080:80 ghcr.io/daniel-grinevich/bean-ai-frontend:dev   # http://localhost:8080
```

- Backend env: `OPEN_ROUTER_KEY` (required), `AGENT_MODEL` (optional). No `.env` is baked into the image.
- Frontend env: `BACKEND_URL` (default `http://bean-backend:8000`, **no trailing slash**), rendered into the nginx
  config at start. nginx resolves that host when it starts, so the backend Service/DNS name must exist.
  Proxy buffering is off for `/api` so streamed replies arrive live. `/healthz` is a cheap liveness check.
- History is in memory, so run **one backend replica** (or add a shared store) or conversations will scatter.

## Configuration

| Variable          | Where    | Default                              | Notes                                   |
| ----------------- | -------- | ------------------------------------ | --------------------------------------- |
| `OPEN_ROUTER_KEY` | backend  | (none)                               | Required for real replies.              |
| `AGENT_MODEL`     | backend  | `deepseek/deepseek-v4.1-flash-1017`  | Any OpenRouter model id.                |
| `CORS_ORIGINS`    | backend  | `["http://localhost:5173"]`          | Only needed when not using a proxy.     |
| `VITE_API_TARGET` | frontend | `http://localhost:8000`              | Dev proxy target for `/api`.            |
| `VITE_PORT`       | frontend | `5173`                               | Dev server port.                        |

## API

| Method   | Path                        | Notes                                                                     |
| -------- | --------------------------- | ------------------------------------------------------------------------- |
| `GET`    | `/api/health`               | `{"status": "ok", "model": "<AGENT_MODEL>"}`                              |
| `POST`   | `/api/chat`                 | Body `{"message", "conversation_id"?}`. Streams SSE (see below).          |
| `GET`    | `/api/conversations`        | `[{id, title, updated_at, message_count}]`, newest first.                 |
| `GET`    | `/api/conversations/{id}`   | `{id, title, updated_at, messages: [{role, content}]}`, or 404.           |
| `DELETE` | `/api/conversations/{id}`   | 204, or 404.                                                              |

`POST /api/chat` streams server-sent events: `start` `{"conversation_id"}`, then `delta` `{"text"}` for each
chunk, then `done` `{}`. Failures arrive as `error` `{"message"}`. Leave out `conversation_id` to start a new
conversation. History is kept **in memory** (lost on restart). Only completed turns are saved, so a reply
stopped mid-stream isn't remembered.

## Where things live

**Backend** (`backend/src/bean_ai_backend/`)

- `agent.py`: the agent's instructions and model. Add tools with `@agent.tool_plain` (or `@agent.tool` if a tool needs `RunContext`).
- `main.py`: the routes; `/api/chat` streams with `agent.run_stream(...)` and `stream_text(delta=True)`.
- `store.py`: the in-memory conversation store (Pydantic AI message history + display messages).
- `config.py`: settings from env vars / `backend/.env`.

**Frontend** (`frontend/src/`)

| Concern                        | Library                                                                      | Where                                          |
| ------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------- |
| Styling                        | Tailwind CSS v4 (`@tailwindcss/vite`)                                        | `style.css`                                    |
| Components                     | [shadcn-vue](https://shadcn-vue.com) (reka-ui); add more with `npx shadcn-vue@latest add <name>` | `components/ui/` (generated), `components.json` |
| Routing                        | vue-router: `/` and `/c/:conversationId`                                     | `router.ts`                                    |
| Server state                   | `@tanstack/vue-query` (conversations, health, send/delete mutations; the stream writes into the cache) | `queries.ts`, `api.ts`                         |
| Client/UI state                | Pinia (current conversation, stream, sidebar, theme, drafts)                 | `stores/`                                      |
| Composer + settings forms      | `@tanstack/vue-form` + zod (`zod/mini`)                                      | `components/chat/ChatComposer.vue`, `components/SettingsDialog.vue` |
| Message list                   | `@tanstack/vue-virtual`                                                      | `components/chat/MessageList.vue`              |
| Tables in replies              | `@tanstack/vue-table` (markdown tables and ```json row arrays → sortable table) | `components/DataTable.vue`, `lib/markdown.ts`  |
| Keyboard shortcuts             | `@tanstack/vue-hotkeys`                                                      | `App.vue`, `ChatComposer.vue`                  |
| Stream render throttle, draft debounce | `@tanstack/vue-pacer`                                                | `MarkdownContent.vue`, `ChatComposer.vue`      |
| Markdown + code highlighting   | markdown-it + Shiki (lazy-loaded)                                            | `lib/markdown.ts`                              |
| Toasts                         | vue-sonner (shadcn `sonner`)                                                 | `App.vue`                                      |

Shortcuts: <kbd>Enter</kbd> send, <kbd>Shift</kbd>+<kbd>Enter</kbd> newline, <kbd>Esc</kbd> stop streaming,
<kbd>⌘/Ctrl</kbd>+<kbd>K</kbd> new chat, <kbd>/</kbd> focus the composer, <kbd>⌘/Ctrl</kbd>+<kbd>B</kbd> toggle the
sidebar. Settings can switch sending to <kbd>⌘/Ctrl</kbd>+<kbd>Enter</kbd>.

### Frontend scripts

| Script                  | What it does                          |
| ----------------------- | ------------------------------------- |
| `npm run dev`           | Vite dev server                       |
| `npm run build`         | Type-check (vue-tsc) + production build |
| `npm run type-check`    | vue-tsc only                          |
| `npm run lint` / `lint:fix` | ESLint (flat config, Vue + TS)    |
| `npm run format` / `format:check` | Prettier                    |
| `npm run mock`          | Fake SSE backend on :8010             |
| `npm run preview`       | Serve the production build            |

## Deploying

Deploys are tag-driven (`.github/workflows/`). Tag a commit that is already on `production`; any other commit is
refused. Each deploy builds `ghcr.io/daniel-grinevich/bean-ai-backend` and `bean-ai-frontend` (linux/arm64), pushes
them to GHCR, then commits `deploy bean <env>: <sha|version>` to
[rainbow-road](https://github.com/daniel-grinevich/rainbow-road).

| Tag               | Example            | Image tags pushed                                | rainbow-road change                                                                | ArgoCD      |
| ----------------- | ------------------ | ------------------------------------------------ | ---------------------------------------------------------------------------------- | ----------- |
| `vX.Y.Z-staging*` | `v0.2.0-staging.1` | `staging-latest`, `staging-<sha7>`, the tag name | `staging/bean/kustomization.yaml`: `navi.dev/deployed-sha: "<sha7>"`               | auto-sync   |
| `vX.Y.Z`          | `v0.2.0`           | `X.Y.Z`, the tag name, `prod-latest`             | `production/bean/kustomization.yaml`: both `newTag`s set to `X.Y.Z`                | manual Sync |

**Staging always runs `staging-latest`**; its `newTag` never changes. To roll the pods onto the fresh image, CI rewrites
the pod-template annotation `navi.dev/deployed-sha` in the staging overlay (any one-line
`navi.dev/deployed-sha: <value>` entry, e.g. in a Deployment patch or `commonAnnotations`). The changed spec makes
ArgoCD roll the Deployments, and `imagePullPolicy: Always` pulls the new `staging-latest`. `staging-<sha7>` and the
tag name are pushed only for traceability. If the overlay has no such annotation, the deploy fails rather than
silently not rolling. **Production** is pinned to the version tag.

```sh
git switch production && git pull
git tag v0.2.0-staging.1 && git push origin v0.2.0-staging.1   # staging
git tag v0.2.0 && git push origin v0.2.0                       # production (then Sync in ArgoCD)
```

CI (lint, format check, type-check/build, backend install + import + tests when `backend/tests/` exists, and a
no-push Docker build of both images) runs on every PR and push to `production`. The manifest commit needs the
`RAINBOW_ROAD_PAT` repo secret (contents: write on rainbow-road).
