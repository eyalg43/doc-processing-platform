import asyncio
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import check_rate_limit
from app.db.session import get_db
from app.schemas.ask import AskRequest, AskResponse
from app.services.agents import run_qa_crew
from app.services.ai import embed_query

router = APIRouter()


@router.post("/", response_model=AskResponse)
async def ask(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(check_rate_limit),
):
    context_chunks = await _retrieve_chunks(body.question, tenant_id, db)

    if not context_chunks:
        return AskResponse(
            question=body.question,
            answer="No documents found. Please upload and process some documents first.",
            chunks_used=0,
        )

    answer = run_qa_crew(body.question, context_chunks)

    return AskResponse(
        question=body.question,
        answer=answer,
        chunks_used=len(context_chunks),
    )


@router.post("/stream")
async def ask_stream(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(check_rate_limit),
):
    context_chunks = await _retrieve_chunks(body.question, tenant_id, db)

    if not context_chunks:
        async def empty():
            yield "data: No documents found.\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    # Validate first (blocking), then stream the validated answer word by word
    validated_answer = await asyncio.to_thread(run_qa_crew, body.question, context_chunks)

    return StreamingResponse(
        _stream_answer(validated_answer),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_answer(answer: str):
    words = answer.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else " " + word
        yield f"data: {token}\n\n"
        await asyncio.sleep(0.03)
    yield "data: [DONE]\n\n"


async def _retrieve_chunks(question: str, tenant_id: uuid.UUID, db: AsyncSession) -> list[str]:
    question_vector = embed_query(question)
    vector_literal = f"'[{','.join(str(v) for v in question_vector)}]'"
    stmt = text(
        f"""
        SELECT content
        FROM document_chunks
        WHERE tenant_id = :tenant_id
        ORDER BY embedding <=> {vector_literal}::vector
        LIMIT 5
        """
    )
    result = await db.execute(stmt, {"tenant_id": str(tenant_id)})
    rows = result.fetchall()
    return [row.content for row in rows]
