import json
import uuid

from app.core.config import settings
from app.core.redis import get_redis


def _document_key(document_id: uuid.UUID) -> str:
    return f"document:{document_id}"


async def get_cached_document(document_id: uuid.UUID) -> dict | None:
    redis = await get_redis()
    raw = await redis.get(_document_key(document_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached_document(document_id: uuid.UUID, data: dict) -> None:
    redis = await get_redis()
    await redis.setex(
        _document_key(document_id),
        settings.cache_ttl_seconds,
        json.dumps(data),
    )


async def invalidate_document(document_id: uuid.UUID) -> None:
    redis = await get_redis()
    await redis.delete(_document_key(document_id))
