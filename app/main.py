from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import router as v1_router
from app.core.logging import setup_logging
from app.core.middleware import CorrelationIdMiddleware

setup_logging()

app = FastAPI(
    title="Document Processing Platform",
    version="0.1.0",
)

app.add_middleware(CorrelationIdMiddleware)
app.include_router(v1_router, prefix="/api/v1")

Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    return {"status": "ok"}
