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
| **Observability** | Prometheus + Grafana (metrics + dashboards) |
| **Logging** | structlog (structured JSON logs + correlation IDs) |
| **Resilience** | pybreaker (circuit breaker around OpenAI) |
| **Multi-agent** | CrewAI (Extractor, Summarizer, QA, Validator agents) |
| **PDF Parsing** | PyMuPDF (fitz) |
| **Streaming** | SSE (Server-Sent Events) via sse-starlette |
| **Containerisation** | Docker + Docker Compose |
| **Cloud** | AWS (EKS, RDS, ElastiCache, ECR, S3) via Terraform |
| **Dependency Management** | uv (Astral) |

---

## Features Built (Phases 1–6)

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

### Phase 5 — Observability & Resilience
- Structured JSON logging with `structlog` — every log line includes `correlation_id` and `tenant_id`
- Correlation ID middleware — unique ID generated per request, traceable end-to-end across API → Kafka → Celery
- Prometheus metrics auto-instrumented on all endpoints (request count, latency histograms, error rates)
- Grafana dashboard connected to Prometheus for live visualization
- Circuit breaker (`pybreaker`) around all OpenAI calls — trips after 3 failures, recovers after 30 seconds
- Dead Letter Queue — tasks that exhaust all retries are routed to `documents.dlq` instead of being silently dropped

### Phase 6 — Cloud Infrastructure
- Full AWS infrastructure defined as Terraform code (IaC)
- VPC with public/private subnets across 2 availability zones
- EKS (managed Kubernetes) running FastAPI + Celery as separate deployments
- RDS Postgres + ElastiCache Redis in private subnets (not internet-accessible)
- ECR as Docker image registry
- S3 for document storage + Terraform remote state
- Kubernetes manifests: Deployments, Services, Jobs (Alembic migrations)
- Kubernetes Secrets for zero-secrets-in-git credential management
- Graceful Kafka fallback: direct Celery dispatch when broker unavailable

---

## Request Lifecycle

```
POST /documents
  → validate JWT (tenant_id extracted)
  → check rate limit (Redis)
  → persist document to Postgres (status: pending)
  → publish event to Kafka (falls back to direct Celery if Kafka unavailable)
  → return 202 Accepted

[async, in background]
  Kafka Consumer → dispatch Celery task
  Celery Worker:
    → Extractor Agent: pull structured facts from document
    → Summarizer Agent: write human-readable summary
    → chunk text (500 tokens, 50 overlap)
    → embed chunks (OpenAI embeddings)
    → store chunks + vectors in pgvector
    → update status: done
    → invalidate Redis cache

POST /ask?question=...
  → embed question (OpenAI)
  → cosine similarity search in pgvector (top 5 chunks)
  → QA Agent: formulate answer from retrieved chunks
  → Validator Agent: verify answer is grounded in source, not hallucinated
  → stream answer token by token (SSE)
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

## Cloud Deployment (AWS)

Infrastructure is fully defined as Terraform code in `terraform/`.

```bash
cd terraform
terraform apply   # provision all AWS resources (~15 min)
terraform destroy # tear down everything to stop billing
```

Kubernetes manifests in `k8s/`:
- `api-deployment.yaml` — FastAPI (2 replicas)
- `worker-deployment.yaml` — Celery worker (2 replicas)
- `service.yaml` — AWS Load Balancer
- `migrate-job.yaml` — Alembic migration job (run once per deploy)

---

### Phase 7 — Real PDFs, Multi-Agent, SSE Streaming
- Real file uploads via multipart form — PDFs saved to disk, path stored in Postgres
- PyMuPDF (fitz) extracts raw text page by page from real PDF files
- CrewAI multi-agent pipeline at upload time: Extractor agent (key facts) + Summarizer agent (plain-language summary)
- CrewAI multi-agent pipeline at query time: QA agent (answers from chunks) + Validator agent (removes hallucinations)
- Validate-then-stream pattern: full answer validated before streaming begins, ensuring correctness
- `POST /ask/stream` endpoint streams validated answer word by word via SSE
- `asyncio.to_thread` keeps the async API responsive while blocking CrewAI runs in a background thread
- 10 integration tests (pytest + pytest-asyncio + httpx) covering auth, document CRUD, 404 handling, and tenant isolation
- Locust load test (`locustfile.py`) simulating concurrent tenants uploading and querying documents
- Load testing revealed bcrypt blocking the async event loop under concurrency — fixed by offloading to `asyncio.to_thread`, reducing `/auth/register` P95 from 61s to 3.7s
