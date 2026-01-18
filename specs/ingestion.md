# Ingestion Module Specification

This document describes the ingestion module architecture and implementation.

## Overview

The ingestion module handles document upload, processing, and indexing for the shorui-ai platform. It supports general documents and HIPAA regulations with multi-tenant project isolation.

---

## Module Structure

```
app/ingestion/
├── schemas.py              # Pydantic request/response models
├── routes/                 # API endpoints by domain
│   ├── documents.py        # Document upload & status
│   ├── transcripts.py      # HIPAA compliance analysis
│   └── regulations.py      # Regulation collection stats
└── services/               # Business logic
    ├── pipeline.py         # Composable processing pipeline
    ├── chunking.py         # Text splitting
    ├── embedding.py        # Vector embeddings
    ├── indexing.py         # Qdrant indexing
    ├── storage.py          # MinIO storage
    ├── local_storage.py    # Filesystem storage (dev)
    ├── storage_protocol.py # Storage interface
    ├── job_ledger.py       # PostgreSQL job tracking
    └── document_ingestion_service.py
```

---

## API Endpoints

### Document Processing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/documents` | Upload document for async processing |
| `GET` | `/documents/{job_id}/status` | Get processing job status |

> Source: [documents.py](../app/ingestion/routes/documents.py)

### HIPAA Compliance

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/clinical-transcripts` | Upload transcript for PHI detection |
| `GET` | `/clinical-transcripts/jobs/{job_id}` | Poll analysis job status |
| `GET` | `/clinical-transcripts/{id}/compliance-report` | Get compliance report |
| `GET` | `/audit-log` | Query audit events |

> Source: [transcripts.py](../app/ingestion/routes/transcripts.py)

### HIPAA Regulations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/hipaa-regulations/stats` | Get Qdrant collection stats |

> Source: [regulations.py](../app/ingestion/routes/regulations.py)

---

## Schemas

All request/response models use Pydantic for validation:

- `JobStatus` - Processing job status response
- `UploadResponse` - Document upload acknowledgment
- `TranscriptUploadResponse` - Transcript analysis result
- `ComplianceReportResponse` - Full HIPAA compliance report
- `AuditLogEntry` / `AuditLogResponse` - Audit trail
- `RegulationCollectionStats` - Qdrant collection info

> Source: [schemas.py](../app/ingestion/schemas.py)

---

## Processing Pipeline

Documents are processed through a composable pipeline:

```
Raw Content → TextExtractor → Chunker → Embedder → QdrantIndexer
```

### Pipeline Stages

| Stage | Class | Purpose |
|-------|-------|---------|
| Text extraction | `TextExtractor` | PDF/TXT to plain text |
| Chunking | `Chunker` | Split into overlapping chunks |
| Embedding | `Embedder` | Generate vector embeddings |
| Indexing | `QdrantIndexer` | Store in vector database |

### Usage

```python
from app.ingestion.services import create_document_pipeline, PipelineContext

pipeline = create_document_pipeline(collection_name="my_docs")
ctx = pipeline.run(PipelineContext(
    raw_content=document_bytes,
    filename="report.pdf",
    content_type="application/pdf",
))
```

> Source: [pipeline.py](../app/ingestion/services/pipeline.py)

---

## Storage Backends

Storage is abstracted via the `StorageBackend` protocol:

| Backend | Class | Use Case |
|---------|-------|----------|
| MinIO | `MinIOStorage` | Production |
| Filesystem | `LocalStorage` | Development/Testing |

### Factory Function

```python
from app.ingestion.services import get_storage_backend

storage = get_storage_backend()  # Auto-selects based on config
```

> Source: [storage_protocol.py](../app/ingestion/services/storage_protocol.py), [storage.py](../app/ingestion/services/storage.py), [local_storage.py](../app/ingestion/services/local_storage.py)

---

## Services

### ChunkingService

Splits text into overlapping character-based chunks.

- Default chunk size: 1000 characters
- Default overlap: 100 characters

> Source: [chunking.py](../app/ingestion/services/chunking.py)

### EmbeddingService

Generates vector embeddings using the `e5-large-unsupervised` model.

> Source: [embedding.py](../app/ingestion/services/embedding.py)

### IndexingService

Manages Qdrant vector database operations:
- Collection creation
- Batch point upserts
- Default collection: `hipaa_regulations`

> Source: [indexing.py](../app/ingestion/services/indexing.py)

### JobLedgerService

PostgreSQL-backed job tracking with:
- Idempotency via SHA-256 content hashing
- Dead Letter Queue for failed jobs
- Status: `pending` → `processing` → `completed` / `failed`

> Source: [job_ledger.py](../app/ingestion/services/job_ledger.py)

---

## Async Processing

Document processing is handled asynchronously via Celery:

1. `POST /documents` receives file → generates `job_id`
2. Celery task `process_document` runs in background
3. Status tracked in PostgreSQL via `JobLedgerService`
4. `GET /documents/{job_id}/status` polls for completion

> Source: [tasks.py](../app/workers/tasks.py)

---

## Configuration

Key settings from `shorui_core.config`:

| Setting | Description |
|---------|-------------|
| `QDRANT_DATABASE_HOST` | Qdrant server host |
| `MINIO_ENDPOINT` | MinIO server endpoint |
| `MINIO_BUCKET_RAW` | Raw document bucket |
| `USE_LOCAL_STORAGE` | Use filesystem instead of MinIO |
| `TEXT_EMBEDDING_MODEL_ID` | Embedding model (e5-large) |

> Source: [config.py](../shorui_core/config.py)
