import asyncio
import uuid

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.core.config import settings
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
    # Create a fresh engine per task invocation to avoid asyncpg event loop conflicts on Windows
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
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

                import time
                time.sleep(2)

                document.status = "done"
                document.extracted_text = f"Simulated extraction for {document.filename}"
                document.summary = f"Simulated summary for {document.filename}"
                await db.commit()

                # Create fresh Redis client per task to avoid event loop conflicts on Windows
                redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
                try:
                    await redis_client.delete(f"document:{document_id}")
                finally:
                    await redis_client.aclose()

                return {"status": "done", "document_id": document_id}

            except Exception as exc:
                document.status = "pending"
                await db.commit()
                raise task.retry(exc=exc)
    finally:
        await engine.dispose()
