"""Monthly spend and usage reports, shared by the HTTP API and the CLI."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import ApiKey, Usage

GROUP_BYS = ("surface", "agent", "key", "model", "service", "day", "status")

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def month_bounds(month: str | None = None) -> tuple[str, datetime, datetime]:
    """(YYYY-MM, start, end) in UTC. ``month`` defaults to the current one."""
    if month is None:
        now = datetime.now(UTC)
        year, mon = now.year, now.month
    else:
        if not _MONTH_RE.match(month):
            raise ValueError("month must be YYYY-MM")
        year, mon = int(month[:4]), int(month[5:])
    start = datetime(year, mon, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC) if mon == 12 else datetime(year, mon + 1, 1, tzinfo=UTC)
    return f"{year:04d}-{mon:02d}", start, end


async def month_spend(session: AsyncSession, *, api_key_id: str | None = None, service: str | None = None) -> Decimal:
    _, start, end = month_bounds()
    stmt = select(func.coalesce(func.sum(Usage.cost_usd), 0)).where(Usage.created_at >= start, Usage.created_at < end)
    if api_key_id is not None:
        stmt = stmt.where(Usage.api_key_id == api_key_id)
    if service is not None:
        stmt = stmt.where(Usage.service == service)
    return Decimal(str((await session.execute(stmt)).scalar_one()))


@dataclass(frozen=True)
class UsageFilter:
    month: str | None = None
    service: str | None = None
    api_key_id: str | None = None


def _group_column(group_by: str) -> Any:
    match group_by:
        case "surface":
            return Usage.surface
        case "agent":
            return Usage.agent_id
        case "key":
            # Bean's in-process calls have no key.
            return func.coalesce(ApiKey.name + literal(" (") + ApiKey.key_id + literal(")"), literal("(internal)"))
        case "model":
            return Usage.model
        case "service":
            return Usage.service
        case "status":
            return Usage.status_code
        case "day":
            return func.date(Usage.created_at)
        case _:
            raise ValueError(f"group by must be one of {', '.join(GROUP_BYS)}")


def _totals(requests: Any, inp: Any, out: Any, cost: Any) -> dict[str, Any]:
    return {
        "requests": int(requests),
        "input_tokens": int(inp),
        "output_tokens": int(out),
        "cost_usd": f"{Decimal(str(cost)):.8f}",
    }


async def summarize(session: AsyncSession, flt: UsageFilter, group_by: str | None = None) -> dict[str, Any]:
    month, start, end = month_bounds(flt.month)
    aggregates = (
        func.count(Usage.id),
        func.coalesce(func.sum(Usage.input_tokens), 0),
        func.coalesce(func.sum(Usage.output_tokens), 0),
        func.coalesce(func.sum(Usage.cost_usd), 0),
    )

    def where(stmt: Any) -> Any:
        stmt = stmt.where(Usage.created_at >= start, Usage.created_at < end)
        if flt.service:
            stmt = stmt.where(Usage.service == flt.service)
        if flt.api_key_id:
            stmt = stmt.where(Usage.api_key_id == flt.api_key_id)
        return stmt

    total = (await session.execute(where(select(*aggregates)))).one()
    result: dict[str, Any] = {"month": month, "totals": _totals(*total)}
    if flt.service:
        result["service"] = flt.service
    if group_by:
        col = _group_column(group_by).label("group")
        stmt = where(select(col, *aggregates).outerjoin(ApiKey, ApiKey.id == Usage.api_key_id))
        stmt = stmt.group_by(col).order_by(func.sum(Usage.cost_usd).desc())
        rows: list[Any] = list((await session.execute(stmt)).all())
        result["group_by"] = group_by
        result["groups"] = [{"group": None if g is None else str(g), **_totals(r, i, o, c)} for g, r, i, o, c in rows]
    return result
