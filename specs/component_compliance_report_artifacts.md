# Component Spec: Compliance Report Artifacts (Persistence + Retrieval)

This spec makes compliance outputs stable, retrievable artifacts rather than transient in-memory results. It defines how transcripts and compliance reports are stored, linked to jobs, and served via APIs.

Status: Proposed (P0/P1)

---

## 1) Problem Statement

The compliance pipeline can generate PHI spans and a report, but:
- `GET /compliance/clinical-transcripts/{transcript_id}/report` is unimplemented.
- Async job status returns a placeholder transcript ID and no real report retrieval.
- Results are not persisted in a durable, queryable way.

---

## 2) Goals

P0:
- Persist compliance report as an artifact and implement report retrieval endpoint.
- Persist transcript metadata and pointer to encrypted transcript blob.
- Ensure results are tenant/project scoped.

P1:
- Store redacted transcript (optional) for RAG indexing with provenance metadata.
- Versioning of report schema and model version.

---

## 3) Data Model (Logical)

### Transcript record
- `transcript_id` (UUID)
- `tenant_id`, `project_id`
- `filename` (optional; consider hashed form)
- `storage_pointer` (encrypted blob pointer)
- `byte_size`, `text_length`
- `file_hash` (sha256)
- `created_at`
- `created_by_job_id`

### Compliance report record
- `report_id` (UUID)
- `tenant_id`, `project_id`
- `transcript_id` (FK)
- `overall_risk_level`
- `total_phi_detected`, `total_violations`
- `report_json` (JSONB) OR `report_pointer` (object storage) depending on size
- `schema_version`
- `model_id`/`prompt_version` (for provenance)
- `generated_at`
- `created_by_job_id`

---

## 4) API Contracts

### `POST /compliance/clinical-transcripts`
Unchanged at the boundary, but must:
- Create a job record and transcript record (or reserve transcript_id early).
- Ensure the job result includes `transcript_id` and `report_id` or pointers.

### `GET /compliance/clinical-transcripts/job/{job_id}`
Must return:
- `transcript_id` and (when completed) `report_id` or report summary.

### `GET /compliance/clinical-transcripts/{transcript_id}/report`
Must:
- Verify tenant/project authorization.
- Return the persisted report (not “regenerate”).

---

## 5) Storage & Security

- Transcript text stored encrypted at rest; pointer stored in DB.
- Report content may include PHI-derived findings; treat as sensitive. Prefer storing as JSONB with encryption-at-rest at DB layer or store as encrypted object.
- Retention policy per environment.

---

## 6) Observability & Audit

Required audit events:
- `TRANSCRIPT_UPLOADED`
- `PHI_DETECTED` (counts)
- `COMPLIANCE_REPORT_GENERATED` (risk level + IDs)
- `PHI_ACCESSED` when report/transcript content is retrieved

---

## 7) Acceptance Criteria

P0:
- Completed compliance job yields stable `transcript_id` and `report_id`.
- `GET .../{transcript_id}/report` returns 200 with persisted report.
- Job status endpoint returns real IDs (no placeholders).

---

## 8) Open Questions

1) Should the report be stored in Postgres (JSONB) or object storage (pointer) by default?
2) Do you want report redaction (e.g., no raw PHI spans) as a hard requirement for the API response?

### Defaults (least effort, v1)
- Store reports in **Postgres JSONB** by default for simplest retrieval and implementation.
- Redaction: **do not include raw PHI spans in API responses by default**; return counts and stable IDs, and treat detailed PHI as restricted access (upgrade path can add privileged views).

Upgrade path:
- If report size or security posture demands it, store the report as an encrypted object (`report_pointer`) and keep only metadata + pointer in Postgres.
