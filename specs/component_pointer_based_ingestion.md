# Component Spec: Pointer-Based Ingestion (Production Hardening)

This spec defines a production-grade ingestion workflow that avoids moving raw document bytes through the task queue, enforces tenant boundaries, and provides stable artifacts that downstream services (RAG/Compliance/Agents) can rely on.

Status: Proposed (targeting P0 hardening)

---

## 1) Problem Statement

Current ingestion queues raw file bytes through Celery (`/ingest/documents` → `process_document.delay(file_content=...)`). This:
- Does not scale to large files (broker memory/throughput).
- Expands PHI exposure surface (raw content copied into broker/task payloads/logs).
- Makes idempotency and replay harder (payloads are not stable artifacts).
- Produces incomplete “job result” semantics (no standardized result pointers).

We need an ingestion design where:
- The API stores uploads in an artifact store (MinIO/S3) and enqueues only pointers.
- Workers operate on artifact pointers and produce deterministic result artifacts.
- The job ledger becomes a stable source of truth for status and result references.

---

## 2) Scope / Non-Scope

### In Scope
- Document ingestion entrypoint (`POST /ingest/documents`) and worker task input shape.
- Artifact storage contract (raw upload pointers, processed pointers).
- Job ledger semantics: status, idempotency, result pointers, error reporting.
- Upload limits, validation, and PHI-safe logging requirements for ingestion.
- Backwards-compatible rollout plan from “bytes-in-queue” to “pointers-in-queue”.

### Non-Scope (separate specs)
- Audit ledger/tamper evidence (see `specs/component_audit_ledger.md`).
- AuthN/AuthZ and tenant identity model (see `specs/component_auth_tenant_isolation.md`).
- RAG retrieval/generation contract changes.
- Compliance transcript/report persistence.

---

## 3) Current State (Observed)

### API
- `POST /ingest/documents` reads full file into memory and calls `process_document.delay(...)` with raw bytes.
- The response returns only `job_id`.
- Status endpoint reads from job ledger (`jobs` table).

### Worker
- `process_document` takes `file_content: bytes` and delegates to `IngestionOrchestrator`.
- `IngestionOrchestrator` attempts MinIO upload but may continue processing on upload failure.
- Ledger decorator (`@track_job_ledger`) computes content hashes and creates a job record, but result fields are overloaded.

### Storage
- MinIO is used for raw/processed buckets; local storage exists for dev.
- No explicit TTL/cleanup for uploaded artifacts.

---

## 4) Design Goals & Requirements

### P0 (Launch Blockers)
1) **No raw bytes in Celery payloads**
- Celery tasks must receive `{storage_pointer, filename, content_type, project_id, …}` not file bytes.

2) **Deterministic artifact model**
- Every ingestion run produces stable pointers to:
  - raw uploaded object (immutable)
  - processed object(s) (optional)
  - index result summary artifact (JSON)

3) **Tenant boundary enforcement**
- All artifacts are stored under `tenant_id/project_id` namespaces.
- `tenant_id` is enforced internally even before AuthN/AuthZ ships:
  - Public API continues to accept only `project_id` initially.
  - The service MUST resolve `tenant_id` server-side (e.g., from a known project-to-tenant mapping or identity principal) and persist it everywhere (ledger, storage paths, idempotency keys, task payloads). No "default" fallback is permitted.

4) **PHI-safe logging**
- No logging of raw content or extracted text.
- Filenames should be treated as sensitive; log only safe metadata (size, content_type) unless explicitly permitted by policy.

5) **Hard limits**
- Request size limits and content type allowlists at API boundary.

### P1 (Reliability / Ops)
- Retry semantics: worker retries must be safe (idempotent).
- DLQ entries must not include raw payloads.
- Storage failures are fatal (no “upload failed but continue indexing”).

### P2 (Optimization)
- Streaming upload support (avoid buffering whole file in memory).
- Chunking/embedding concurrency controls and cost accounting.

---

## 5) Proposed Architecture

### Overview
**API Path**
1) Validate request (size/type/tenant).
2) Upload raw bytes to object storage → `raw_pointer`.
3) Create job in ledger with `raw_pointer` + `content_hash`.
4) Enqueue Celery task with `job_id` + `raw_pointer` + metadata.
5) Return `202` with `job_id`.

**Worker Path**
1) Load job record; set status `processing`.
2) Download raw artifact by `raw_pointer`.
3) Process according to `document_type`:
   - general: extract→chunk→embed→index
   - hipaa_regulation: extract→chunk→index to regulations collection (+ optional graph)
4) Persist a **result artifact** (JSON) to object storage → `result_pointer`.
5) Update ledger status `completed` with `result_pointer`, stats, and optional processed pointers.

---

## 6) Contracts

### 6.1 API: `POST /ingest/documents`

**Request**
- Multipart `file`
- Form fields:
  - `project_id: string`
  - `document_type: "general" | "hipaa_regulation"`
  - `index_to_vector: bool`
  - `index_to_graph: bool`
  - optional regulation metadata: `source`, `title`, `category`

**Response (202)**
```json
{
  "job_id": "uuid",
  "message": "queued",
  "raw_pointer": "bucket/path/object" // optional exposure; can omit in public API
}
```

