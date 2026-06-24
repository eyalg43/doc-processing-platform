import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    filename: str
    content_type: str


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    filename: str
    content_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
