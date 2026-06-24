from pydantic import BaseModel


class TenantCreate(BaseModel):
    name: str
    api_key: str


class TokenRequest(BaseModel):
    api_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