**Notes**
- `tenant_id` is not required in the public request initially; it is derived server-side (temporary until `specs/component_auth_tenant_isolation.md` is implemented).
- `raw_pointer` should be omitted from the public API if it becomes security-sensitive; keep it internal in ledger.

**Tenant derivation (Global Policy)**
- `tenant_id` must be explicitly resolved from the identity or project context. Anonymous or "default" fallback is forbidden.

### 6.2 API: `GET /ingest/documents/{job_id}/status`

**Response**
```json
{
  "job_id": "uuid",
  "status": "pending|processing|completed|failed|skipped",
  "progress": 0,
  "error": null,
  "result": {
    "result_pointer": "bucket/path/result.json",
    "items_indexed": 1234,
    "collection_name": "project_foo",
    "storage_pointers": {
      "raw": "raw/...",
      "processed": "processed/..." 
    }
  }
}
```

### 6.3 Celery Task Input (New)

`process_document(job_id, tenant_id, project_id, raw_pointer, filename, content_type, document_type, ...)`

Explicitly forbidden:
- `file_content: bytes` in task args/kwargs.

---

## 7) Data Model Changes (Ledger)

### 7.1 Jobs/Artifacts schema

Use canonical `jobs` and `artifacts` tables:
- `jobs`: tenant_id, project_id, job_type, status, progress, idempotency_key, request_id, raw_pointer, result_pointer, processed_pointer, content_type, document_type, byte_size, items_indexed, timestamps.
- `artifacts`: tenant_id, project_id, artifact_type, storage_backend, storage_pointer, content_type, byte_size, sha256, schema_version, created_by_job_id.

`items_indexed` retains a single meaning: “count of indexed vector points” (or chunk count) for ingestion jobs. Compliance PHI counts must not overload this column (tracked elsewhere).

### 7.2 Idempotency semantics

Idempotency key = SHA-256 of raw bytes + `tenant_id` + `project_id` + `document_type` (+ possibly `content_type`).

Rules:
- If an existing job with same key is `completed`, return `skipped` with `existing_job_id` and/or `result_pointer`.
- If existing job is `processing/pending`, either:
  - return the existing job ID (preferred), or
  - create a new job but point to same `raw_pointer` (not preferred).

---

## 8) Storage & Security Requirements

1) **Object storage namespace**
- Store objects under `tenant_id/project_id/` now.
- Example:
  - raw: `raw/{tenant_id}/{project_id}/{uuid}_{filename}`
  - results: `results/{tenant_id}/{project_id}/{job_id}.json`

2) **Encryption**
- Production: encrypted at rest + TLS in transit for MinIO/S3.
- Dev: local storage allowed, but must maintain the same pointer contract.

3) **Retention**
- Raw uploads: configurable TTL by environment (dev short, prod policy-driven).
- Result artifacts: longer retention; versioned if schema changes.

4) **Access control**
- Only workers/services with appropriate role can read raw pointers.
- Public APIs should not expose raw pointers unless authorized and necessary.

---

## 9) Observability

Minimum P0:
- Generate `request_id` per API call; store in ledger; include in logs.
- Record stage timing in result artifact (extract_ms, embed_ms, index_ms).

P1:
- Metrics: upload size distribution, task durations, Qdrant upsert latency, error rates, retries, DLQ volume.
- Traces: propagate `request_id` to Celery task headers and downstream calls.

---

## 10) Failure Modes & Handling

1) Storage upload fails (API)
- Fail request (`500` or `503`) and do not enqueue task.

2) Storage download fails (worker)
- Mark job failed; include safe error code; retry if transient.

3) Qdrant indexing fails
- Mark job failed; do not mark completed; retry with idempotency (upserts are idempotent if point IDs stable; if not, record a run-specific namespace).

4) Partial success (indexed but result artifact failed to store)
- Treat as failed; safe retry must not duplicate indexes (requires stable point IDs or dedupe strategy).

---

## 11) Rollout Plan (Backwards Compatible)

Phase 0: Prep
- Add new DB columns and release.
- Add storage pointer write path in API (still also sending bytes to queue temporarily).

Phase 1: Dual-write
- API uploads to storage and enqueues pointer + bytes (temporary).
- Worker prefers pointer; falls back to bytes if pointer missing (temporary).

Phase 2: Pointer-only
- Remove bytes from Celery payload.
- Reject tasks that include raw bytes (guardrail).

Phase 3: Cleanup
- Remove fallback code paths.
- Enforce retention TTL cleanup job for raw uploads.

---

## 12) Acceptance Criteria

P0 acceptance:
- No Celery task contains raw file bytes in arguments/kwargs.
- A successful ingestion job produces:
  - `raw_pointer` stored in ledger
  - `result_pointer` stored in ledger
  - `status=completed`
- If storage upload fails, the API does not enqueue a task.
- If storage upload succeeds but worker fails, job is `failed` and DLQ entry contains no raw content.

P1 acceptance:
- Idempotent re-uploads with same content return `skipped` and reference prior `result_pointer`.
- Metrics exist for ingestion latency and failure rates.
