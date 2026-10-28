from decimal import Decimal
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient

from bean_ai_backend.config import settings
from bean_ai_backend.gateway import get_gateway
from bean_ai_backend.gateway.attribution import Attribution
from bean_ai_backend.main import app

from .conftest import BARISTA_HOST, DECISION_BODY, GRINDER_HOST, admin_headers, caller, last_json, make_key

DECIDE = {"state": "We have 3 open bugs and a demo tomorrow.", "questions": {"ship": {"type": "noul"}}}
EMBED = {"input": ["espresso", "latte"]}


def usage_by(client: TestClient, by: str, **params: str) -> dict[str, Any]:
    resp = client.get("/v1/admin/usage", params={"by": by, **params}, headers=admin_headers())
    assert resp.status_code == 200, resp.text
    return {g["group"]: g for g in resp.json()["groups"]}


# --- happy paths ---


def test_decide_forwards_to_openrouter_and_logs_usage(client: TestClient, openrouter: respx.MockRouter) -> None:
    key = make_key(client, "barista")
    resp = client.post("/v1/decide", json=DECIDE, headers=caller(key))
    assert resp.status_code == 200, resp.text
    assert resp.json() == DECISION_BODY
    assert resp.headers["X-Cost-Usd"] == "0.00040000"
    assert Decimal(resp.headers["X-Budget-Remaining-Usd"]) == Decimal("0.9996")

    sent = last_json(openrouter["decide"])
    assert sent["model"] == "perplexity/pplx-decider-flash-v1.2"
    assert sent["provider"] == {"data_collection": "deny"}
    assert sent["user"].startswith("barista:")
    assert sent["questions"] == DECIDE["questions"]

    surfaces = usage_by(client, "surface")
    assert surfaces["slack"]["requests"] == 1
    assert surfaces["slack"]["cost_usd"] == "0.00040000"
    assert usage_by(client, "agent")["alices-bot"]["input_tokens"] == 120


