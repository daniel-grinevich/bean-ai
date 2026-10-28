"""In-process token bucket per API key. Bean runs one replica; more replicas would need this in Postgres/Redis."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def try_acquire(self, key: str, rpm: int) -> float | None:
        """Take one request. Return None when allowed, else the seconds until one is available."""
        if rpm <= 0:
            return 60.0
        rate = rpm / 60.0
        now = self._clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = _Bucket(tokens=float(rpm), updated=now)
        else:
            bucket.tokens = min(float(rpm), bucket.tokens + (now - bucket.updated) * rate)
            bucket.updated = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return None
        return (1.0 - bucket.tokens) / rate


def retry_after_header(seconds: float) -> str:
    return str(max(1, math.ceil(seconds)))
