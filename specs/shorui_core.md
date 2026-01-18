# Shorui Core Module Specification

This document describes the `shorui_core` module, which serves as the shared foundation for the shorui-ai platform.

## Overview

`shorui_core` contains domain-agnostic interfaces, shared infrastructure connectors, and global configuration. It allows `ingestion`, `rag`, and `compliance` modules to share common abstractions without creating circular dependencies.

---

## Module Structure

-   `shorui_core/config.py`: Global Pydantic settings
-   `shorui_core/domain/`: Pure domain abstractions
    -   `interfaces.py`: Service Protocols (Storage, Chunker, etc.)
    -   `exceptions.py`: Standard exception hierarchy
    -   `hipaa_schemas.py`: Shared Pydantic models (PHI, Audit)
-   `shorui_core/infrastructure/`: concrete infrastructure connectors
    -   `qdrant.py`: Qdrant singleton
    -   `neo4j.py`: Neo4j singleton
    -   `embeddings.py`: Embedding model singleton
    -   `minio.py`: MinIO client factory

---

## Domain Layer

The domain layer defines the "contract" for the system using Python Protocols and standard Exceptions.

### Service Protocols

Defined in `domain/interfaces.py`, these protocols verify that services in `app/` strictly adhere to the expected interface.

-   **`StorageBackend`**: Abstract interface for file persistence (upload/download/delete)
-   **`ChunkerProtocol`**: Interface for text splitting implementations
-   **`EmbedderProtocol`**: Interface for vector embedding generation
-   **`IndexerProtocol`**: Interface for vector database operations
-   **`ExtractorProtocol`**: Interface for parsing raw documents/PDFs

-   **Source**: [interfaces.py](../shorui_core/domain/interfaces.py)

### Error Handling

Defined in `domain/exceptions.py`, providing a unified failure hierarchy:

-   `ShoruiError` (Base)
    -   `IngestionError`
        -   `IndexingError`
        -   `EmbeddingError`
        -   `ChunkingError`
    -   `ComplianceError`
        -   `PHIDetectionError`

-   **Source**: [exceptions.py](../shorui_core/domain/exceptions.py)

---

## Infrastructure Layer

The infrastructure layer provides **Singleton** connectors to ensure efficient resource usage and connection pooling.

-   **Qdrant**
    -   **Class**: `QdrantDatabaseConnector`
    -   **Description**: Manages connection to Qdrant Vector DB (Cloud/Local)
    -   **Source**: [qdrant.py](../shorui_core/infrastructure/qdrant.py)
-   **Neo4j**
    -   **Class**: `Neo4jClientConnector`
    -   **Description**: Manages driver/session pool for Graph DB
    -   **Source**: [neo4j.py](../shorui_core/infrastructure/neo4j.py)
-   **Embeddings**
    -   **Class**: `EmbeddingModelSingleton`
    -   **Description**: Loads the transformer model once and shares it
    -   **Source**: [embeddings.py](../shorui_core/infrastructure/embeddings.py)

### Usage Example

```python
from shorui_core.infrastructure.qdrant import QdrantDatabaseConnector

# Get singleton instance
client = QdrantDatabaseConnector.get_instance()
```

---

## Configuration

Configuration is handled via `pydantic-settings` in `config.py`. It loads environment variables from `.env` and provides type-safety.

-   **Database**: `QDRANT_DATABASE_HOST`, `NEO4J_URI`, `POSTGRES_DSN`
-   **Storage**: `MINIO_ENDPOINT`, `MINIO_BUCKET_RAW`
-   **Model**: `TEXT_EMBEDDING_MODEL_ID` (Default: `e5-large`)
-   **Async**: `CELERY_BROKER_URL`

-   **Source**: [config.py](../shorui_core/config.py)
