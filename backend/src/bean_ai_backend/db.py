"""Postgres tables (SQLAlchemy 2, async). The schema itself is created by `bean migrate` (migrations/*.sql);
these models must match it. Conversations still live in memory (store.py) and can move here later."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(14, 8)


def utcnow() -> datetime:
    return datetime.now(UTC)


def async_url(url: str) -> str:
    """Accept a plain postgres:// URL (what Infisical/psql use) and pick the asyncpg driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


class Base(DeclarativeBase):
    pass


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Public lookup id embedded in the key: bar_<key_id>_<secret>.
    key_id: Mapped[str] = mapped_column(String(32), unique=True)
    service: Mapped[str] = mapped_column(String(16))
    # sha256 hex of the full key. The plaintext is shown once and never stored.
    key_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list[str]] = mapped_column(JSON)
    rpm: Mapped[int] = mapped_column(Integer)
    max_tokens_per_request: Mapped[int] = mapped_column(Integer)
    monthly_budget_usd: Mapped[Decimal] = mapped_column(MONEY)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Usage(Base):
    """One row per gateway request, rejections included."""

    __tablename__ = "usage"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    # None for bean's own in-process calls.
    api_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id"))
    service: Mapped[str] = mapped_column(String(16))
    endpoint: Mapped[str] = mapped_column(String(64))
    surface: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    # "openrouter" (usage.cost), "pricing" (catalogue), "fallback", or "none" (rejected before upstream).
    cost_source: Mapped[str] = mapped_column(String(16), default="none")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status_code: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    upstream_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(async_url(url), pool_pre_ping=True)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()
