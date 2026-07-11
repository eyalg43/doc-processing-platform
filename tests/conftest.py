import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Register all models with Base.metadata before create_all.
# These must be imported BEFORE `from app.main import app` because
# `import app.models.*` rebinds the local name `app` to the package,
# which would shadow the FastAPI instance.
import app.models.chunk  # noqa: F401
import app.models.document  # noqa: F401
import app.models.tenant  # noqa: F401

from app.core.cache import get_cached_document, set_cached_document
from app.core.rate_limit import check_rate_limit
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.tenant import Tenant

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/docplatform"

# A fixed UUID used as the tenant in all tests that use the `client` fixture.
# Tests that need auth to work for real should use `auth_client` instead.
MOCK_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """Create (or verify) all tables once for the whole test session."""

    async def _run():
        eng = create_async_engine(TEST_DB_URL)
        async with eng.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.commit()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_run())


@pytest_asyncio.fixture
async def client():
    """
    HTTP test client with:
    - DB wired to the local Postgres test instance
    - check_rate_limit bypassed (returns MOCK_TENANT_ID)
    - Redis cache bypassed (patched to no-op)

    Requires: docker compose up (Postgres on port 5433)
    """
    eng = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)

    async def _get_db():
        async with factory() as session:
            yield session

    async def _rate_limit():
        return MOCK_TENANT_ID

    async def _cache_miss(_doc_id):
        return None

    async def _cache_noop(_doc_id, _data):
        pass

    # Seed a real tenant row so the documents FK constraint is satisfied.
    # The `client` fixture bypasses JWT, but Postgres still enforces the FK.
    async with factory() as seed_session:
        existing = await seed_session.get(Tenant, MOCK_TENANT_ID)
        if not existing:
            seed_session.add(
                Tenant(
                    id=MOCK_TENANT_ID,
                    name="Test Tenant",
                    api_key_hash="not-a-real-hash",
                    is_active=True,
                )
            )
            await seed_session.commit()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[check_rate_limit] = _rate_limit

    import app.api.v1.documents as doc_module

    doc_module.get_cached_document = _cache_miss
    doc_module.set_cached_document = _cache_noop

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    doc_module.get_cached_document = get_cached_document
    doc_module.set_cached_document = set_cached_document
    await eng.dispose()


@pytest_asyncio.fixture
async def auth_client():
    """
    HTTP test client with real JWT auth + real rate limit (needs Redis).
    Use this fixture when you need to test the auth flow end-to-end.

    Requires: docker compose up (Postgres port 5433 + Redis port 6379)
    """
    eng = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)

    async def _get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await eng.dispose()
