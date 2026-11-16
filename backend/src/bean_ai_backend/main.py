from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .observability import setup_tracing
from .routers import agents, chat, conversations, health, models

app = FastAPI(title="Bean AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(chat.router, prefix="/api")

# None when tracing is off (no OTEL_EXPORTER_OTLP_ENDPOINT).
tracer_provider = setup_tracing(app)
