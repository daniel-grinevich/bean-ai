"""X-AGENT-SURFACE / X-AGENT-ID: where a call comes from and which app or agent made it, for usage reports.

They are not auth (the API key is). Internal callers can send "internal" for both.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import ApiError

SURFACE_HEADER = "X-AGENT-SURFACE"
AGENT_HEADER = "X-AGENT-ID"
SLUG_RE = re.compile(r"^[a-z0-9._-]{1,64}$")


@dataclass(frozen=True)
class Attribution:
    surface: str
    agent_id: str


def read_attribution(headers: Mapping[str, str]) -> Attribution:
    """Parse both headers, or raise a 400 naming the missing or invalid ones."""
    missing: list[str] = []
    invalid: list[str] = []
    values: dict[str, str] = {}
    for header in (SURFACE_HEADER, AGENT_HEADER):
        value = (headers.get(header) or "").strip().lower()
        if not value:
            missing.append(header)
        elif not SLUG_RE.match(value):
            invalid.append(header)
        else:
            values[header] = value
    if missing:
        raise ApiError(
            400,
            "missing_header",
            f"Missing required header {' and '.join(missing)}. Send {SURFACE_HEADER} (where the call comes from, "
            f"e.g. 'internal' or 'slack') and {AGENT_HEADER} (a stable name for your app or agent).",
            headers_missing=missing,
        )
    if invalid:
        raise ApiError(
            400,
            "invalid_header",
            f"Invalid header {' and '.join(invalid)}: use 1-64 characters of [a-z0-9._-].",
            headers_invalid=invalid,
        )
    return Attribution(surface=values[SURFACE_HEADER], agent_id=values[AGENT_HEADER])
