"""The `bean` command.

bean migrate                                                  # apply database migrations (safe to run concurrently)
bean keys create --service barista --name alice --rpm 30 --budget 5
bean keys list [--service grinder]
bean keys revoke <key_id>
bean usage [--month 2026-10] [--service barista] [--by surface|agent|key|model|day]
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import Database
from .gateway.keys import Service
from .gateway.keystore import create_key, key_to_dict, list_keys, revoke_key
from .gateway.usage import GROUP_BYS, UsageFilter, summarize
from .migrate import migrate


def _database_url() -> str:
    if not settings.database_url:
        sys.exit("DATABASE_URL is not set.")
    return settings.database_url


async def _with_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    db = Database(_database_url())
    try:
        async with db.sessionmaker() as session:
            return await fn(session)
    finally:
        await db.dispose()


def _money(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value}") from exc


def _print_keys(keys: list[dict[str, Any]]) -> None:
    columns = ("key_id", "service", "name", "rpm", "max_tokens_per_request", "monthly_budget_usd", "last_used_at")
    print("  ".join(columns) + "  status")
    for k in keys:
        print("  ".join(str(k[c]) for c in columns) + ("  revoked" if k["revoked_at"] else "  active"))


def cmd_migrate(_: argparse.Namespace) -> None:
    applied = asyncio.run(migrate(_database_url()))
    print(f"applied {', '.join(applied)}" if applied else "database is up to date")


def cmd_keys_create(args: argparse.Namespace) -> None:
    async def run(session: AsyncSession) -> tuple[str, dict[str, Any]]:
        created = await create_key(
            session,
            settings,
            service=Service(args.service),
            name=args.name,
            rpm=args.rpm,
            max_tokens_per_request=args.max_tokens,
            monthly_budget_usd=args.budget,
        )
        return created.plaintext, key_to_dict(created.key)

    try:
        plaintext, key = asyncio.run(_with_session(run))
    except ValueError as exc:
        sys.exit(str(exc))
    print(json.dumps(key, indent=2, ensure_ascii=False))
    print(f"\n{plaintext}\n\nThis is the only time the key is shown. Send it to {key['name']} privately.")


def cmd_keys_list(args: argparse.Namespace) -> None:
    service = Service(args.service) if args.service else None
    keys = asyncio.run(_with_session(lambda s: list_keys(s, service=service)))
    _print_keys([key_to_dict(k) for k in keys])


def cmd_keys_revoke(args: argparse.Namespace) -> None:
    key = asyncio.run(_with_session(lambda s: revoke_key(s, args.key_id)))
    if key is None:
        sys.exit(f"no key {args.key_id}")
    print(f"revoked {key.key_id} ({key.name})")


def cmd_usage(args: argparse.Namespace) -> None:
    flt = UsageFilter(month=args.month, service=args.service)
    try:
        report = asyncio.run(_with_session(lambda s: summarize(s, flt, args.by)))
    except ValueError as exc:
        sys.exit(str(exc))
    print(json.dumps(report, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bean", description="Bean backend admin commands.")
    sub = parser.add_subparsers(required=True, metavar="command")
    services = [s.value for s in Service]

    sub.add_parser("migrate", help="apply database migrations").set_defaults(fn=cmd_migrate)

    keys = sub.add_parser("keys", help="manage barista/grinder API keys").add_subparsers(
        required=True, metavar="action"
    )
    create = keys.add_parser("create", help="create a key (shown once)")
    create.add_argument("--service", required=True, choices=services)
    create.add_argument("--name", required=True, help="who the key is for, e.g. alice")
    create.add_argument("--rpm", type=int, help=f"requests per minute (default {settings.default_rpm})")
    create.add_argument("--budget", type=_money, help=f"monthly USD (default {settings.default_monthly_budget_usd})")
    create.add_argument(
        "--max-tokens", type=int, help=f"max tokens per request (default {settings.default_max_tokens_per_request})"
    )
    create.set_defaults(fn=cmd_keys_create)
    lst = keys.add_parser("list", help="list keys")
    lst.add_argument("--service", choices=services)
    lst.set_defaults(fn=cmd_keys_list)
    revoke = keys.add_parser("revoke", help="revoke a key")
    revoke.add_argument("key_id", help="the key_id, or the key's bar_…/grd_… prefix")
    revoke.set_defaults(fn=cmd_keys_revoke)

    usage = sub.add_parser("usage", help="usage and spend for a month")
    usage.add_argument("--month", nargs="?", help="YYYY-MM (default, or bare --month: this month, UTC)")
    usage.add_argument("--service", choices=services)
    usage.add_argument("--by", choices=GROUP_BYS)
    usage.set_defaults(fn=cmd_usage)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.fn(args)
