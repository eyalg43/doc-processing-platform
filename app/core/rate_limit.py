import uuid

from fastapi import Depends, HTTPException

from app.core.config import settings
from app.core.dependencies import get_current_tenant
from app.core.redis import get_redis


async def check_rate_limit(tenant_id: uuid.UUID = Depends(get_current_tenant)) -> uuid.UUID:
    redis = await get_redis()
    key = f"rate_limit:{tenant_id}"

    count = await redis.incr(key)
    if count == 1:
        # First request in this window — set the 60-second expiry
        await redis.expire(key, 60)

    if count > settings.rate_limit_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")

    return tenant_id
