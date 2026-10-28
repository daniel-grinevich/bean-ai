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

- Backend env: `OPEN_ROUTER_KEY` (required), `AGENT_MODEL` (optional), `DATABASE_URL` and the other
  barista/grinder settings (see `backend/.env.example`). No `.env` is baked into the image. Run `bean migrate` before
  a new version starts (it's on the image's `PATH`).
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
| `DATABASE_URL`    | backend  | (none)                               | Postgres for barista/grinder.           |
| `BARISTA_ADMIN_TOKEN` | backend | (none)                           | Enables `/v1/admin/*`.                  |
| `BARISTA_HOSTS`, `GRINDER_HOSTS` | backend | (none)              | Comma-separated hostnames per service.  |
| `GATEWAY_ON_BEAN_HOST` | backend | `true`                         | Gateway endpoints on bean's own host.   |
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

## barista and grinder (for friends and internal apps)

Bean also serves two OpenRouter model endpoints that other people and apps call with **their own keys**:

| Service     | Endpoint          | Upstream                                  | Default model                         | Key prefix |
| ----------- | ----------------- | ----------------------------------------- | ------------------------------------- | ---------- |
| **barista** | `POST /v1/decide` | OpenRouter Decisions API                  | `perplexity/pplx-decider-flash-v1.2`  | `bar_…`    |
| **grinder** | `POST /v1/embed`  | OpenRouter `/embeddings`                  | `qwen/qwen3-embedding-8b`             | `grd_…`    |

A `bar_` key only works on `/v1/decide` and a `grd_` key only on `/v1/embed`. Keys are shown once, stored as a
sha256 hash, and can be revoked. Each key has a requests-per-minute limit, a max tokens per request and a monthly USD
budget; each service also has a global monthly cap. Every request (rejections included) is logged to the `usage`
table with the caller's surface and agent id. `data_collection: deny` is always sent to OpenRouter (callers can't
turn it off). The code is in `backend/src/bean_ai_backend/gateway/`.

### Calling them (send this to friends)

Every call needs your key plus two headers saying where the call comes from (`X-AGENT-SURFACE`, e.g. `slack`, `cli`,
`web`) and which app or agent made it (`X-AGENT-ID`). Both are 1-64 characters of `[a-z0-9._-]`; internal callers
can send `internal` for both.

```sh
# barista: ask a decision model
curl https://barista.tailf9a785.ts.net/v1/decide \
  -H "Authorization: Bearer $BARISTA_KEY" \
  -H "X-AGENT-SURFACE: cli" -H "X-AGENT-ID: alices-script" \
  -H "Content-Type: application/json" \
  -d '{
        "state": "We have 3 open bugs, one is a crash on login. The demo is tomorrow at 10.",
        "questions": {"ship": {"type": "noul", "instructions": "Should we demo the current build?"}}
      }'

# grinder: embed one or more strings
curl https://grinder.tailf9a785.ts.net/v1/embed \
  -H "Authorization: Bearer $GRINDER_KEY" \
  -H "X-AGENT-SURFACE: web" -H "X-AGENT-ID: alices-search" \
  -H "Content-Type: application/json" \
  -d '{"input": ["flat white", "cortado"]}'

# what you've spent this month, by surface (or agent, model, day)
curl "https://barista.tailf9a785.ts.net/v1/usage?by=surface" -H "Authorization: Bearer $BARISTA_KEY"
```

