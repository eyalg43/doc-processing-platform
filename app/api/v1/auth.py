from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_api_key, verify_api_key
from app.db.session import get_db
from app.models.tenant import Tenant
from app.schemas.auth import TenantCreate, TenantResponse, TokenRequest, TokenResponse

router = APIRouter()


@router.post("/register", response_model=TenantResponse, status_code=201)
async def register_tenant(body: TenantCreate, db: AsyncSession = Depends(get_db)):
    tenant = Tenant(
        name=body.name,
        api_key_hash=hash_api_key(body.api_key),
        is_active=True,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return TenantResponse(tenant_id=str(tenant.id), name=tenant.name)


@router.post("/token", response_model=TokenResponse)
async def get_token(body: TokenRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.is_active == True))
    tenants = result.scalars().all()

    for tenant in tenants:
        if verify_api_key(body.api_key, tenant.api_key_hash):
            return TokenResponse(access_token=create_access_token(tenant.id))

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )
