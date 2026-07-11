from crewai import Agent, Crew, Process, Task
from langchain_openai import ChatOpenAI

from app.core.config import settings

_llm = ChatOpenAI(
    model="gpt-4o-mini",
    openai_api_key=settings.openai_api_key,
    temperature=0,
)


def run_document_processing_crew(extracted_text: str) -> tuple[str, str]:
    """
    Runs Extractor + Summarizer agents on the raw PDF text.
    Returns (structured_facts, summary).
    """

    extractor = Agent(
        role="Document Extractor",
        goal="Extract structured key facts from document text accurately",
        backstory=(
            "You are a precise analyst who reads documents and pulls out "
            "the most important structured information: dates, names, amounts, "
            "parties involved, deadlines, and key terms. You never guess — "
            "only extract what is explicitly stated."
        ),
        llm=_llm,
        verbose=False,
    )

    summarizer = Agent(
        role="Document Summarizer",
        goal="Write a clear, concise summary that a non-expert can understand",
        backstory=(
            "You are a skilled writer who takes complex documents and distills "
            "them into plain language. You write 2-3 sentence summaries that "
            "capture the essence without jargon. Your summaries help busy "
            "professionals quickly understand what a document is about."
        ),
        llm=_llm,
        verbose=False,
    )

    extract_task = Task(
        description=(
            f"Read the following document text and extract all key facts "
            f"(dates, names, amounts, parties, obligations, deadlines).\n\n"
            f"Document text:\n{extracted_text[:4000]}"
        ),
        expected_output=(
            "A structured list of key facts extracted from the document. "
            "Each fact on its own line, prefixed with the fact type. "
            "Example: 'Party A: Acme Corp', 'Contract value: $50,000', 'Start date: Jan 1 2026'"
        ),
        agent=extractor,
    )

    summarize_task = Task(
        description=(
            f"Read the following document text and write a 2-3 sentence summary "
            f"in plain language that a non-expert can understand.\n\n"
            f"Document text:\n{extracted_text[:4000]}"
        ),
        expected_output=(
            "A 2-3 sentence plain language summary of the document. "
            "No bullet points, just clear prose."
        ),
        agent=summarizer,
    )

    crew = Crew(
        agents=[extractor, summarizer],
        tasks=[extract_task, summarize_task],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff()

    # Extract individual task outputs
    facts = extract_task.output.raw if extract_task.output else ""
    summary = summarize_task.output.raw if summarize_task.output else ""

    return facts, summary


def run_qa_crew(question: str, context_chunks: list[str]) -> str:
    """
    Runs QA + Validator agents to answer a question from document chunks.
    Validate first, then the answer is streamed by the caller.
    """
    context = "\n\n---\n\n".join(context_chunks)

    qa_agent = Agent(
        role="Document QA Specialist",
        goal="Answer questions accurately using only the provided document context",
        backstory=(
            "You are a careful analyst who answers questions strictly from "
            "the provided source material. You never make up information. "
            "If the answer isn't in the context, you say so clearly."
        ),
        llm=_llm,
        verbose=False,
    )

    validator = Agent(
        role="Answer Validator",
        goal="Verify that answers are grounded in the source material and contain no hallucinations",
        backstory=(
            "You are a quality checker who reads answers and compares them "
            "against the source document chunks. You flag anything that wasn't "
            "explicitly stated in the source. If the answer is accurate, you "
            "return it unchanged. If not, you correct it."
        ),
        llm=_llm,
        verbose=False,
    )

    qa_task = Task(
        description=(
            f"Answer the following question using only the context provided. "
            f"If the answer is not in the context, say 'I don't have enough information to answer that.'\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}"
        ),
        expected_output="A direct, accurate answer to the question based solely on the provided context.",
        agent=qa_agent,
    )

    validate_task = Task(
        description=(
            f"Review the answer to this question: '{question}'\n\n"
            f"Check it against the source context:\n{context}\n\n"
            f"Verify every claim in the answer is supported by the context. "
            f"If the answer is accurate, return it as-is. "
            f"If anything is unsupported or hallucinated, correct it or remove it."
        ),
        expected_output=(
            "The validated final answer. Either the original answer confirmed accurate, "
            "or a corrected version with unsupported claims removed."
        ),
        agent=validator,
        context=[qa_task],
    )

    crew = Crew(
        agents=[qa_agent, validator],
        tasks=[qa_task, validate_task],
        process=Process.sequential,
        verbose=False,
    )

    crew.kickoff()

    return validate_task.output.raw if validate_task.output else "Unable to generate an answer."
