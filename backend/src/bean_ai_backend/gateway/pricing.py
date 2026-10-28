"""What a request costs: OpenRouter's usage.cost first, then the cached catalogue price, then a pessimistic fallback
so budgets still bite when both are missing."""

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from ..config import Settings
from .openrouter import OpenRouterClient

MTOK = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    prompt: Decimal  # USD per input token
    completion: Decimal  # USD per output token
    request: Decimal  # USD per request


@dataclass(frozen=True)
class Cost:
    usd: Decimal
    source: str  # openrouter | pricing | fallback


def to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value)) if value not in (None, "") else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


class PricingCache:
    def __init__(self, settings: Settings, client: OpenRouterClient) -> None:
        self._settings = settings
        self._client = client
        self._prices: dict[str, ModelPrice] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    def _stale(self) -> bool:
        return self._fetched_at is None or time.monotonic() - self._fetched_at > self._settings.pricing_ttl_s

    async def price(self, model: str) -> ModelPrice | None:
        if self._stale():
            async with self._lock:
                if self._stale():
                    await self._refresh()
        return self._prices.get(model)

    async def _refresh(self) -> None:
        prices: dict[str, ModelPrice] = {}
        if self._client.configured:
            for model in await self._client.list_models():
                pricing = model.get("pricing") or {}
                price = ModelPrice(
                    prompt=to_decimal(pricing.get("prompt")),
                    completion=to_decimal(pricing.get("completion")),
                    request=to_decimal(pricing.get("request")),
                )
                prices[model["id"]] = price
                if slug := model.get("canonical_slug"):
                    prices.setdefault(slug, price)
        if prices:
            self._prices = prices
        # Even on failure, wait a TTL before retrying so a dead catalogue doesn't slow every call.
        self._fetched_at = time.monotonic()

    def _fallback_per_token(self) -> Decimal:
        return self._settings.fallback_price_per_mtok_usd / MTOK

    async def estimate(self, model: str, input_tokens: int) -> Decimal:
        """Rough pre-call cost, used by the budget check."""
        price = await self.price(model)
        if price is None:
            return self._fallback_per_token() * input_tokens
        return price.prompt * input_tokens + price.request

    async def cost(self, model: str, input_tokens: int, output_tokens: int, reported: Any) -> Cost:
        if reported is not None:
            return Cost(to_decimal(reported), "openrouter")
        price = await self.price(model)
        if price is None:
            return Cost(self._fallback_per_token() * (input_tokens + output_tokens), "fallback")
        return Cost(price.prompt * input_tokens + price.completion * output_tokens + price.request, "pricing")
