"""
Unified FastAPI application for shorui-ai.

This is the main entry point that consolidates both the ingestion
and RAG services into a single, unified API.

Usage:
    uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ingestion.routes import router as ingestion_router
from app.rag.routes import router as rag_router
from app.agent.routes import router as agent_router
from app.compliance.routes import router as compliance_router
from shorui_core.auth.middleware import AuthMiddleware
from shorui_core.config import settings
from shorui_core.infrastructure.telemetry import TelemetryService, setup_telemetry
from shorui_core.logging import setup_logging

# Initialize logging
setup_logging()

# Initialize Telemetry (Tracing/Metrics)
setup_telemetry()

# Create the unified FastAPI app
app = FastAPI(
    title="Shorui AI",
    description="Unified API for document ingestion and RAG (Retrieval-Augmented Generation)",
    version="1.0.0",
)

# Instrument FastAPI app
TelemetryService().instrument_app(app)

# CORS configuration for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative frontend
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware (set REQUIRE_AUTH=true in production)
app.add_middleware(AuthMiddleware, require_auth=settings.REQUIRE_AUTH)


# Mount the ingestion router under /ingest prefix
app.include_router(ingestion_router, prefix="/ingest", tags=["Ingestion"])

# Mount the RAG router under /rag prefix
app.include_router(rag_router, prefix="/rag", tags=["RAG"])

# Mount the agent router (no prefix, routes already have /agent)
app.include_router(agent_router, tags=["Agent"])

# Mount the compliance router under /compliance prefix
app.include_router(compliance_router, prefix="/compliance", tags=["Compliance"])


@app.get("/health")
def health():
    """
    Health check endpoint for the unified application.

    Returns:
        dict: Status and service information.
    """
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0"}
