"""
Document CRUD tests.
Uses the `client` fixture (DB wired, rate limit + cache bypassed).
Kafka is patched out — we only test the API layer, not async processing.
"""
import uuid
from unittest.mock import patch


async def test_upload_document_returns_202(client):
    with patch("app.api.v1.documents.publish_document_event"):
        resp = await client.post(
            "/api/v1/documents/",
            files={"file": ("sample.pdf", b"fake pdf content", "application/pdf")},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    assert data["filename"] == "sample.pdf"
    assert data["content_type"] == "application/pdf"


async def test_upload_stores_document_id(client):
    with patch("app.api.v1.documents.publish_document_event"):
        resp = await client.post(
            "/api/v1/documents/",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert resp.status_code == 202
    uuid.UUID(resp.json()["id"])  # raises ValueError if not a valid UUID


async def test_get_document_returns_200(client):
    with patch("app.api.v1.documents.publish_document_event"):
        create_resp = await client.post(
            "/api/v1/documents/",
            files={"file": ("get_me.pdf", b"content", "application/pdf")},
        )
    doc_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == doc_id


async def test_get_nonexistent_document_returns_404(client):
    resp = await client.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_tenant_isolation(client):
    """A document uploaded by one tenant must not be visible to another."""
    from app.core.rate_limit import check_rate_limit
    from app.main import app

    # Upload as the default mock tenant
    with patch("app.api.v1.documents.publish_document_event"):
        create_resp = await client.post(
            "/api/v1/documents/",
            files={"file": ("private.pdf", b"secret", "application/pdf")},
        )
    doc_id = create_resp.json()["id"]

    # Temporarily switch to a different tenant
    other_tenant = uuid.uuid4()
    app.dependency_overrides[check_rate_limit] = lambda: other_tenant

    get_resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 404

    # Restore original override (conftest will do a full clear on teardown,
    # but restore now so other tests in this module aren't affected)
    from tests.conftest import MOCK_TENANT_ID

    app.dependency_overrides[check_rate_limit] = lambda: MOCK_TENANT_ID


async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
