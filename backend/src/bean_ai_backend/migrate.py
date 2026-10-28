"""`bean migrate`: apply migrations/NNNN_*.sql in order, once each.

Plain SQL instead of alembic: the schema is small, and every file runs in its own transaction. A Postgres advisory
lock makes concurrent runs (e.g. two pods' initContainers starting together) safe: the second waits, then finds
nothing left to do.
"""

from importlib.resources import files

import asyncpg

# Any constant works; it only has to be the same for every `bean migrate`.
LOCK_ID = 0x6265616E  # "bean"


def plain_url(url: str) -> str:
    """asyncpg wants postgresql://, not SQLAlchemy's postgresql+asyncpg://."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def migration_files() -> list[tuple[str, str]]:
    """[(version, sql)] sorted by file name, e.g. ("0001_gateway", "CREATE TABLE ...")."""
    root = files("bean_ai_backend") / "migrations"
    sql_files = sorted((f for f in root.iterdir() if f.name.endswith(".sql")), key=lambda f: f.name)
    return [(f.name.removesuffix(".sql"), f.read_text()) for f in sql_files]


async def migrate(url: str) -> list[str]:
    """Apply pending migrations and return their versions."""
    conn = await asyncpg.connect(plain_url(url))
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", LOCK_ID)
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        applied: list[str] = []
        for version, sql in migration_files():
            if version in done:
                continue
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", version)
            applied.append(version)
        return applied
    finally:
        await conn.close()