def test_embed_forwards_to_openrouter(client: TestClient, openrouter: respx.MockRouter) -> None:
    key = make_key(client, "grinder")
    resp = client.post("/v1/embed", json=EMBED, headers=caller(key, "internal", "internal"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    sent = last_json(openrouter["embed"])
    assert sent["model"] == "qwen/qwen3-embedding-8b"
    assert sent["input"] == EMBED["input"]
    assert sent["provider"]["data_collection"] == "deny"
    assert usage_by(client, "surface", service="grinder")["internal"]["input_tokens"] == 5


def test_caller_cannot_turn_data_collection_back_on(client: TestClient, openrouter: respx.MockRouter) -> None:
    key = make_key(client, "grinder")
    body = {**EMBED, "provider": {"data_collection": "allow", "order": ["nebius"]}}
    assert client.post("/v1/embed", json=body, headers=caller(key)).status_code == 200
    assert last_json(openrouter["embed"])["provider"] == {"data_collection": "deny", "order": ["nebius"]}


def test_bean_agents_call_in_process(client: TestClient, openrouter: respx.MockRouter) -> None:
    gateway = get_gateway()
    assert gateway is not None
    portal = client.portal
    assert portal is not None

    async def run() -> Any:
        return await gateway.embed({"input": "cortado"}, attribution=Attribution("internal", "ops-agent"))

    result = portal.call(run)
    assert result.body["id"] == "emb-1"
    assert result.budget_remaining_usd is None
    assert openrouter["embed"].call_count == 1
    assert usage_by(client, "key")["(internal)"]["requests"] == 1
    assert "ops-agent" in usage_by(client, "agent")


# --- keys and scopes ---


def test_keys_are_scoped_per_service(client: TestClient) -> None:
    bar, grd = make_key(client, "barista"), make_key(client, "grinder")
    resp = client.post("/v1/embed", json=EMBED, headers=caller(bar))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "wrong_service"
    resp = client.post("/v1/decide", json=DECIDE, headers=caller(grd))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "wrong_service"


@pytest.mark.parametrize(
    ("auth", "code"),
    [
        (None, "missing_api_key"),
        ("Bearer nope", "invalid_api_key"),
        ("Bearer bar_aaaaaaaaaaaa_" + "x" * 43, "invalid_api_key"),
    ],
)
def test_bad_keys_are_401(client: TestClient, auth: str | None, code: str) -> None:
    headers = {"X-AGENT-SURFACE": "internal", "X-AGENT-ID": "internal"}
    if auth:
        headers["Authorization"] = auth
    resp = client.post("/v1/decide", json=DECIDE, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == code


def test_wrong_secret_for_real_key_id_is_401(client: TestClient) -> None:
    key = make_key(client, "barista")
    forged = key[: len("bar_") + 12] + "_" + "y" * 43
    assert client.post("/v1/decide", json=DECIDE, headers=caller(forged)).status_code == 401


def test_revoked_key_stops_working(client: TestClient) -> None:
    key = make_key(client, "barista")
    assert client.post("/v1/decide", json=DECIDE, headers=caller(key)).status_code == 200
    key_id = key.split("_")[1]
    resp = client.post(f"/v1/admin/keys/{key_id}/revoke", headers=admin_headers())
    assert resp.status_code == 200
    assert resp.json()["revoked_at"] is not None
    resp = client.post("/v1/decide", json=DECIDE, headers=caller(key))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "revoked_api_key"


def test_key_is_stored_hashed(client: TestClient) -> None:
    key = make_key(client, "grinder")
    listed = client.get("/v1/admin/keys", headers=admin_headers()).json()
    assert len(listed) == 1
    assert key not in str(listed)
    assert listed[0]["prefix"] == f"grd_{key.split('_')[1]}_…"


# --- attribution headers ---


@pytest.mark.parametrize("missing", ["X-AGENT-SURFACE", "X-AGENT-ID"])
def test_missing_attribution_header_is_400(client: TestClient, missing: str) -> None:
    key = make_key(client, "barista")
    headers = caller(key)
    del headers[missing]
    resp = client.post("/v1/decide", json=DECIDE, headers=headers)
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "missing_header"
    assert error["headers_missing"] == [missing]
    assert missing in error["message"]


def test_invalid_attribution_header_is_400(client: TestClient) -> None:
    key = make_key(client, "grinder")
    resp = client.post("/v1/embed", json=EMBED, headers=caller(key, surface="has spaces"))
    assert resp.status_code == 400
    assert resp.json()["error"]["headers_invalid"] == ["X-AGENT-SURFACE"]


def test_attribution_is_lowercased(client: TestClient) -> None:
    key = make_key(client, "grinder")
    assert client.post("/v1/embed", json=EMBED, headers=caller(key, surface="Slack")).status_code == 200
    assert "slack" in usage_by(client, "surface")


# --- limits ---


def test_rate_limit_is_429(client: TestClient) -> None:
    key = make_key(client, "barista", rpm=1)
    assert client.post("/v1/decide", json=DECIDE, headers=caller(key)).status_code == 200
    resp = client.post("/v1/decide", json=DECIDE, headers=caller(key))
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert int(resp.headers["Retry-After"]) >= 1


def test_max_tokens_per_request_is_413(client: TestClient, openrouter: respx.MockRouter) -> None:
    key = make_key(client, "grinder", max_tokens_per_request=10)
    resp = client.post("/v1/embed", json={"input": "x" * 200}, headers=caller(key))
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "too_many_tokens"
    assert openrouter["embed"].call_count == 0


def test_key_budget_is_402(client: TestClient) -> None:
    # Each call costs $0.0004. The check runs before the call, so the call that crosses the budget still goes through
    # and the next one is refused.
    key = make_key(client, "barista", monthly_budget_usd="0.0003")
    assert client.post("/v1/decide", json=DECIDE, headers=caller(key)).status_code == 200
    resp = client.post("/v1/decide", json=DECIDE, headers=caller(key))
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "budget_exceeded"
    # Rejections are logged too.
    statuses = usage_by(client, "status")
    assert statuses["200"]["requests"] == 1
    assert statuses["402"]["requests"] == 1


def test_service_cap_is_402(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    alice, bob = make_key(client, "barista", monthly_budget_usd="5"), make_key(client, "barista")
    monkeypatch.setattr(settings, "barista_monthly_cap_usd", Decimal("0.0003"))
    assert client.post("/v1/decide", json=DECIDE, headers=caller(alice)).status_code == 200
    resp = client.post("/v1/decide", json=DECIDE, headers=caller(bob))
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "service_budget_exceeded"


def test_model_allow_list(client: TestClient) -> None:
    key = make_key(client, "barista")
    resp = client.post("/v1/decide", json={**DECIDE, "model": "openai/gpt-5"}, headers=caller(key))
    assert resp.status_code == 400
    assert resp.json()["error"]["allowed_models"] == ["perplexity/pplx-decider-flash-v1.2"]


# --- upstream errors ---


@pytest.mark.parametrize(
    ("upstream", "status", "code"),
    [(400, 400, "upstream_rejected"), (402, 502, "upstream_auth"), (429, 503, "upstream_rate_limited")],
)
def test_upstream_errors_are_mapped(
    client: TestClient, openrouter: respx.MockRouter, upstream: int, status: int, code: str
) -> None:
    openrouter["embed"].respond(upstream, json={"error": {"message": "nope"}})
    key = make_key(client, "grinder")
    resp = client.post("/v1/embed", json=EMBED, headers=caller(key))
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code


# --- host-based exposure ---


def test_barista_host_only_exposes_decide(client: TestClient) -> None:
    host = {"Host": BARISTA_HOST}
    key = make_key(client, "barista")
    assert client.post("/v1/decide", json=DECIDE, headers=caller(key) | host).status_code == 200
    assert client.get("/health", headers=host).status_code == 200
    assert client.get("/v1/usage", headers=caller(key) | host).status_code == 200
    for method, path in [
        ("POST", "/v1/embed"),
        ("GET", "/api/conversations"),
        ("POST", "/api/chat"),
        ("GET", "/api/health"),
        ("GET", "/v1/admin/keys"),
        ("GET", "/docs"),
    ]:
        resp = client.request(method, path, headers=admin_headers() | host)
        assert resp.status_code == 404, path
        assert resp.json()["error"]["code"] == "not_found"


def test_grinder_host_only_exposes_embed(client: TestClient) -> None:
    host = {"Host": f"{GRINDER_HOST}:443"}
    grd, bar = make_key(client, "grinder"), make_key(client, "barista")
    assert client.post("/v1/embed", json=EMBED, headers=caller(grd) | host).status_code == 200
    assert client.post("/v1/decide", json=DECIDE, headers=caller(bar) | host).status_code == 404
    assert client.get("/api/conversations", headers=host).status_code == 404
    # A barista key can't read its usage through grinder's hostname.
    assert client.get("/v1/usage", headers=caller(bar) | host).status_code == 403


def test_forwarded_host_can_only_narrow_access(client: TestClient) -> None:
    resp = client.get("/api/conversations", headers={"Host": BARISTA_HOST, "X-Forwarded-Host": "bean.example"})
    assert resp.status_code == 404
    resp = client.get("/api/conversations", headers={"X-Forwarded-Host": GRINDER_HOST})
    assert resp.status_code == 404


def test_bean_host_keeps_chat_api_and_its_error_format(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200
    resp = client.get("/api/conversations/missing")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Conversation not found"}


def test_gateway_can_be_switched_off_on_bean_host(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    key = make_key(client, "barista")
    monkeypatch.setattr(settings, "gateway_on_bean_host", False)
    assert client.post("/v1/decide", json=DECIDE, headers=caller(key)).status_code == 404
    assert client.post("/v1/decide", json=DECIDE, headers=caller(key) | {"Host": BARISTA_HOST}).status_code == 200
    assert client.get("/api/health").status_code == 200


# --- usage and admin ---


def test_own_usage_report(client: TestClient) -> None:
    key = make_key(client, "barista")
    client.post("/v1/decide", json=DECIDE, headers=caller(key, "slack", "bot-a"))
    client.post("/v1/decide", json=DECIDE, headers=caller(key, "cli", "bot-a"))
    other = make_key(client, "barista")
    client.post("/v1/decide", json=DECIDE, headers=caller(other, "web", "bot-b"))

    resp = client.get("/v1/usage", params={"by": "surface"}, headers=caller(key))
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["totals"]["requests"] == 2
    assert {g["group"] for g in report["groups"]} == {"slack", "cli"}
    assert report["key"]["service"] == "barista"


def test_admin_requires_token(client: TestClient) -> None:
    assert client.get("/v1/admin/keys").status_code == 401
    assert client.get("/v1/admin/keys", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_admin_disabled_without_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "barista_admin_token", "")
    assert client.get("/v1/admin/keys", headers=admin_headers()).status_code == 503


def test_admin_rejects_bad_key_settings(client: TestClient) -> None:
    resp = client.post("/v1/admin/keys", json={"service": "barista", "name": "x", "rpm": 0}, headers=admin_headers())
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_gateway_off_without_database(configure: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_url", "")
    with TestClient(app) as c:
        resp = c.post("/v1/decide", json=DECIDE, headers=caller("bar_x"))
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "gateway_not_configured"
        assert c.get("/api/health").status_code == 200
