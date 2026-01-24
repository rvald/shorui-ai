# Component Spec: Audit Ledger (Tamper-Evident, Production-Grade)

This spec standardizes HIPAA-adjacent audit logging across services. It resolves schema drift, defines required audit events, and specifies tamper-evident storage semantics (hash chaining) with explicit migrations.

Status: Proposed (P0)

---

## 1) Problem Statement

Audit logging currently has conflicting schemas and unclear guarantees:
- `db/init-db.sql` defines a hash-chained append-only `audit_events` schema.
- `AuditService` creates a different `audit_events` table at runtime.
- This drift breaks “tamper-evident audit trail” claims and makes querying/retention unpredictable.

---

## 2) Goals

P0:
- Single audit schema and explicit migrations (no runtime DDL).
- Append-only semantics and tamper evidence.
- Minimal PHI exposure: audit descriptions/metadata must be PHI-safe by policy.

P1:
- Correlation across request → job → artifact → graph/vector entries via `request_id`, `job_id`.

P2:
- Optional external WORM storage export; cryptographic signing; retention enforcement tooling.

---

## 3) Audit Event Model

### Required fields
- `id` (UUID)
- `sequence_number` (monotonic per table)
- `event_type` (enum)
- `timestamp` (UTC)
- `tenant_id`, `project_id`
- `user_id` (nullable until AuthN is implemented)
- `user_ip` (optional, careful with privacy policy)
- `resource_type`, `resource_id`
- `metadata` (JSON, PHI-safe)
- `previous_hash` (nullable for first event)
- `event_hash` (hash of this event + previous_hash)

### PHI safety rules
- Audit entries MUST NOT store raw transcript text, PHI spans, or unredacted filenames by default.
- Store counts, IDs, and pointers/handles; if filenames are needed, store a hashed/normalized form.

---

## 4) Tamper-Evidence

### Hash chaining algorithm (recommended)
- Canonical serialization of event fields (stable key order).
- `event_hash = sha256(previous_hash || canonical_json(event_fields_without_hashes))`

Operational notes:
- Writes must be serialized to ensure correct chain ordering.
- Use a DB transaction that:
  1) reads last `event_hash`
  2) inserts new row with `previous_hash=last_hash` and computed `event_hash`

---

## 5) API / Service Contract

### `AuditLogger` interface (logical)
- `log(event_type, description, resource_type, resource_id, user_id, tenant_id, project_id, metadata)`
- `query_events(filters..., tenant_id, project_id, limit)`

Rules:
- All calls require `tenant_id` and `project_id` (derived server-side until auth exists).
- `metadata` is validated against allowlisted keys.

---

## 6) Required Event Types (Minimum)

P0 minimum:
- `PHI_DETECTED` (count + transcript_id)
- `PHI_ACCESSED` (who accessed + artifact handle; no PHI content)
- `TRANSCRIPT_UPLOADED` (job_id + byte_size)
- `COMPLIANCE_REPORT_GENERATED` (report_id + transcript_id + risk level)
- `DOCUMENT_INGESTED` (job_id + doc_type + points indexed)

---

## 7) Migration Plan

P0:
- Choose the canonical schema (recommend using `db/init-db.sql` as source of truth).
- Remove or dev-gate runtime DDL creation in `AuditService`.
- Add migrations tooling (Alembic recommended) and codify schema.
- Backfill strategy:
  - If there is existing data in the “wrong” table, migrate it or drop it explicitly in dev.

---

## 8) Acceptance Criteria

P0:
- Only one `audit_events` schema exists in production.
- Runtime does not issue `CREATE TABLE` for audit.
- Every audit row has valid `previous_hash`/`event_hash` chain, verifiable offline.
- Audit log entries are PHI-safe by policy (no raw text).

---

## 9) Open Questions

1) Do you require strict hash-chaining from day one, or is “append-only + restricted access” acceptable initially?
2) Should audit queries be exposed publicly, or only as admin/operator endpoints?

