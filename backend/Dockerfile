# syntax=docker/dockerfile:1
# Bean AI backend: FastAPI + Pydantic AI on uvicorn, port 8000.
# Runtime config comes from env vars: OPEN_ROUTER_KEY (required), AGENT_MODEL (optional), and DATABASE_URL for the
# barista/grinder endpoints. Run `bean migrate` (e.g. in an initContainer) before starting a new version.

FROM python:3.13-slim AS build
# uv from PyPI (pulling the ghcr.io/astral-sh/uv image is blocked on some networks).
RUN pip install --no-cache-dir uv==0.13.1
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3
WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
RUN groupadd --system --gid 10001 bean && useradd --system --uid 10001 --gid bean --no-create-home bean
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["uvicorn", "bean_ai_backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
