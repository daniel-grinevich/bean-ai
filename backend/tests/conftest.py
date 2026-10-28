"""Gateway test fixtures. OpenRouter is mocked with respx.

The database is SQLite by default. Set TEST_DATABASE_URL to a disposable Postgres (CI does) to run the same tests
against the real migrations instead: every table is emptied before each test.
"""

import asyncio
import json
import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from bean_ai_backend.config import settings
from bean_ai_backend.db import Base, async_url
from bean_ai_backend.main import app
from bean_ai_backend.migrate import migrate

ADMIN_TOKEN = "test-admin-token"
BARISTA_HOST = "barista-staging.example.ts.net"
GRINDER_HOST = "grinder-staging.example.ts.net"
DECISIONS_URL = "https://openrouter.test/api/alpha/decisions"
EMBEDDINGS_URL = "https://openrouter.test/api/v1/embeddings"

DECISION_BODY = {
    "id": "dec-1",
    "model": "perplexity/pplx-decider-flash-v1.2",
    "answers": {"ship": {"type": "noul", "noul": "yes"}},
    "usage": {"input_tokens": 120, "output_tokens": 8, "cost": 0.0004},
}
EMBEDDING_BODY = {
    "id": "emb-1",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
    "usage": {"prompt_tokens": 5, "total_tokens": 5, "cost": 0.00001},
}


async def _reset_postgres(url: str) -> None:
    await migrate(url)
    engine = create_async_engine(async_url(url))
    async with engine.begin() as conn:
        await conn.exec_driver_sql("TRUNCATE usage, api_keys RESTART IDENTITY CASCADE")
    await engine.dispose()


async def _create_sqlite(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        asyncio.run(_reset_postgres(url))
        return url
    url = f"sqlite+aiosqlite:///{tmp_path / 'bean.db'}"
    asyncio.run(_create_sqlite(url))
    return url


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    values: dict[str, Any] = {
        "database_url": database_url,
        "open_router_key": "sk-or-test",
        "barista_admin_token": ADMIN_TOKEN,
        "barista_hosts": [BARISTA_HOST],
        "grinder_hosts": [GRINDER_HOST],
        "gateway_on_bean_host": True,
        "openrouter_base_url": "https://openrouter.test/api/v1",
        "openrouter_decisions_url": DECISIONS_URL,
        "openrouter_data_collection": "deny",
        "upstream_max_retries": 0,
        "upstream_backoff_base_s": 0.0,
        "barista_monthly_cap_usd": Decimal(20),
        "grinder_monthly_cap_usd": Decimal(20),
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


@pytest.fixture
def openrouter() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith="https://openrouter.test/api/v1/models").respond(json={"data": []})
        router.get("https://openrouter.test/api/v1/embeddings/models").respond(json={"data": []})
        router.post(DECISIONS_URL, name="decide").respond(json=DECISION_BODY)
        router.post(EMBEDDINGS_URL, name="embed").respond(json=EMBEDDING_BODY)
        yield router


@pytest.fixture
def client(configure: None, openrouter: respx.MockRouter) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def make_key(client: TestClient, service: str, **limits: Any) -> str:
    resp = client.post("/v1/admin/keys", json={"service": service, "name": "alice", **limits}, headers=admin_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


def caller(key: str, surface: str = "slack", agent: str = "alices-bot") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "X-AGENT-SURFACE": surface, "X-AGENT-ID": agent}


def last_json(route: respx.Route) -> dict[str, Any]:
    request: httpx.Request = route.calls.last.request
    return json.loads(request.content)
