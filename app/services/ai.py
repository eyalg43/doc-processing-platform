import uuid

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

from app.core.config import settings

_openai_client = OpenAI(api_key=settings.openai_api_key)

_embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=settings.openai_api_key,
)

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
)

_llm = ChatOpenAI(
    model="gpt-4o-mini",
    openai_api_key=settings.openai_api_key,
    temperature=0,
)


def extract_and_summarize(filename: str, content_type: str) -> tuple[str, str]:
    """Call OpenAI to simulate extraction and summarization from a document."""
    prompt = (
        f"You are processing a document named '{filename}' of type '{content_type}'. "
        "Generate realistic extracted text (2-3 paragraphs) and a one-sentence summary. "
        "Reply in JSON format: {\"extracted_text\": \"...\", \"summary\": \"...\"}"
    )
    response = _openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    import json
    result = json.loads(response.choices[0].message.content)
    return result["extracted_text"], result["summary"]


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    return _splitter.split_text(text)


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed a list of text chunks into vectors."""
    return _embeddings.embed_documents(chunks)


def embed_query(query: str) -> list[float]:
    """Embed a single query string for similarity search."""
    return _embeddings.embed_query(query)


def answer_question(question: str, context_chunks: list[str]) -> str:
    """Given retrieved context chunks, ask the LLM to answer the question."""
    context = "\n\n---\n\n".join(context_chunks)
    prompt = (
        f"Answer the following question using only the context provided. "
        f"If the answer is not in the context, say 'I don't have enough information to answer that.'\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )
    from langchain_core.messages import HumanMessage
    response = _llm.invoke([HumanMessage(content=prompt)])
    return response.content