Use the `-staging` hostnames (`barista-staging…`, `grinder-staging…`) for staging. Request bodies are OpenRouter's:
`/v1/decide` takes `{state, questions, model?, assets?, session_id?}` (question types: `noul`, `choice`, `score`,
`box`; see OpenRouter's Decisions API docs) and returns `{id, answers, usage, …}`;
`/v1/embed` takes `{input, model?, dimensions?, …}` and returns `{data: [{embedding}], usage}`. `model` is optional
and must be on the allow-list. Successful responses carry `X-Cost-Usd` and `X-Budget-Remaining-Usd` headers.

Errors are JSON, `{"error": {"code": "...", "message": "..."}}`:

| Status | `code`                                                           | Meaning                                                    |
| ------ | ---------------------------------------------------------------- | ---------------------------------------------------------- |
| 400    | `missing_header`, `invalid_header`, `model_not_allowed`          | Fix the request. The message names the header.             |
| 401    | `missing_api_key`, `invalid_api_key`, `revoked_api_key`          | Key missing, wrong or revoked.                             |
| 403    | `wrong_service`                                                  | A `grd_` key on barista or a `bar_` key on grinder.        |
| 413    | `too_many_tokens`                                                | Bigger than your key's max tokens per request.             |
| 429    | `rate_limited`                                                   | Over your requests/minute; wait `Retry-After` seconds.     |
| 402    | `budget_exceeded`, `service_budget_exceeded`                     | Your monthly budget (or the service's cap) is used up. Resets on the 1st (UTC). |
| 502/503 | `upstream_*`                                                    | OpenRouter had a problem; retry later.                     |

### Hostnames

`BARISTA_HOSTS` and `GRINDER_HOSTS` list the hostnames that route to bean-backend for each service. On a barista
host only `/v1/decide`, `/v1/usage` and `/health` answer; on a grinder host only `/v1/embed`, `/v1/usage` and
`/health`. Everything else, including bean's chat API and the admin API, is a 404 there. Any other hostname is bean's
own: the chat API works as before, and the gateway endpoints answer too unless `GATEWAY_ON_BEAN_HOST=false`.

### Running it locally

```sh
docker compose up -d                 # Postgres on localhost:5445 (repo root)
cd backend
# in backend/.env: DATABASE_URL=postgresql://bean:bean@localhost:5445/bean
uv run bean migrate                  # create/upgrade the tables (safe to run concurrently)
uv run bean keys create --service barista --name alice --rpm 30 --budget 5
```

Without `DATABASE_URL` bean runs as before and `/v1/*` answers 503.

### Managing keys

```sh
bean keys create --service barista|grinder --name alice [--rpm 30] [--budget 5] [--max-tokens 8000]
bean keys list [--service grinder]
bean keys revoke <key_id>                       # or paste the bar_…/grd_… prefix
bean usage --month [2026-10] [--service barista] [--by surface|agent|key|model|day]
```

In the cluster, run them in the backend pod (`kubectl exec deploy/bean-backend -- bean keys list`). The same
operations are available over HTTP on bean's own host with `Authorization: Bearer $BARISTA_ADMIN_TOKEN`:
`POST /v1/admin/keys` (`{service, name, rpm?, max_tokens_per_request?, monthly_budget_usd?}`, returns `api_key`
once), `GET /v1/admin/keys[?service=]`, `POST /v1/admin/keys/{key_id}/revoke`, and
`GET /v1/admin/usage?month=&service=&key=&by=`.

### From bean's own agents

Agents call the services in-process (same client, pricing and usage log, no HTTP hop and no key; the service's
monthly cap still applies):

```python
from bean_ai_backend.gateway import get_gateway
from bean_ai_backend.gateway.attribution import Attribution

gateway = get_gateway()  # None when DATABASE_URL isn't set
result = await gateway.embed({"input": ["latte"]}, attribution=Attribution("internal", "ops-agent"))
result.body["data"][0]["embedding"]
```

### Tests

`uv run pytest` (OpenRouter is mocked; SQLite by default). Set `TEST_DATABASE_URL` to an empty Postgres to run them
against the real migrations, as CI does. Also `uv run ruff check . && uv run ruff format --check . && uv run pyright`.

## Where things live

**Backend** (`backend/src/bean_ai_backend/`)

- `agent.py`: the agent's instructions and model. Add tools with `@agent.tool_plain` (or `@agent.tool` if a tool needs `RunContext`).
- `main.py`: the routes; `/api/chat` streams with `agent.run_stream(...)` and `stream_text(delta=True)`.
- `store.py`: the in-memory conversation store (Pydantic AI message history + display messages).
- `config.py`: settings from env vars / `backend/.env`.
- `gateway/`: barista and grinder (routes, host routing, keys, limits, pricing, usage, OpenRouter client).
- `db.py` + `migrations/*.sql`: the Postgres tables (`api_keys`, `usage`), applied by `migrate.py` (`bean migrate`).
- `cli.py`: the `bean` command.

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

| Tag                | Example            | Image tags pushed                                | rainbow-road change                                                                | ArgoCD      |
| ------------------ | ------------------ | ------------------------------------------------ | ---------------------------------------------------------------------------------- | ----------- |
| `staging` (moving) | `staging`          | `staging-latest`, `staging-<sha7>`               | `staging/bean/kustomization.yaml`: `navi.dev/deployed-sha: "<sha7>"`               | auto-sync   |
| `vX.Y.Z`           | `v0.2.0`           | `X.Y.Z`, the tag name, `prod-latest`             | `production/bean/kustomization.yaml`: both `newTag`s set to `X.Y.Z`                | manual Sync |

**Staging** has no versions: it deploys whatever commit the single `staging` tag points at (move it with a force-push).
It always runs `staging-latest`; its `newTag` never changes. To roll the pods onto the fresh image, CI rewrites
the pod-template annotation `navi.dev/deployed-sha` in the staging overlay (any one-line
`navi.dev/deployed-sha: <value>` entry, e.g. in a Deployment patch or `commonAnnotations`). The changed spec makes
ArgoCD roll the Deployments, and `imagePullPolicy: Always` pulls the new `staging-latest`. `staging-<sha7>` is
pushed only for traceability. If the overlay has no such annotation, the deploy fails rather than
silently not rolling. **Production** is pinned to the version tag.

```sh
git switch production && git pull
git tag -f staging && git push -f origin staging               # staging (moves the tag)
git tag v0.2.0 && git push origin v0.2.0                       # production (then Sync in ArgoCD)
```

CI (lint, format check, type-check/build, backend install + import + tests when `backend/tests/` exists, and a
no-push Docker build of both images) runs on every PR and push to `production`. The manifest commit needs the
`RAINBOW_ROAD_PAT` repo secret (contents: write on rainbow-road).
