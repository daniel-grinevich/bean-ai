from fastapi import APIRouter

from ..config import registry, settings
from ..schemas.models import ModelInfo, ModelList

router = APIRouter()


@router.get("/models")
async def list_models() -> ModelList:
    return ModelList(
        default=registry.default,
        models=[
            ModelInfo(id=m.id, label=m.label, provider=m.provider, available=bool(settings.api_key(m.provider)))
            for m in registry.enabled()
        ],
    )
