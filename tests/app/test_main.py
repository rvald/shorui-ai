"""
Unit tests for the unified FastAPI application.

These tests verify that the unified app correctly mounts both
ingestion and RAG routers, and that the health endpoint works.
"""

import pytest
from fastapi.testclient import TestClient


class TestUnifiedAppHealth:
    """Tests for the health endpoint."""

    def test_health_endpoint_returns_ok(self, test_client):
        """The /health endpoint should return status ok."""
        response = test_client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_endpoint_includes_service_name(self, test_client):
        """The /health endpoint should include the service name."""
        response = test_client.get("/health")

        assert "service" in response.json()


class TestUnifiedAppRouterMounting:
    """Tests for router mounting under correct prefixes."""

    def test_ingestion_router_mounted_under_ingest_prefix(self, test_client):
        """Ingestion endpoints should be accessible under /ingest/*."""
        # The ingestion router should have a /documents endpoint
        response = test_client.get("/ingest/health")

        # Should not be 404 (route exists)
        assert response.status_code != 404

    def test_rag_router_mounted_under_rag_prefix(self, test_client):
        """RAG endpoints should be accessible under /rag/*."""
        # The RAG router should be mounted
        response = test_client.get("/rag/health")

        # Should not be 404 (route exists)
        assert response.status_code != 404


class TestUnifiedAppCORS:
    """Tests for CORS configuration."""

    def test_cors_allows_localhost_origin(self, test_client):
        """CORS should allow requests from localhost development servers."""
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        # Should include CORS headers
        assert "access-control-allow-origin" in response.headers


class TestUnifiedAppOpenAPI:
    """Tests for OpenAPI documentation."""

    def test_openapi_schema_available(self, test_client):
        """The OpenAPI schema should be accessible at /openapi.json."""
        response = test_client.get("/openapi.json")

        assert response.status_code == 200
        assert "openapi" in response.json()

    def test_docs_endpoint_available(self, test_client):
        """The Swagger UI should be accessible at /docs."""
        response = test_client.get("/docs")

        assert response.status_code == 200


# --- Fixtures ---


@pytest.fixture
def test_client():
    """
    Provides a TestClient for the unified FastAPI app.
    """
    from app.main import app

    return TestClient(app)
