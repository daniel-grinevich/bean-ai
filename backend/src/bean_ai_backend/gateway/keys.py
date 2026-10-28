"""The two services and their API keys.

A key looks like ``bar_<key_id>_<secret>`` (barista) or ``grd_<key_id>_<secret>`` (grinder). The prefix says which
service it works on, ``key_id`` is a public lookup id stored in clear, and only the sha256 of the whole key is stored,
so a leaked database can't be replayed.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from ..config import Settings


class Service(StrEnum):
    BARISTA = "barista"  # OpenRouter Decisions API, POST /v1/decide
    GRINDER = "grinder"  # OpenRouter embeddings, POST /v1/embed

    @property
    def key_prefix(self) -> str:
        return "bar" if self is Service.BARISTA else "grd"

    @property
    def scope(self) -> str:
        """The scope that unlocks this service's model endpoint."""
        return "decide" if self is Service.BARISTA else "embed"

    @property
    def scopes(self) -> list[str]:
        return [self.scope, "usage"]

    def models(self, settings: Settings) -> list[str]:
        return settings.barista_models if self is Service.BARISTA else settings.grinder_models

    def monthly_cap(self, settings: Settings) -> Decimal:
        return settings.barista_monthly_cap_usd if self is Service.BARISTA else settings.grinder_monthly_cap_usd


_KEY_RE = re.compile(r"^(?P<prefix>bar|grd)_(?P<key_id>[a-z0-9]{12})_(?P<secret>[A-Za-z0-9_-]{32,64})$")
_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


@dataclass(frozen=True)
class ParsedKey:
    service: Service
    key_id: str


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def verify_key(plaintext: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_key(plaintext), key_hash)


def generate_key(service: Service) -> tuple[str, str]:
    """Return (key_id, plaintext)."""
    key_id = "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))
    return key_id, f"{service.key_prefix}_{key_id}_{secrets.token_urlsafe(32)}"


def parse_key(plaintext: str) -> ParsedKey | None:
    match = _KEY_RE.match(plaintext)
    if not match:
        return None
    service = Service.BARISTA if match["prefix"] == "bar" else Service.GRINDER
    return ParsedKey(service=service, key_id=match["key_id"])
