# Component Spec: Artifacts & Jobs (Canonical Model)

This spec defines the canonical “job” and “artifact” model used across ingestion, compliance, RAG, and agents. It standardizes identifiers, storage pointers, result pointers, and status semantics so the system can be production hardened incrementally with consistent contracts.

Status: Proposed

---

## 1) Problem Statement

Today, “job” semantics are overloaded and inconsistent:
- Raw content may be queued through Celery.
- `items_indexed` is reused for unrelated meanings.
- Jobs do not reliably reference stable result artifacts (reports, index summaries).
- Different modules generate IDs (job_id, transcript_id, report_id) with weak linkage/correlation.

This causes operational ambiguity (“what did we produce?”), makes retries unsafe, and blocks reliable retrieval, auditing, and evaluation.

---

## 2) Goals

P0:
- Canonical job lifecycle and status semantics shared by all async workloads.
- Canonical artifact model with stable pointers and metadata.
- Strong tenant boundary enforcement (`tenant_id`, `project_id`).

P1:
- Deterministic idempotency keys and dedup behavior.
- Replayability (re-run from artifact pointers without re-upload).

P2:
- Versioning of artifacts and schemas; immutability where needed.

---

## 3) Definitions

### Job
An asynchronous unit of work tracked in a ledger.

### Artifact
An immutable or append-only output/input referenced by an ID and stored in an artifact store (object storage, DB blob, etc.).

### Pointer
A string that locates an artifact in storage (e.g., `bucket/path/object`), not necessarily globally dereferenceable by clients.

---

## 4) Canonical IDs

All IDs are UUIDs unless specified.
- `tenant_id`: string (auth-bound later; default `"default"` for now)
- `project_id`: string (tenant-scoped namespace)
- `job_id`: UUID (job ledger primary key)
- `artifact_id`: UUID (artifact registry primary key, optional but recommended)

Domain-specific IDs (examples):
- `transcript_id`: UUID
- `report_id`: UUID

Rule: any domain ID must have an explicit foreign key linkage to the job that produced it (directly in DB or via artifact metadata).

---

## 5) Canonical Job Status Model

### Status enum
- `pending`: accepted/enqueued but not started
- `processing`: worker started; progress updates allowed
- `completed`: finished successfully; result pointers exist
- `failed`: terminal failure; safe error recorded; DLQ entry may exist
- `skipped`: idempotent short-circuit; references existing results

### Required job fields (logical)
- `job_id`, `tenant_id`, `project_id`
- `job_type` (e.g., `ingestion_document`, `compliance_transcript`)
- `status`, `progress` (0–100)
- `created_at`, `updated_at`, `completed_at`, `failed_at`
- `idempotency_key` (nullable for non-idempotent jobs)
- `input_artifacts[]` (pointers or artifact_ids)
- `result_artifacts[]` (pointers or artifact_ids)
- `error_code`, `error_message_safe`, `error_debug_id` (for correlation)
- `request_id` (correlation/tracing)

---

## 6) Canonical Artifact Model

### Artifact fields (logical)
- `artifact_id`
- `tenant_id`, `project_id`
- `artifact_type`: enum/string (e.g., `raw_upload`, `redacted_text`, `compliance_report`, `rag_retrieval_result`, `index_summary`)
- `storage_backend`: enum (`minio`, `local`, `postgres`, …)
- `storage_pointer`: string (opaque to clients by default)
- `content_type`: string (e.g., `application/pdf`, `application/json`)
- `byte_size`: int
- `sha256`: optional (for dedupe/integrity)
- `schema_version`: optional (for JSON artifacts)
- `created_at`
- `created_by_job_id`: optional

### Artifact immutability rules
- Artifacts are immutable once written.
- “Updates” create a new artifact with a new `artifact_id` and link via metadata if needed.

---

## 7) Storage Pointer Semantics

- Pointer format is backend-specific but must include namespace:
  - `/{tenant_id}/{project_id}/...` (or equivalent).
- Pointers must be treated as sensitive.
- Public APIs should generally return **artifact IDs** or domain IDs, not raw pointers.

---

## 8) Idempotency

### Idempotency key construction
`idempotency_key = sha256(input_bytes) + tenant_id + project_id + job_type + (optional parameters that change behavior)`

Rules:
- If a `completed` job exists with the same idempotency_key, new requests return `skipped` referencing existing job/result artifacts.
- If a `pending/processing` job exists, return the existing `job_id` (preferred).

---

## 9) DB/Migration Strategy (High Level)

This spec does not prescribe a single DB schema, but expects:
- Job ledger tables per domain or a unified `jobs` table.
- Optional artifact registry table (`artifacts`) if we want first-class artifact tracking.
- Migrations are explicit (no runtime DDL).

### Recommended Baseline (Revised)
- **Unified Jobs Table**: Use a single `jobs` table with a `job_type` discriminator. This ensures consistent observability, retry logic, and ledger management across all domains (ingestion, compliance, RAG).
- **Artifacts Table**: Use a first-class `artifacts` table immediately to track all inputs and outputs (raw uploads, redacted text, reports). This avoids overloading job tables with storage pointers.

---

## 10) Acceptance Criteria

P0:
- Every async task/job has a single canonical job record with status + result pointer(s).
- Every job and artifact is namespaced by `tenant_id` and `project_id`.
- No result is “only in memory”; clients can fetch completed job results via stable IDs.

---

## 11) Open Questions

1) Do you prefer a unified `jobs` table for all job types, or separate tables per domain (ingestion/compliance) with a shared interface?
2) Do you want a first-class `artifacts` table now (recommended), or keep pointers embedded in domain tables initially?

### Defaults (Updated)
- Job tables: **Unified `jobs` table**.
- Artifacts table: **First-class `artifacts` registry** table.
