import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import check_rate_limit
from app.db.session import get_db
from app.models.chunk import DocumentChunk
from app.schemas.ask import AskRequest, AskResponse
from app.services.ai import answer_question, embed_query

router = APIRouter()


@router.post("/", response_model=AskResponse)
async def ask(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(check_rate_limit),
):
    # Embed the question
    question_vector = embed_query(body.question)

    # Find the top 5 most similar chunks for this tenant using pgvector cosine similarity
    vector_literal = f"'[{','.join(str(v) for v in question_vector)}]'"
    stmt = text(
        f"""
        SELECT id, content
        FROM document_chunks
        WHERE tenant_id = :tenant_id
        ORDER BY embedding <=> {vector_literal}::vector
        LIMIT 5
        """
    )
    result = await db.execute(stmt, {"tenant_id": str(tenant_id)})
    rows = result.fetchall()

    if not rows:
        return AskResponse(
            question=body.question,
            answer="No documents found. Please upload and process some documents first.",
            chunks_used=0,
        )

    context_chunks = [row.content for row in rows]
    answer = answer_question(body.question, context_chunks)

    return AskResponse(
        question=body.question,
        answer=answer,
        chunks_used=len(context_chunks),
    )
