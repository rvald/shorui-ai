# Workers Module Specification

This document describes the workers module architecture, which handles asynchronous background processing for the shorui-ai platform.

## Overview

The workers module provides a scalable, resilient async processing layer using Celery and Redis. It decouples long-running operations (like document ingestion and HIPAA analysis) from the blocking API layer.

---

## Module Structure

```
app/workers/
├── celery_app.py        # Celery app configuration (Redis connection)
├── decorators.py        # @track_job_ledger decorator (Lifecycle management)
├── tasks.py             # Document processing entry points
└── transcript_tasks.py  # Clinical transcript analysis entry points
```

---

## Architecture

The module follows a **"Thin Task" Architecture** combined with **Orchestrators** and **Decorators**.

### 1. Thin Tasks
Celery tasks are minimal entry points. They do **not** contain business logic. Their only job is to:
1.  Receive arguments.
2.  Instantiate an Orchestrator.
3.  Call the business method.

### 2. Job Ledger Decorator
Cross-cutting concerns regarding the `JobLedgerService` (idempotency, status updates, error handling) are encapsulated in the `@track_job_ledger` decorator.

**Behavior:**
-   **Before Task**: Computes hash, checks idempotency, creates Ledger entry (`pending` -> `processing`).
-   **After Success**: Updates Ledger to `completed` with stats.
-   **On Exception**: Updates Ledger to `failed` and pushes to Dead Letter Queue (DLQ).

### 3. Orchestrators & Strategies

Business logic is delegated to Orchestrators in the respective domain modules:

| Task | Orchestrator | Service Location | Pattern |
|------|--------------|------------------|---------|
| `process_document` | `IngestionOrchestrator` | `app/ingestion` | **Strategy** (`General` vs `HIPAA`) |
| `analyze_transcript` | `ComplianceOrchestrator` | `app/compliance` | **Facade** |

---

## Tasks

### Process Document
**Queue**: `celery` (default)
**Task Name**: `app.workers.tasks.process_document`

Handles the upload, indexing, and storage of documents.

-   **Input**: File content (bytes), metadata.
-   **Routing**:
    -   `general`: Indexes to Qdrant (Vector) + MinIO.
    -   `hipaa_regulation`: Parses regulation text + Neo4j (Graph).

### Analyze Clinical Transcript
**Queue**: `celery` (default)
**Task Name**: `app.workers.transcript_tasks.analyze_clinical_transcript`

Handles strict HIPAA compliance analysis.

-   **Input**: Transcript text.
-   **Flow**:
    1.  **PHI Detection**: Presidio (CPU intensive).
    2.  **Report Generation**: LLM (Network/IO bound).
    3.  **Graph Ingestion**: Neo4j (IO bound).

---

## Configuration

The Celery app is configured via environment variables and `shorui_core.config`:

| Setting | Value (Default) | Description |
|---------|-----------------|-------------|
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Job queue |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Result storage |
| `worker_concurrency` | 2 | Concurrent tasks per worker |
| `task_acks_late` | True | Reliability (ack only after success) |

> Source: [celery_app.py](../app/workers/celery_app.py)
