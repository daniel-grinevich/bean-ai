"""The request pipeline shared by /v1/decide, /v1/embed and bean's own in-process calls.

For a friend's key: scope (403) -> rate limit (429) -> model allow-list (400) -> max tokens (413)
-> key budget / service cap (402) -> OpenRouter -> cost -> usage row. Every step writes a usage row, rejections
included. Auth (401) and the attribution headers (400) are checked by the routes before this runs.

Bean's agents call `get_gateway().decide(...)` / `.embed(...)` directly: same client, pricing and usage log, no key
(so no rpm or per-key budget), but the service's global monthly cap still applies.
"""

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from ..config import Settings
from ..db import ApiKey, Database, Usage, utcnow
from .attribution import Attribution
from .errors import ApiError
from .keys import Service, parse_key, verify_key
from .openrouter import OpenRouterClient, UpstreamResponse, UpstreamUnavailable
from .pricing import PricingCache
from .ratelimit import RateLimiter, retry_after_header
from .usage import month_spend

log = logging.getLogger("bean.gateway")

# Token estimate before the call, when real counts aren't known yet.
CHARS_PER_TOKEN = 4

INTERNAL = Attribution(surface="internal", agent_id="bean")


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return max(1, -(-len(text) // CHARS_PER_TOKEN))


@dataclass
class Result:
    body: Any
    cost_usd: Decimal
    # What's left of the key's monthly budget after this call; None for in-process calls.
    budget_remaining_usd: Decimal | None


@dataclass
class _Call:
    """Service-specific parts of a request."""

    endpoint: str
    send: Callable[[dict[str, Any]], Any]
    estimated_tokens: int
    # (input_tokens, output_tokens, reported_cost) from the upstream body.
    read_usage: Callable[[Any], tuple[int, int, Any]]


def _usage_field(body: Any, name: str) -> Any:
    usage = body.get("usage") if isinstance(body, dict) else None
    return usage.get(name) if isinstance(usage, dict) else None


class Gateway:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.client = OpenRouterClient(settings)
        self.pricing = PricingCache(settings, self.client)
        self.limiter = RateLimiter()

    async def aclose(self) -> None:
        await self.client.aclose()
        await self.db.dispose()

    # --- auth ---

    async def authenticate(self, headers: Mapping[str, str], service: Service | None) -> ApiKey:
        """Look up the caller's key. With ``service``, the key must belong to it (bar_ on decide, grd_ on embed)."""
        plaintext = _bearer(headers)
        if plaintext is None:
            raise ApiError(
                401,
                "missing_api_key",
                "Send your key as 'Authorization: Bearer <key>'.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        parsed = parse_key(plaintext)
        if parsed is None:
            raise ApiError(401, "invalid_api_key", "API key is malformed or unknown.")
        async with self.db.sessionmaker() as session:
            key = (await session.execute(select(ApiKey).where(ApiKey.key_id == parsed.key_id))).scalar_one_or_none()
        if key is None or key.service != parsed.service.value or not verify_key(plaintext, key.key_hash):
            raise ApiError(401, "invalid_api_key", "API key is malformed or unknown.")
        if key.revoked_at is not None:
            raise ApiError(401, "revoked_api_key", "This API key has been revoked.")
        if service is not None and parsed.service is not service:
            raise ApiError(
                403,
                "wrong_service",
                f"This is a {parsed.service.value} key; it only works on {parsed.service.value}, not {service.value}.",
            )
        return key

    # --- the two services ---

    async def decide(
        self, payload: dict[str, Any], *, key: ApiKey | None = None, attribution: Attribution = INTERNAL
    ) -> Result:
        """OpenRouter Decisions API. ``payload`` is {state, questions, model?, assets?, session_id?, ...}."""
        payload = dict(payload)
        payload["model"] = self._resolve_model(Service.BARISTA, payload.get("model"))
        call = _Call(
            endpoint="/v1/decide",
            send=self.client.decide,
            estimated_tokens=estimate_tokens({k: v for k, v in payload.items() if k != "model"}),
            read_usage=lambda b: (
                int(_usage_field(b, "input_tokens") or 0),
                int(_usage_field(b, "output_tokens") or 0),
                _usage_field(b, "cost"),
            ),
        )
        return await self._run(Service.BARISTA, payload, call, key, attribution)

    async def embed(
        self, payload: dict[str, Any], *, key: ApiKey | None = None, attribution: Attribution = INTERNAL
    ) -> Result:
        """OpenRouter /embeddings. ``payload`` is {input: str | [str], model?, dimensions?, ...}."""
        payload = dict(payload)
        payload["model"] = self._resolve_model(Service.GRINDER, payload.get("model"))
        inputs = payload.get("input")
        if isinstance(inputs, list) and len(inputs) > self.settings.max_embed_inputs:
            raise ApiError(400, "too_many_inputs", f"At most {self.settings.max_embed_inputs} inputs per request.")
        call = _Call(
            endpoint="/v1/embed",
            send=self.client.embed,
            estimated_tokens=estimate_tokens(inputs),
            read_usage=lambda b: (int(_usage_field(b, "prompt_tokens") or 0), 0, _usage_field(b, "cost")),
        )
        return await self._run(Service.GRINDER, payload, call, key, attribution)

    # --- pipeline ---

    def _resolve_model(self, service: Service, requested: Any) -> str:
        allowed = service.models(self.settings)
        if requested is None:
            return allowed[0]
        if requested not in allowed:
            raise ApiError(400, "model_not_allowed", f"Model '{requested}' is not allowed.", allowed_models=allowed)
        return requested

    def _provider_prefs(self, service: Service, payload: dict[str, Any], key: ApiKey | None) -> dict[str, Any]:
        provider = payload.get("provider")
        provider = dict(provider) if isinstance(provider, dict) else {}
        if self.settings.openrouter_data_collection:
            # Forced, not defaulted: a caller can't opt the account into data collection.
            provider["data_collection"] = self.settings.openrouter_data_collection
        if provider:
            payload["provider"] = provider
        # A stable end-user id per key for OpenRouter's abuse tooling, unless the caller set one.
        payload.setdefault("user", f"{service.value}:{key.key_id if key else 'bean'}")
        return payload

    async def _run(
        self, service: Service, payload: dict[str, Any], call: _Call, key: ApiKey | None, attribution: Attribution
    ) -> Result:
        started = time.perf_counter()

        async def record(status: int, error_code: str | None = None, **fields: Any) -> None:
            await self._record(
                service,
                key,
                attribution,
                endpoint=call.endpoint,
                model=payload["model"],
                status=status,
                error_code=error_code,
                latency_ms=int((time.perf_counter() - started) * 1000),
                **fields,
            )

        try:
            if key is not None:
                self._check_key_limits(service, key, call)
            remaining = await self._check_budgets(service, key, payload["model"], call.estimated_tokens)
            if not self.client.configured:
                raise ApiError(503, "upstream_not_configured", "OPEN_ROUTER_KEY is not configured.")
            try:
                upstream: UpstreamResponse = await call.send(self._provider_prefs(service, payload, key))
            except UpstreamUnavailable as exc:
                raise ApiError(502, "upstream_unavailable", "Could not reach OpenRouter.") from exc
            if upstream.status >= 400:
                raise _upstream_error(upstream)
            inp, out, reported = call.read_usage(upstream.body)
            cost = await self.pricing.cost(payload["model"], inp, out, reported)
        except ApiError as exc:
            await record(exc.status, exc.code)
            raise
        await record(
            200,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=cost.usd,
            cost_source=cost.source,
            upstream_id=upstream.body.get("id") if isinstance(upstream.body, dict) else None,
        )
        return Result(
            body=upstream.body,
            cost_usd=cost.usd,
            budget_remaining_usd=None if remaining is None else max(Decimal(0), remaining - cost.usd),
        )

    def _check_key_limits(self, service: Service, key: ApiKey, call: _Call) -> None:
        if service.scope not in key.scopes:
            raise ApiError(403, "insufficient_scope", f"This key lacks the '{service.scope}' scope.")
        retry_after = self.limiter.try_acquire(key.id, key.rpm)
        if retry_after is not None:
            raise ApiError(
                429,
                "rate_limited",
                f"Rate limit of {key.rpm} requests/minute exceeded.",
                headers={"Retry-After": retry_after_header(retry_after)},
                retry_after_s=round(retry_after, 2),
            )
        if call.estimated_tokens > key.max_tokens_per_request:
            raise ApiError(
                413,
                "too_many_tokens",
                f"Request is ~{call.estimated_tokens} tokens; this key allows {key.max_tokens_per_request}.",
                estimated_tokens=call.estimated_tokens,
                max_tokens_per_request=key.max_tokens_per_request,
            )

    async def _check_budgets(
        self, service: Service, key: ApiKey | None, model: str, estimated_tokens: int
    ) -> Decimal | None:
        """Raise 402 if this call would go over the key's budget or the service cap. Returns the key's remaining budget.

        Not atomic: concurrent requests can overshoot by at most what's in flight.
        """
        estimate = await self.pricing.estimate(model, estimated_tokens)
        remaining = None
        async with self.db.sessionmaker() as session:
            if key is not None:
                spent = await month_spend(session, api_key_id=key.id)
                remaining = key.monthly_budget_usd - spent
                if spent + estimate > key.monthly_budget_usd:
                    raise ApiError(
                        402,
                        "budget_exceeded",
                        f"This key's monthly budget of ${key.monthly_budget_usd:.2f} is used up "
                        f"(${spent:.4f} spent this month). It resets on the 1st (UTC).",
                        budget_usd=str(key.monthly_budget_usd),
                        spent_usd=f"{spent:.8f}",
                    )
            cap = service.monthly_cap(self.settings)
            if cap > 0 and await month_spend(session, service=service.value) + estimate > cap:
                log.warning("monthly cap reached for %s", service.value)
                raise ApiError(
                    402,
                    "service_budget_exceeded",
                    f"{service.value} has hit its global monthly cap. "
                    "Try again next month or ask the owner to raise it.",
                )
        return remaining

    async def _record(
        self,
        service: Service,
        key: ApiKey | None,
        attribution: Attribution,
        *,
        endpoint: str,
        model: str,
        status: int,
        error_code: str | None,
        latency_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: Decimal = Decimal(0),
        cost_source: str = "none",
        upstream_id: str | None = None,
    ) -> None:
        try:
            async with self.db.sessionmaker() as session:
                now = utcnow()
                session.add(
                    Usage(
                        api_key_id=key.id if key else None,
                        service=service.value,
                        endpoint=endpoint,
                        surface=attribution.surface,
                        agent_id=attribution.agent_id,
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_usd,
                        cost_source=cost_source,
                        latency_ms=latency_ms,
                        status_code=status,
                        error_code=error_code,
                        upstream_id=upstream_id,
                        created_at=now,
                    )
                )
                if key is not None and (db_key := await session.get(ApiKey, key.id)) is not None:
                    db_key.last_used_at = now
                await session.commit()
        except Exception:
            # Never fail a paid request because logging failed, but make it loud.
            log.exception("failed to record %s usage", service.value)


def _bearer(headers: Mapping[str, str]) -> str | None:
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _upstream_error(upstream: UpstreamResponse) -> ApiError:
    message = "OpenRouter returned an error."
    body = upstream.body
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        message = str(body["error"].get("message") or message)
    status = upstream.status
    if status in (400, 404, 413, 422):
        # The caller's request was bad; pass the reason through.
        return ApiError(status, "upstream_rejected", message, upstream_status=status)
    if status in (401, 402, 403):
        # Our OpenRouter key or credits, not the caller's fault. Don't leak details.
        log.error("OpenRouter refused bean's key: %s %s", status, message)
        return ApiError(502, "upstream_auth", "The gateway's upstream account was refused.")
    if status == 429:
        return ApiError(
            503, "upstream_rate_limited", "OpenRouter is rate limiting; retry shortly.", headers={"Retry-After": "5"}
        )
    return ApiError(502, "upstream_error", message, upstream_status=status)


# Set at startup (main.py lifespan) when DATABASE_URL is configured.
_current: Gateway | None = None


def set_gateway(gateway: Gateway | None) -> None:
    global _current
    _current = gateway


def get_gateway() -> Gateway | None:
    """The running gateway, for in-process calls from bean's agents. None when DATABASE_URL isn't set."""
    return _current
