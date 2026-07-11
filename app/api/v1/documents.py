import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cached_document, set_cached_document
from app.core.rate_limit import check_rate_limit
from app.db.session import get_db
from app.models.document import Document
from app.schemas.document import DocumentResponse
from app.services.kafka_producer import publish_document_event

router = APIRouter()
logger = structlog.get_logger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/", response_model=DocumentResponse, status_code=202)
async def create_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(check_rate_limit),
):
    document = Document(
        tenant_id=tenant_id,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Save file to disk so the Celery worker can read it
    file_path = UPLOAD_DIR / f"{document.id}.pdf"
    content = await file.read()
    file_path.write_bytes(content)

    document.file_path = str(file_path)
    await db.commit()

    publish_document_event(document.id, tenant_id)

    logger.info("document_created", document_id=str(document.id), tenant_id=str(tenant_id), filename=file.filename)
    return document


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(check_rate_limit),
):
    cached = await get_cached_document(document_id)
    if cached:
        if str(cached.get("tenant_id")) != str(tenant_id):
            raise HTTPException(status_code=404, detail="Document not found")
        logger.info("document_cache_hit", document_id=str(document_id), tenant_id=str(tenant_id))
        return cached

    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Document not found")

    data = DocumentResponse.model_validate(document).model_dump(mode="json")
    await set_cached_document(document_id, data)

    logger.info("document_cache_miss", document_id=str(document_id), tenant_id=str(tenant_id))
    return document
