"""Create, list and revoke keys. Shared by the CLI and the admin endpoints."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db import ApiKey, utcnow
from .keys import Service, generate_key, hash_key


@dataclass(frozen=True)
class CreatedKey:
    key: ApiKey
    plaintext: str


async def create_key(
    session: AsyncSession,
    settings: Settings,
    *,
    service: Service,
    name: str,
    rpm: int | None = None,
    max_tokens_per_request: int | None = None,
    monthly_budget_usd: Decimal | None = None,
) -> CreatedKey:
    name = name.strip()
    rpm = settings.default_rpm if rpm is None else rpm
    max_tokens = settings.default_max_tokens_per_request if max_tokens_per_request is None else max_tokens_per_request
    budget = settings.default_monthly_budget_usd if monthly_budget_usd is None else monthly_budget_usd
    if not name:
        raise ValueError("name must not be empty")
    if rpm < 1 or max_tokens < 1 or budget < 0:
        raise ValueError("rpm and max tokens must be at least 1, and the budget can't be negative")
    key_id, plaintext = generate_key(service)
    key = ApiKey(
        key_id=key_id,
        service=service.value,
        key_hash=hash_key(plaintext),
        name=name,
        scopes=service.scopes,
        rpm=rpm,
        max_tokens_per_request=max_tokens,
        monthly_budget_usd=budget,
        created_at=utcnow(),
    )
    session.add(key)
    await session.commit()
    return CreatedKey(key=key, plaintext=plaintext)


async def list_keys(session: AsyncSession, *, service: Service | None = None) -> list[ApiKey]:
    stmt = select(ApiKey).order_by(ApiKey.created_at)
    if service is not None:
        stmt = stmt.where(ApiKey.service == service.value)
    return list((await session.execute(stmt)).scalars())


async def find_key(session: AsyncSession, key_id: str) -> ApiKey | None:
    # Accept the bare key_id or a pasted prefix like "bar_abc123def456_…".
    parts = key_id.split("_")
    if len(parts) >= 2 and parts[0] in ("bar", "grd"):
        key_id = parts[1]
    return (await session.execute(select(ApiKey).where(ApiKey.key_id == key_id))).scalar_one_or_none()


async def revoke_key(session: AsyncSession, key_id: str) -> ApiKey | None:
    key = await find_key(session, key_id)
    if key is not None and key.revoked_at is None:
        key.revoked_at = utcnow()
        await session.commit()
    return key


def key_to_dict(key: ApiKey) -> dict[str, Any]:
    def iso(value: Any) -> str | None:
        return value.isoformat() if value else None

    return {
        "key_id": key.key_id,
        "prefix": f"{Service(key.service).key_prefix}_{key.key_id}_…",
        "service": key.service,
        "name": key.name,
        "scopes": key.scopes,
        "rpm": key.rpm,
        "max_tokens_per_request": key.max_tokens_per_request,
        "monthly_budget_usd": str(key.monthly_budget_usd),
        "created_at": iso(key.created_at),
        "last_used_at": iso(key.last_used_at),
        "revoked_at": iso(key.revoked_at),
    }
