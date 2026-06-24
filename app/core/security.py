import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_api_key(api_key: str) -> str:
    return pwd_context.hash(api_key)


def verify_api_key(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(tenant_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(tenant_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    tenant_id = payload.get("sub")
    if not tenant_id:
        raise JWTError("Missing subject")
    return uuid.UUID(tenant_id)
