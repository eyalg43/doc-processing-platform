import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_tenant
from app.db.session import get_db
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentResponse

router = APIRouter()


@router.post("/", response_model=DocumentResponse, status_code=202)
async def create_document(
    body: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant),
):
    document = Document(
        tenant_id=tenant_id,
        filename=body.filename,
        content_type=body.content_type,
        status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
