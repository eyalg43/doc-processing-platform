import asyncio
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="process_document",
)
def process_document(self, document_id: str, tenant_id: str) -> dict:
    return asyncio.run(_process(self, document_id, tenant_id))


async def _process(task, document_id: str, tenant_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(
                Document.id == uuid.UUID(document_id),
                Document.tenant_id == uuid.UUID(tenant_id),
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            return {"status": "skipped", "reason": "not found"}

        if document.status == "done":
            return {"status": "skipped", "reason": "already processed"}

        try:
            document.status = "processing"
            await db.commit()

            # Phase 4: real AI processing goes here
            # For now we simulate work
            import time
            time.sleep(2)

            document.status = "done"
            document.extracted_text = f"Simulated extraction for {document.filename}"
            document.summary = f"Simulated summary for {document.filename}"
            await db.commit()

            return {"status": "done", "document_id": document_id}

        except Exception as exc:
            document.status = "pending"
            await db.commit()
            raise task.retry(exc=exc)
