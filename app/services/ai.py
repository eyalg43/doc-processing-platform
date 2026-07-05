import json

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

from app.core.circuit_breaker import openai_breaker
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


@openai_breaker
def extract_and_summarize(filename: str, content_type: str) -> tuple[str, str]:
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
    result = json.loads(response.choices[0].message.content)
    return result["extracted_text"], result["summary"]


def chunk_text(text: str) -> list[str]:
    return _splitter.split_text(text)


@openai_breaker
def embed_chunks(chunks: list[str]) -> list[list[float]]:
    return _embeddings.embed_documents(chunks)


@openai_breaker
def embed_query(query: str) -> list[float]:
    return _embeddings.embed_query(query)


@openai_breaker
def answer_question(question: str, context_chunks: list[str]) -> str:
    context = "\n\n---\n\n".join(context_chunks)
    prompt = (
        f"Answer the following question using only the context provided. "
        f"If the answer is not in the context, say 'I don't have enough information to answer that.'\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )
    response = _llm.invoke([HumanMessage(content=prompt)])
    return response.content
