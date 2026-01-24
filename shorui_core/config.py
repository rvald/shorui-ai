"""
Unified configuration for shorui-ai services.

This module provides a single Settings class that consolidates all
environment variables used across the ingestion and RAG services.
Uses defensive programming - raises errors early if required values are missing.
"""

from __future__ import annotations

from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine project root for .env file loading (allows running from any CWD)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Unified settings for all shorui-ai services.

    Environment variables are loaded from .env file and can be overridden
    by actual environment variables.
    """

    # Service identification
    SERVICE_NAME: str = "shorui-ai"

    # PostgreSQL
    POSTGRES_DSN: str = "host=localhost port=5432 dbname=postgres user=postgres password=postgres"

    # Neo4j Configuration
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    NEO4J_DATABASE: str = "neo4j"

    # Qdrant Configuration
    USE_QDRANT_CLOUD: bool = False
    QDRANT_DATABASE_HOST: str = "localhost"
    QDRANT_DATABASE_PORT: int = 6333
    QDRANT_CLOUD_URL: str = ""
    QDRANT_APIKEY: str | None = None

    # MinIO Configuration
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_RAW: str = "raw"
    MINIO_BUCKET_PROCESSED: str = "processed"
    MINIO_SECURE: bool = False

    # Redis / Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Embedding Models
    TEXT_EMBEDDING_MODEL_ID: str = "intfloat/e5-large-unsupervised"
    RERANKING_CROSS_ENCODER_MODEL_ID: str = "cross-encoder/ms-marco-MiniLM-L-4-v2"
    RAG_MODEL_DEVICE: str = "cpu"

    # LLM Inference (RunPod)
    RUNPOD_API_URL: str = ""
    RUNPOD_API_TOKEN: str = ""
    MODEL_INFERENCE: str = "gpt-oss-20b"
    MAX_OUTPUT_TOKENS_INFERENCE: int = 4096
    TOP_P_INFERENCE: float = 0.9
    TEMPERATURE_INFERENCE: float = 0.0

    # OpenAI (alternative)
    OPENAI_MODEL_ID: str = "gpt-5-nano"
    OPENAI_API_KEY: str = ""

    # App host/port
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8081

    # Temporary directory
    TEMP_DIR: str = "tmp"

    # Auth settings
    REQUIRE_AUTH: bool = False  # Set True in production

    # Ingestion retention
    RAW_UPLOAD_TTL_DAYS: int = 30


    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore"
    )


# Global settings instance
settings = Settings()  # type: ignore
