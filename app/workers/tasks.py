import asyncio
import uuid

import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="process_document",
)
def process_document(self, document_id: str, tenant_id: str) -> dict:
    return asyncio.run(_process(self, document_id, tenant_id))


async def _process(task, document_id: str, tenant_id: str) -> dict:
    from app.services.ai import chunk_text, embed_chunks, extract_text_from_pdf
    from app.services.agents import run_document_processing_crew

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

                # Extract real text from the uploaded PDF
                extracted_text = extract_text_from_pdf(document.file_path)

                # Run CrewAI agents: Extractor + Summarizer
                structured_facts, summary = run_document_processing_crew(extracted_text)

                # Chunk and embed
                chunks = chunk_text(extracted_text)
                embeddings = embed_chunks(chunks)

                # Save chunks to Postgres
                for i, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
                    chunk = DocumentChunk(
                        document_id=document.id,
                        tenant_id=document.tenant_id,
                        chunk_index=i,
                        content=chunk_content,
                        embedding=embedding,
                    )
                    db.add(chunk)

                document.status = "done"
                document.extracted_text = structured_facts
                document.summary = summary
                await db.commit()

                # Invalidate Redis cache so next GET returns fresh data
                redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
                try:
                    await redis_client.delete(f"document:{document_id}")
                finally:
                    await redis_client.aclose()

                return {"status": "done", "document_id": document_id}

            except Exception as exc:
                document.status = "pending"
                await db.commit()
                if task.request.retries >= task.max_retries:
                    logger.error(
                        "task_sent_to_dlq",
                        document_id=document_id,
                        tenant_id=tenant_id,
                        error=str(exc),
                    )
                    celery_app.send_task(
                        "process_document_dlq",
                        args=[document_id, tenant_id, str(exc)],
                        queue="documents.dlq",
                    )
                    return {"status": "failed", "document_id": document_id}
                raise task.retry(exc=exc)
    finally:
        await engine.dispose()
