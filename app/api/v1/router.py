from fastapi import APIRouter

from app.api.v1 import auth, documents

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
