"""
Ingestion API routes package.

This package provides a combined router for all ingestion endpoints,
organized by domain:
- documents: Document upload and processing
- transcripts: Clinical transcript analysis and compliance
- regulations: HIPAA regulation management
"""

from fastapi import APIRouter

from .documents import router as documents_router
from .regulations import router as regulations_router
from .transcripts import router as transcripts_router

router = APIRouter()

# Include all sub-routers
router.include_router(documents_router)
router.include_router(transcripts_router)
router.include_router(regulations_router)

__all__ = ["router"]
