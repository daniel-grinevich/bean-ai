from fastapi import APIRouter

from ..config import registry

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": registry.default}
