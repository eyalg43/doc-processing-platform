"""
Auth flow tests.
These use `auth_client` (real JWT + real DB) to verify the registration
and token issuance path end-to-end.
"""
import uuid


async def test_register_tenant(auth_client):
    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"name": "Test Corp", "api_key": f"key-{uuid.uuid4().hex}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "tenant_id" in data
    assert data["name"] == "Test Corp"


async def test_get_token(auth_client):
    api_key = f"key-{uuid.uuid4().hex}"
    await auth_client.post(
        "/api/v1/auth/register",
        json={"name": "Token Corp", "api_key": api_key},
    )
    resp = await auth_client.post("/api/v1/auth/token", json={"api_key": api_key})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_invalid_api_key_returns_401(auth_client):
    resp = await auth_client.post(
        "/api/v1/auth/token", json={"api_key": "totally-wrong-key"}
    )
    assert resp.status_code == 401


async def test_register_returns_tenant_id_as_uuid(auth_client):
    api_key = f"key-{uuid.uuid4().hex}"
    resp = await auth_client.post(
        "/api/v1/auth/register",
        json={"name": "UUID Corp", "api_key": api_key},
    )
    assert resp.status_code == 201
    # tenant_id must be a valid UUID string
    uuid.UUID(resp.json()["tenant_id"])  # raises if invalid
