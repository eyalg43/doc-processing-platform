# CLAUDE.md — AI-Powered Document Processing Platform

> This file is the contract for how we build this project. Claude Code reads it at the
> start of every session. It captures the architecture, the rules, and the working agreement.

---

## 1. What we are building

A multi-tenant platform where companies submit documents via a REST API and get back
AI-extracted structure, summaries, classifications, and the ability to ask natural-language
questions across their entire document corpus (RAG).

**The request lifecycle (the one diagram to memorize):**

```
                                  ┌─────────────────────────────────────────┐
                                  │            FastAPI (async)               │
  Company ──HTTP POST /documents─▶│  - JWT auth (multi-tenant)               │
                                  │  - validate + persist metadata (Postgres)│
                                  │  - publish event to Kafka                │
                                  │  - return 202 Accepted + document_id     │
                                  └───────────────┬─────────────────────────┘
                                                  │ produce
                                                  ▼
                                    ┌───────────────────────────┐
                                    │   Kafka topic: documents   │  durable, partitioned,
                                    │   (ingestion buffer)       │  replayable log
                                    └─────────────┬─────────────┘
                                                  │ consume
                                                  ▼
                                    ┌───────────────────────────┐
                                    │   Celery workers (pool)    │  async AI processing
                                    │  - extract / summarize /   │
                                    │    classify via OpenAI     │
                                    │  - circuit breaker + retry │
                                    │  - chunk + embed           │
                                    └───┬───────────────┬───────┘
                                        │               │
                          write embeddings           cache results
                                        ▼               ▼
                              ┌──────────────────┐  ┌─────────┐
                              │ Postgres+pgvector│  │  Redis  │
                              │ (vectors + rows) │  │ (cache) │
                              └─────────┬────────┘  └─────────┘
                                        │
                  GET /search, /ask     │ semantic retrieval
  Company ◀───── (SSE stream) ──────────┘ + RAG agent (LangChain/CrewAI)
```

**Key design stance:** ingestion is *accepted fast and processed asynchronously*. The API
never blocks on AI work. Kafka decouples "we received it" from "we processed it."

---

## 2. Why each component is here (the interview answers)

| Component | Job | Why this and not the alternative |
|---|---|---|
| **FastAPI** | Async REST API, auth, validation | Async I/O fits a workload that is mostly waiting on network (DB, Kafka, OpenAI). Type hints + Pydantic give validation + OpenAPI for free. |
| **Kafka** | Durable ingestion buffer between API and workers | A *log*, not just a queue: replayable, partitioned for parallelism, retains messages. Survives worker outages. Decouples produce rate from consume rate. |
| **Celery** | Distributed worker pool that does the AI work | Mature task framework: retries, routing, scheduling, concurrency. Workers scale horizontally and independently of the API. |
| **Redis** | Cache, rate-limit store, Celery result backend, pub/sub | In-memory, sub-ms reads. Cache-aside for expensive AI results; token-bucket rate limiting; pub/sub for live updates. |
| **PostgreSQL** | Source of truth for tenants, documents, metadata | ACID, relational integrity, mature. Multi-tenant rows scoped by `tenant_id`. |
| **pgvector** | Vector similarity search inside Postgres | Keep embeddings next to relational data — one datastore, transactional, no separate vector DB to operate (until scale demands it). |
| **Alembic** | Versioned schema migrations | Every schema change is code, reviewed, reversible, replayable across environments. |
| **LangChain** | RAG pipeline + LLM orchestration | Standard abstractions for chunking, retrieval, prompt templates, agents. |
| **CrewAI** | Multi-agent orchestration | When one agent isn't enough — specialized agents (extractor, summarizer, QA) with roles. |
| **OpenAI API** | The LLM | Wrapped in circuit breaker + exponential backoff because it's an unreliable external dependency. |
| **Prometheus + Grafana** | Metrics + dashboards | Measure latency, throughput, queue depth, error rates. You can't fix what you can't see. |
| **Locust** | Load testing | Simulate hundreds–thousands of users to find bottlenecks before production does. |
| **Docker Compose** | Local dev: all services in containers | Reproducible environment; mirrors the AWS topology locally. |
| **AWS (EKS/RDS/ElastiCache/MSK/S3/IAM/CloudWatch)** | Managed production infra | Managed versions of every local service. Terraform defines them as code. |

