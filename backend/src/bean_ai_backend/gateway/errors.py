"""Gateway JSON errors: ``{"error": {"code": "<slug>", "message": "...", ...}}``.

Only /v1/* uses this envelope; bean's own /api routes keep FastAPI's default ``{"detail": ...}``, which the
frontend reads.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, *, headers: dict[str, str] | None = None, **extra: Any
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers
        self.extra = extra

    def response(self) -> JSONResponse:
        body = {"error": {"code": self.code, "message": self.message, **self.extra}}
        return JSONResponse(body, status_code=self.status, headers=self.headers)


def _is_gateway(request: Request) -> bool:
    return request.url.path.startswith("/v1/")


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> Response:
        return exc.response()

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> Response:
        if not _is_gateway(request):
            return await request_validation_exception_handler(request, exc)
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
        return ApiError(422, "invalid_request", "Request body failed validation.", details=details).response()

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> Response:
        if not _is_gateway(request):
            return await http_exception_handler(request, exc)
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return ApiError(exc.status_code, code, str(exc.detail)).response()
