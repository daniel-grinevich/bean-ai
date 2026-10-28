"""HTTP routes: /v1/decide (barista), /v1/embed (grinder), /v1/usage, and /v1/admin/* behind BARISTA_ADMIN_TOKEN."""

import hmac
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..config import settings
from .attribution import read_attribution
from .core import Gateway, Result
from .errors import ApiError
from .keys import Service
from .keystore import create_key, find_key, key_to_dict, list_keys, revoke_key
from .usage import GROUP_BYS, UsageFilter, summarize

router = APIRouter(prefix="/v1")


def get_gateway(request: Request) -> Gateway:
    gateway: Gateway | None = getattr(request.app.state, "gateway", None)
    if gateway is None:
        raise ApiError(503, "gateway_not_configured", "DATABASE_URL is not set, so barista and grinder are off.")
    return gateway


GatewayDep = Annotated[Gateway, Depends(get_gateway)]


class DecideRequest(BaseModel):
    """OpenRouter Decisions request. Extra fields (assets, session_id, ...) are passed through."""

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    state: Any
    questions: dict[str, Any] = Field(min_length=1)


class EmbedRequest(BaseModel):
    """OpenAI-style embeddings request. Extra fields (dimensions, encoding_format, ...) are passed through."""

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    input: str | list[str] = Field(min_length=1)


def _response(result: Result) -> JSONResponse:
    headers = {"X-Cost-Usd": f"{result.cost_usd:.8f}"}
    if result.budget_remaining_usd is not None:
        headers["X-Budget-Remaining-Usd"] = f"{result.budget_remaining_usd:.6f}"
    return JSONResponse(result.body, headers=headers)


@router.post("/decide")
async def decide(body: DecideRequest, request: Request, gateway: GatewayDep) -> JSONResponse:
    key = await gateway.authenticate(request.headers, Service.BARISTA)
    attribution = read_attribution(request.headers)
    return _response(await gateway.decide(body.model_dump(exclude_none=True), key=key, attribution=attribution))


@router.post("/embed")
async def embed(body: EmbedRequest, request: Request, gateway: GatewayDep) -> JSONResponse:
    key = await gateway.authenticate(request.headers, Service.GRINDER)
    attribution = read_attribution(request.headers)
    return _response(await gateway.embed(body.model_dump(exclude_none=True), key=key, attribution=attribution))


UsageGroup = Literal["surface", "agent", "model", "day", "status"]


@router.get("/usage")
async def own_usage(
    request: Request,
    gateway: GatewayDep,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    by: UsageGroup | None = None,
) -> dict[str, Any]:
    """This month's usage for the calling key."""
    host_services: set[str] = getattr(request.state, "host_services", set())
    # On a barista host only barista keys count, and the same for grinder.
    service = Service(next(iter(host_services))) if len(host_services) == 1 else None
    key = await gateway.authenticate(request.headers, service)
    if "usage" not in key.scopes:
        raise ApiError(403, "insufficient_scope", "This key lacks the 'usage' scope.")
    async with gateway.db.sessionmaker() as session:
        report = await _summarize(session, UsageFilter(month=month, api_key_id=key.id), by)
    return {"key": key_to_dict(key), **report}


async def _summarize(session: Any, flt: UsageFilter, by: str | None) -> dict[str, Any]:
    try:
        return await summarize(session, flt, by)
    except ValueError as exc:
        raise ApiError(400, "invalid_request", str(exc)) from exc


# --- admin ---


def require_admin(request: Request) -> None:
    if not settings.barista_admin_token:
        raise ApiError(503, "admin_disabled", "BARISTA_ADMIN_TOKEN is not set, so the admin API is off.")
    auth = request.headers.get("authorization") or ""
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(token.encode(), settings.barista_admin_token.encode()):
        raise ApiError(401, "invalid_admin_token", "Send 'Authorization: Bearer <BARISTA_ADMIN_TOKEN>'.")


admin = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    service: Service
    name: str = Field(min_length=1, max_length=128)
    rpm: int | None = Field(default=None, ge=1)
    max_tokens_per_request: int | None = Field(default=None, ge=1)
    monthly_budget_usd: Decimal | None = Field(default=None, ge=0)


@admin.post("/keys", status_code=201)
async def admin_create_key(body: CreateKeyRequest, gateway: GatewayDep) -> dict[str, Any]:
    """Create a key. The response is the only time the full key is shown."""
    async with gateway.db.sessionmaker() as session:
        created = await create_key(
            session,
            gateway.settings,
            service=body.service,
            name=body.name,
            rpm=body.rpm,
            max_tokens_per_request=body.max_tokens_per_request,
            monthly_budget_usd=body.monthly_budget_usd,
        )
    return {"api_key": created.plaintext, **key_to_dict(created.key)}


@admin.get("/keys")
async def admin_list_keys(gateway: GatewayDep, service: Service | None = None) -> list[dict[str, Any]]:
    async with gateway.db.sessionmaker() as session:
        return [key_to_dict(k) for k in await list_keys(session, service=service)]


@admin.post("/keys/{key_id}/revoke")
async def admin_revoke_key(key_id: str, gateway: GatewayDep) -> dict[str, Any]:
    async with gateway.db.sessionmaker() as session:
        key = await revoke_key(session, key_id)
    if key is None:
        raise ApiError(404, "not_found", f"No key '{key_id}'.")
    return key_to_dict(key)


@admin.get("/usage")
async def admin_usage(
    gateway: GatewayDep,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    service: Service | None = None,
    key: str | None = None,
    by: Annotated[str | None, Query(description=f"One of {', '.join(GROUP_BYS)}")] = None,
) -> dict[str, Any]:
    """Usage across all keys (and bean's own calls), optionally for one service or key, grouped."""
    async with gateway.db.sessionmaker() as session:
        api_key_id = None
        if key is not None:
            found = await find_key(session, key)
            if found is None:
                raise ApiError(404, "not_found", f"No key '{key}'.")
            api_key_id = found.id
        flt = UsageFilter(month=month, service=service.value if service else None, api_key_id=api_key_id)
        return await _summarize(session, flt, by)


router.include_router(admin)