---

## 3. Build phases (do not skip ahead)

Each phase must be solid — runnable, understood, explainable in an interview — before the next.

1. **Foundation** — FastAPI + PostgreSQL + Alembic + Docker + JWT auth (multi-tenant).
2. **Core async architecture** — Kafka ingestion + Celery workers. *The interview centerpiece.*
3. **Caching** — Redis cache-aside, TTL, invalidation, rate limiting.
4. **AI layer** — embeddings, chunking, RAG retrieval, LangChain, CrewAI multi-agent, SSE streaming.
5. **Observability & resilience** — Prometheus, Grafana, structured logging + correlation IDs, circuit breakers, DLQ, Locust load tests + bottleneck fixes.
6. **Cloud** — AWS via Terraform, EKS/RDS/ElastiCache/MSK/S3, GitHub Actions CI/CD.
7. **Polish** — README, architecture diagram, test coverage, design-decision write-ups.

Current phase: **1 — Foundation (not yet started; design walkthrough in progress).**

---

## 4. Project rules & conventions

- **Language/runtime:** Python 3.12+, FastAPI, async-first.
- **Dependency management:** **uv** (Astral). Pin versions, commit `uv.lock`. Use `uv add`,
  `uv run`, `uv sync` — not bare pip.
- **Migrations:** every schema change goes through Alembic. Never edit the DB by hand. Never
  edit a migration that has been applied/shared — add a new one.
- **Multi-tenancy:** every tenant-owned row carries `tenant_id`. Every query is scoped by it.
  This is a security boundary, not a convenience.
- **Config:** 12-factor. All config via environment variables, loaded through Pydantic Settings.
  No secrets in code or git. `.env.example` documents every variable.
- **Idempotency:** async processing must tolerate duplicate delivery (Kafka is at-least-once).
  Use idempotency keys / dedupe on `document_id`.
- **Correlation IDs:** generated at the API edge, propagated through Kafka headers → worker →
  logs, so one request is traceable end-to-end.
- **Errors:** external calls (OpenAI) are wrapped in retry + circuit breaker. Poison messages
  go to a dead-letter queue, never silently dropped.
- **Tests:** pytest. Mock OpenAI in unit tests. Integration tests run against Dockerized deps.
- **Git:** feature branches + PRs. CI (GitHub Actions) runs lint + tests on every PR.
- **Structured logging:** JSON logs, one event per line, always include `correlation_id` and
  `tenant_id` when known.

---

## 5. Working agreement (how Claude should teach in this project)

The user is a CS grad and backend developer (strong Java) leveling up into backend-at-scale + AI.
The goal is genuine market demand, not just a working app. Therefore:

- **Teach, don't just produce.** For every concept: explain *why* it works that way, the
  *tradeoffs*, and *how to explain it in an interview*.
- **Act as senior engineer + instructor simultaneously.**
- **Work in phases**, foundational first. Do not advance until the current phase is solid and
  the user can explain everything built so far.
- **Default model: Sonnet at medium thinking.** Medium is the daily driver — covers code,
  explanation, tradeoffs, and debugging. High thinking is for math-heavy/algorithmic problems
  only, and those moments overlap with Opus triggers anyway.
- **Opus escalation:** when a task genuinely warrants it (hard architecture decision, deep
  conceptual synthesis, Sonnet visibly struggling), Claude flags it explicitly. User switches
  to Opus for that task, then back to Sonnet medium afterward.
- **Prefer understanding over speed.** A working feature the user can't explain is a failure here.
- **Teaching pace: concept-first.** Before each piece, teach the concept + tradeoffs + interview
  framing, confirm the user has it, *then* write the code together. Don't lead with code.

---

## 6. Local development (filled in during Phase 1)

```
# placeholder — docker compose up, alembic upgrade head, uvicorn ... to be defined in Phase 1
```
