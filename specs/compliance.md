# Compliance Module Specification

This document describes the compliance module architecture and implementation, which handles HIPAA compliance, PHI detection, and audit logging.

## Overview

The compliance module ensures that all processed clinical transcripts adhere to HIPAA regulations. It provides automated PHI detection, de-identification/masking, compliance reporting using LLMs, and a tamper-evident audit trail.

---

## Module Structure

-   `app/compliance/protocols.py`: Interface definitions (PHIDetector, AuditLogger, etc.)
-   `app/compliance/factory.py`: Component wiring & dependency injection
-   `app/compliance/routes.py`: API endpoints
-   `app/compliance/schemas.py`: Pydantic request/response models
-   `app/compliance/services/`:
    -   `privacy_extraction.py`: Orchestrator for PHI detection & analysis
    -   `phi_detector.py`: Presidio implementation
    -   `audit_service.py`: Audit logging implementation
    -   `compliance_report_service.py`: LLM-based reporting
    -   `hipaa_graph_ingestion.py`: Neo4j ingestion with pointer storage
    -   `hipaa_regulation_service.py`: Regulation indexing
    -   `regulation_retriever.py`: RAG for regulations

---

## Architecture

The module follows a **Protocol-Oriented Architecture** to allow for flexible backend implementations and easy testing.

### Protocols

Core capabilities are defined as Protocols in `protocols.py`:

-   **`PHIDetector`**: Detects 18 Safe Harbor identifiers.
    -   **Implementation**: `PHIDetector` (Presidio)
    -   **Source**: [protocols.py](../app/compliance/protocols.py)
-   **`AuditLogger`**: Logs tamper-evident audit events.
    -   **Implementation**: `AuditService`
    -   **Source**: [audit_service.py](../app/compliance/services/audit_service.py)
-   **`RegulationRetriever`**: Retrieves relevant HIPAA rules.
    -   **Implementation**: `RegulationRetriever`
    -   **Source**: [regulation_retriever.py](../app/compliance/services/regulation_retriever.py)
-   **`ComplianceReporter`**: Generates reports via LLM.
    -   **Implementation**: `ComplianceReportService`
    -   **Source**: [compliance_report_service.py](../app/compliance/services/compliance_report_service.py)
-   **`GraphIngestor`**: Stores metadata in Neo4j.
    -   **Implementation**: `HIPAAGraphIngestionService`
    -   **Source**: [hipaa_graph_ingestion.py](../app/compliance/services/hipaa_graph_ingestion.py)

### Factory Pattern

Dependencies are injected via factory functions in `factory.py`. This ensures that services like `PrivacyAwareExtractionService` simply declare their needs (e.g., `phi_detector: PHIDetector`) without coupling to concrete classes.
-   **Source**: [factory.py](../app/compliance/factory.py)

### Storage Abstraction

All secure storage operations (e.g., storing raw PHI text) use the `StorageBackend` protocol (shared with `ingestion`), allowing switching between MinIO (production) and LocalStorage (development) via configuration.

---

## API Endpoints

All endpoints are mounted under `/compliance`.

### Clinical Transcripts

-   **`POST /clinical-transcripts`**: Upload & analyze transcript (Async/Sync)
-   **`GET /clinical-transcripts/job/{job_id}`**: Check analysis job status
-   **`GET /clinical-transcripts/{id}/report`**: Get generated compliance report

### Audit Log

-   **`GET /audit-log`**: Query the HIPAA audit trail

### Regulations

-   **`GET /hipaa-regulations/stats`**: Get status of indexed regulations

-   **Source**: [routes.py](../app/compliance/routes.py)

---

## Pipeline

Clinical transcript processing follows this pipeline:

1.  **PHI Detection**: `PHIDetector` scans text for entities (Names, SSNs, etc.).
2.  **Audit Logging**: `AuditLogger` records the detection event.
3.  **Compliance Analysis**:
    -   `RegulationRetriever` fetches relevant HIPAA rules based on detected PHI.
    -   `ComplianceReporter` uses LLM + Rules to analyze violations and suggest redactions.
4.  **Graph Ingestion**: `GraphIngestor` stores:
    -   **Metadata/Structure** in Neo4j (Graph).
    -   **Raw PHI Text** in MinIO/S3 (Encrypted Blob).
    -   **Pointer** linking Graph Node → Blob.

---

## Services

### PrivacyAwareExtractionService

The main orchestrator. It coordinates the detection, logging, and analysis steps to produce a `PHIExtractionResult`.
-   **Source**: [privacy_extraction.py](../app/compliance/services/privacy_extraction.py)

### HIPAAGraphIngestionService

Handles the secure "Pointer-Based Storage" pattern. It ensures that sensitive text is never written to the graph database, only to the secure `StorageBackend`.
-   **Source**: [hipaa_graph_ingestion.py](../app/compliance/services/hipaa_graph_ingestion.py)

### AuditService

Provides a centralized logging mechanism for all compliance-sensitive events (`PHI_DETECTED`, `PHI_ACCESSED`, etc.).
-   **Source**: [audit_service.py](../app/compliance/services/audit_service.py)

---

## Async Processing

Long-running analysis is handled via Celery tasks in `app/workers/transcript_tasks.py`. The tasks use `app/compliance/factory.py` to instantiate services, ensuring consistent behavior with the API.

---

## Configuration

-   **`PHI_CONFIDENCE_THRESHOLD`**: Minimum confidence for Presidio detection
-   **`MINIO_BUCKET_ENCRYPTED`**: Secure bucket for PHI blobs
-   **`OPENAI_MODEL_ID`**: Model used for compliance analysis

