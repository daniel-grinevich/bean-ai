"""Async OpenRouter client for decisions, embeddings and the model catalogue.

Retries 429/5xx and transport errors with exponential backoff and jitter. The upstream key never leaves this module.
"""

import asyncio
import contextlib
import logging
import random
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings

log = logging.getLogger("bean.gateway")

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 524, 529})


@dataclass
class UpstreamResponse:
    status: int
    body: Any


class UpstreamUnavailable(Exception):
    """Transport-level failure after all retries."""


class OpenRouterClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        headers = {"HTTP-Referer": "https://github.com/daniel-grinevich/bean-ai", "X-Title": "Bean AI"}
        if settings.open_router_key:
            headers["Authorization"] = f"Bearer {settings.open_router_key}"
        self._http = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(settings.upstream_timeout_s, connect=5.0))

    @property
    def configured(self) -> bool:
        return bool(self._settings.open_router_key)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def decide(self, payload: dict[str, Any]) -> UpstreamResponse:
        return await self._post(self._settings.openrouter_decisions_url, payload)

    async def embed(self, payload: dict[str, Any]) -> UpstreamResponse:
        return await self._post(f"{self._settings.openrouter_base_url}/embeddings", payload)

    async def list_models(self) -> list[dict[str, Any]]:
        """The general catalogue merged with the embeddings one (embedding models aren't always in /models)."""
        models: dict[str, dict[str, Any]] = {}
        base = self._settings.openrouter_base_url
        for url in (f"{base}/models?output_modalities=all", f"{base}/embeddings/models"):
            try:
                resp = await self._http.get(url)
                resp.raise_for_status()
                for model in resp.json().get("data", []):
                    if isinstance(model, dict) and "id" in model:
                        models.setdefault(model["id"], model)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("model catalogue fetch failed for %s: %s", url, type(exc).__name__)
        return list(models.values())

    async def _post(self, url: str, payload: dict[str, Any]) -> UpstreamResponse:
        retries = self._settings.upstream_max_retries
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._http.post(url, json=payload)
            except httpx.TransportError as exc:
                if attempt > retries:
                    raise UpstreamUnavailable(type(exc).__name__) from exc
                await self._backoff(attempt, None)
                continue
            if resp.status_code in RETRY_STATUSES and attempt <= retries:
                await self._backoff(attempt, resp.headers.get("retry-after"))
                continue
            try:
                body: Any = resp.json()
            except ValueError:
                body = {"error": {"message": resp.text[:500]}}
            return UpstreamResponse(status=resp.status_code, body=body)

    async def _backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = self._settings.upstream_backoff_base_s * 2 ** (attempt - 1)
        if retry_after:
            with contextlib.suppress(ValueError):
                delay = max(delay, min(float(retry_after), 10.0))
        await asyncio.sleep(delay * (1 + random.random() * 0.25))
