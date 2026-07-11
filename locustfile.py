"""
Locust load test for the document processing platform.

Run locally (requires docker compose up + uvicorn running):

    uv run locust --host http://localhost:8000

Then open http://localhost:8089 to control the test.

Suggested ramp:
  - Start: 10 users, spawn rate 2/s
  - Stress: 50 users, spawn rate 5/s
  - Break point hunt: 100 users, spawn rate 10/s

What to watch:
  - P95 latency on POST /documents climbing → DB pool or file I/O bottleneck
  - P95 latency on GET /documents/{id} staying low → Redis cache is working
  - 429 errors → rate limiter correctly defending per-tenant quota
  - 500 errors → connection pool exhaustion or unhandled exception under concurrency
"""

import uuid

from locust import HttpUser, between, task


class DocPlatformUser(HttpUser):
    """
    Simulates a tenant that registers once, then continuously uploads and
    retrieves documents. Each virtual user is its own isolated tenant so
    the per-tenant rate limit (60 req/min) doesn't interfere between users.
    """

    wait_time = between(0.5, 2)  # realistic think time between requests

    token: str = ""
    document_ids: list[str] = []

    def on_start(self):
        """Called once per virtual user at startup: register and authenticate."""
        api_key = f"loadtest-{uuid.uuid4().hex}"
        company_name = f"Load Test Co {uuid.uuid4().hex[:6]}"

        r = self.client.post(
            "/api/v1/auth/register",
            json={"name": company_name, "api_key": api_key},
        )
        if r.status_code != 201:
            return

        r = self.client.post("/api/v1/auth/token", json={"api_key": api_key})
        if r.status_code == 200:
            self.token = r.json()["access_token"]
            self.document_ids = []

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    # weight=3: uploads are common but not the majority of traffic
    @task(3)
    def upload_document(self):
        if not self.token:
            return
        # Small synthetic payload — we're testing the API path, not AI processing.
        # The Celery worker will try to extract text from this (it'll get empty text),
        # which is fine — we're measuring API latency, not end-to-end processing time.
        content = b"%PDF-1.4\n1 0 obj<</Type /Catalog>>endobj\nxref\n%%EOF"
        resp = self.client.post(
            "/api/v1/documents/",
            files={"file": ("load-test.pdf", content, "application/pdf")},
            headers=self._headers(),
            name="POST /documents/",
        )
        if resp.status_code == 202:
            doc_id = resp.json().get("id")
            if doc_id:
                self.document_ids.append(doc_id)
                # Keep the list bounded — we don't need thousands of IDs in memory
                if len(self.document_ids) > 20:
                    self.document_ids.pop(0)

    # weight=6: reads heavily outnumber writes in real apps
    @task(6)
    def get_document(self):
        if not self.token or not self.document_ids:
            return
        # Always fetch the most recently uploaded document.
        # First call → cache miss (hits Postgres).
        # Subsequent calls → cache hit (hits Redis, should be ~1ms).
        doc_id = self.document_ids[-1]
        self.client.get(
            f"/api/v1/documents/{doc_id}",
            headers=self._headers(),
            name="GET /documents/{id}",
        )

    # weight=1: baseline — measures pure infrastructure overhead with no business logic
    @task(1)
    def health_check(self):
        self.client.get("/health", name="GET /health")


class RateLimitUser(HttpUser):
    """
    A single aggressive tenant that hammers the upload endpoint.
    Use this user class in isolation (set user count to 1-2) to verify
    that the rate limiter returns 429 after 60 requests within 60 seconds.

    In the Locust UI, watch for 429s appearing once this user's request
    count crosses 60 in a rolling minute.
    """

    wait_time = between(0.1, 0.3)  # very fast — designed to trigger rate limit
    weight = 0  # excluded from mixed-scenario runs by default

    token: str = ""

    def on_start(self):
        api_key = f"ratelimit-{uuid.uuid4().hex}"
        r = self.client.post(
            "/api/v1/auth/register",
            json={"name": "Rate Limit Tester", "api_key": api_key},
        )
        if r.status_code == 201:
            r = self.client.post("/api/v1/auth/token", json={"api_key": api_key})
            if r.status_code == 200:
                self.token = r.json()["access_token"]

    @task
    def spam_upload(self):
        if not self.token:
            return
        self.client.post(
            "/api/v1/documents/",
            files={"file": ("spam.pdf", b"%PDF-1.4", "application/pdf")},
            headers={"Authorization": f"Bearer {self.token}"},
            name="POST /documents/ (rate-limit test)",
        )
