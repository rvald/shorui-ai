"""
HIPAA regulation management routes.

This module handles endpoints for HIPAA regulation administration:
- Get collection statistics

Note: For uploading HIPAA regulations, use POST /documents with document_type="hipaa_regulation"
"""

from fastapi import APIRouter

from app.ingestion.schemas import RegulationCollectionStats

router = APIRouter()


@router.get("/hipaa-regulations/stats", response_model=RegulationCollectionStats)
async def get_regulation_stats():
    """
    Get statistics about the HIPAA regulations collection.

    Returns:
        RegulationCollectionStats: Collection statistics
    """
    from app.compliance.services.hipaa_regulation_service import HIPAARegulationService

    service = HIPAARegulationService()
    stats = service.get_collection_stats()

    return RegulationCollectionStats(
        exists=stats.get("exists", False),
        points_count=stats.get("points_count", 0),
        message="HIPAA regulations collection ready"
        if stats.get("exists")
        else "Collection not initialized",
    )
