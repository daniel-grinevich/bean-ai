"""Host-based exposure: barista/grinder hostnames reach only their own endpoints, never bean's chat API.

The Host header picks the service. X-Forwarded-Host is checked too, but it can only narrow access (a caller on a
barista host can't spoof their way to bean's API with it).
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from ..config import Settings
from .errors import ApiError

COMMON_PATHS = ("/health", "/v1/usage")
SERVICE_PATHS = {"barista": ("/v1/decide",), "grinder": ("/v1/embed",)}
# Gateway paths on bean's own host, which GATEWAY_ON_BEAN_HOST can switch off.
GATEWAY_PATHS = ("/v1/decide", "/v1/embed", "/v1/usage")


def _hostname(value: str) -> str:
    value = value.split(",")[0].strip().lower()
    if value.startswith("["):  # [ipv6]:port
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def host_services(settings: Settings, hosts: list[str]) -> set[str]:
    """The services whose hostnames these Host / X-Forwarded-Host values match (empty = bean's own host)."""
    return {
        service
        for host in (_hostname(h) for h in hosts if h)
        for service, configured in (("barista", settings.barista_hosts), ("grinder", settings.grinder_hosts))
        if host in configured
    }


def allowed(settings: Settings, services: set[str], path: str) -> bool:
    if not services:
        # Bean's own host: everything, except the gateway endpoints when they're switched off here.
        return settings.gateway_on_bean_host or path not in GATEWAY_PATHS
    paths: set[str] = set(COMMON_PATHS)
    if len(services) == 1:
        paths.update(SERVICE_PATHS[next(iter(services))])
    return path in paths


class HostRoutingMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            services = host_services(self.settings, [headers.get("host", ""), headers.get("x-forwarded-host", "")])
            if not allowed(self.settings, services, scope["path"].rstrip("/") or "/"):
                response = ApiError(404, "not_found", "Not found on this host.").response()
                await response(scope, receive, send)
                return
            # Read by /v1/usage, so a barista host only reports on barista keys.
            scope.setdefault("state", {})["host_services"] = services
        await self.app(scope, receive, send)
