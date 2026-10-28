from bean_ai_backend.config import Settings
from bean_ai_backend.db import async_url
from bean_ai_backend.gateway.hosts import allowed, host_services
from bean_ai_backend.gateway.keys import Service, generate_key, hash_key, parse_key, verify_key
from bean_ai_backend.gateway.ratelimit import RateLimiter
from bean_ai_backend.gateway.usage import month_bounds
from bean_ai_backend.migrate import migration_files


def test_key_round_trip() -> None:
    key_id, plaintext = generate_key(Service.GRINDER)
    assert plaintext.startswith(f"grd_{key_id}_")
    parsed = parse_key(plaintext)
    assert parsed is not None
    assert parsed.service is Service.GRINDER
    assert parsed.key_id == key_id
    assert verify_key(plaintext, hash_key(plaintext))
    assert not verify_key(plaintext + "x", hash_key(plaintext))
    assert parse_key("sk-or-v1-abc") is None


def test_rate_limiter_refills() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    assert limiter.try_acquire("k", 2) is None
    assert limiter.try_acquire("k", 2) is None
    wait = limiter.try_acquire("k", 2)
    assert wait is not None and 29 < wait <= 30
    now[0] = 30.0
    assert limiter.try_acquire("k", 2) is None


def test_host_lists_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BARISTA_HOSTS", "Barista.tailf9a785.ts.net, barista-staging.tailf9a785.ts.net")
    monkeypatch.setenv("GRINDER_HOSTS", "grinder.tailf9a785.ts.net")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.barista_hosts == ["barista.tailf9a785.ts.net", "barista-staging.tailf9a785.ts.net"]
    assert host_services(s, ["barista-staging.tailf9a785.ts.net:443"]) == {"barista"}
    assert host_services(s, ["bean.tailf9a785.ts.net"]) == set()
    assert allowed(s, {"barista"}, "/v1/decide")
    assert not allowed(s, {"barista"}, "/v1/embed")
    # Both at once (conflicting headers): only the harmless common paths.
    assert not allowed(s, {"barista", "grinder"}, "/v1/decide")
    assert allowed(s, {"barista", "grinder"}, "/health")


def test_month_bounds() -> None:
    month, start, end = month_bounds("2026-12")
    assert month == "2026-12"
    assert (start.year, start.month, end.year, end.month) == (2026, 12, 2027, 1)


def test_async_url() -> None:
    assert async_url("postgresql://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
    assert async_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"


def test_migrations_are_packaged() -> None:
    versions = [v for v, _ in migration_files()]
    assert versions[0] == "0001_gateway"
    assert versions == sorted(versions)
