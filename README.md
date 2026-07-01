# AI-Powered Document Processing Platform

A production-grade, multi-tenant platform where companies submit documents via a REST API and get back AI-extracted structure, summaries, classifications, and the ability to ask natural-language questions across their entire document corpus (RAG).

Built to demonstrate real backend-at-scale architecture — not just a working app, but one that can be explained and defended in a technical interview.

---

## Architecture

```
Company ──HTTP POST /documents──▶ FastAPI (JWT auth, multi-tenant)
                                      │
                                      ▼
                               Kafka (ingestion buffer)
                                      │
                                      ▼
                               Celery Workers (AI processing)
                                  │           │
                          pgvector (vectors)  Redis (cache)
                                  │
                     GET /search, /ask ──▶ RAG Agent (LangChain)
```

**Key design stance:** ingestion is accepted fast and processed asynchronously. The API never blocks on AI work. Kafka decouples "we received it" from "we processed it."

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API** | FastAPI (async), Pydantic, JWT auth |
| **Database** | PostgreSQL + pgvector (vectors + relational data) |
| **Migrations** | Alembic |
| **Message Queue** | Apache Kafka |
| **Task Queue** | Celery + Redis |
| **Cache** | Redis (cache-aside, TTL, invalidation) |
| **Rate Limiting** | Redis (per-tenant token counter) |
| **AI / LLM** | OpenAI GPT-4o-mini, text-embedding-3-small |
| **RAG Pipeline** | LangChain, LangChain-OpenAI |
| **Chunking** | LangChain RecursiveCharacterTextSplitter |
| **Infra** | Docker Compose |
| **Dependency Management** | uv (Astral) |

---

## Features Built (Phases 1–4)

### Phase 1 — Foundation
- Multi-tenant FastAPI REST API
- JWT authentication (stateless, tenant-scoped)
- PostgreSQL schema with Alembic versioned migrations
- Tenant and Document models with full multi-tenancy (`tenant_id` on every row)
- Docker Compose for local development (Postgres, Kafka, Redis)

### Phase 2 — Async Pipeline
- Kafka ingestion: documents published as events on upload
- Celery worker pool consuming tasks via Redis broker
- Kafka consumer dispatching tasks to Celery
- Idempotency: duplicate document submissions are safely skipped
- `task_acks_late=True`: tasks survive worker crashes
- Returns `202 Accepted` immediately — AI work is fully async

### Phase 3 — Caching & Rate Limiting
- Redis cache-aside for `GET /documents/{id}` — cache hit skips Postgres entirely
- Explicit cache invalidation when Celery finishes processing
- Per-tenant rate limiting: 60 requests/minute, enforced atomically in Redis
- `429 Too Many Requests` with 60-second rolling window

### Phase 4 — AI Layer
- OpenAI GPT-4o-mini for text extraction and summarization
- Document chunking with 500-token chunks and 50-token overlap
- OpenAI `text-embedding-3-small` embeddings stored in pgvector
- `POST /ask` endpoint: semantic search over tenant's document corpus
- RAG pipeline: embed question → cosine similarity search → LLM answers from retrieved context

---

## Request Lifecycle

```
POST /documents
  → validate JWT (tenant_id extracted)
  → check rate limit (Redis)
  → persist document to Postgres (status: pending)
  → publish event to Kafka
  → return 202 Accepted

[async, in background]
  Kafka Consumer → dispatch Celery task
  Celery Worker:
    → extract text + summarize (OpenAI)
    → chunk text (500 tokens, 50 overlap)
    → embed chunks (OpenAI embeddings)
    → store chunks + vectors in pgvector
    → update status: done
    → invalidate Redis cache

POST /ask?question=...
  → embed question (OpenAI)
  → cosine similarity search in pgvector (top 5 chunks)
  → pass chunks as context to GPT-4o-mini
  → return answer grounded in document content
```

---

## Local Development

```bash
# Start all infrastructure
docker compose up -d

# Apply DB migrations
uv run alembic upgrade head

# Terminal 1 — API
uv run uvicorn app.main:app --reload

# Terminal 2 — Celery worker (Windows: --pool=solo)
uv run celery -A app.workers.celery_app worker --loglevel=info --pool=solo

# Terminal 3 — Kafka consumer
uv run python -m app.workers.kafka_consumer
```

### Environment variables (`.env`)
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/docplatform
JWT_SECRET=your-secret
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...
```

---

## Coming Next

- **Phase 5** — Prometheus + Grafana observability, structured logging, circuit breakers, dead-letter queue, Locust load testing
- **Phase 6** — AWS deployment (EKS, RDS, ElastiCache, MSK, S3) via Terraform + GitHub Actions CI/CD
- **Phase 7** — Real file uploads (PDF parsing), CrewAI multi-agent orchestration, SSE streaming
