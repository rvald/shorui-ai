"""
Ingestion API routes package.

This package provides a combined router for all ingestion endpoints,
organized by domain:
- documents: Document upload and processing
"""

from fastapi import APIRouter

from .documents import router as documents_router

router = APIRouter()

# Include all sub-routers
router.include_router(documents_router)

__all__ = ["router"]
