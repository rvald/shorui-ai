# Service Production Review (Strict) — Ingestion, RAG, Compliance, Workers, Core

This document applies the same “production-grade agentic systems” rubric to the non-agent services in this repo: ingestion, RAG, compliance, workers, and shared core infrastructure. It is intentionally strict and assumes HIPAA-adjacent expectations (PHI risk, auditability, retention controls).

Reviewed artifacts:
- `README.md`, `specs/*.md`
- Services: `app/ingestion/*`, `app/rag/*`, `app/compliance/*`, `app/workers/*`
- Core: `shorui_core/*`, `db/init-db.sql`, `docker-compose.yml`

---

## Executive Summary (High-Risk Gaps)

### 1) Payload handling violates production constraints
- The ingestion API reads full upload bytes into memory and enqueues them to Celery (`/ingest/documents` → `process_document.delay(file_content=...)`).
- This is unsafe and expensive: it increases PHI exposure surface, stresses Redis broker memory, and limits file size scalability.

### 2) “Compliance” outputs are not productized end-to-end
- Async transcript job status returns only a summary and uses placeholder transcript IDs.
- Compliance report retrieval endpoint is unimplemented (501).
- The system can produce reports internally but does not persist them as stable artifacts retrievable via API.

### 3) Audit trail claims are undermined by schema mismatch
- `db/init-db.sql` defines an append-only/tamper-evident `audit_events` schema (hash chain fields).
- `AuditService._ensure_table_exists()` creates a different `audit_events` schema at runtime.
- This mismatch will cause drift/bugs and prevents relying on the DB-level guarantees described in docs/specs.

### 4) “Encryption” and secure storage are largely aspirational
- Graph ingestion stores PHI/transcript content as JSON with comments indicating encryption should exist later.
- Docker-compose runs MinIO without TLS (`secure=false`) and uses default credentials.

### 5) Async interfaces frequently wrap synchronous I/O
- Multiple `async` functions perform sync network/DB calls (Neo4j driver sessions, psycopg connections, OpenAI client usage), creating event-loop blocking and unstable latency under load.

### 6) No service-level enforcement layer
- No authN/authZ, no rate limiting, no request size limits, no environment-specific policy enforcement (dev vs prod).
- Tenant boundaries are inconsistently enforced across services.

---

## Rubric Evaluation (Per Service)

### Ingestion Service (`app/ingestion`)

**Planning & task decomposition**
- Strength: clear “thin task” separation via Celery + orchestrator pattern.
- Gap: orchestration boundaries are not enforced via contracts (no stable artifact model, no storage pointer contract, no idempotency at API boundary).

**Tool use & orchestration**
- Current design queues raw bytes into Celery instead of queuing storage pointers.
- Storage upload failure is logged and processing continues (`IngestionOrchestrator.process()`), which can lead to “indexed but not stored” divergence.

**Memory & context management**
- No upload size limits or streaming; full file read into memory.
- PDF extraction uses temp files; no explicit cleanup policy besides temp deletion in some paths.

**Retrieval & grounding (as it relates to ingestion)**
- Metadata is inconsistent: `project_id` used as collection prefix sometimes (`project_{project_id}`), sometimes direct.
- Collection naming is not centralized (risk of cross-tenant collisions if patterns drift).

**Evaluation loops**
- No ingestion correctness tests that validate: idempotency behavior, storage pointer correctness, Qdrant payload schema.

**Guardrails & safety**
- Logs include filenames and project IDs; no PHI-safe logging policy.
- No auth controls on ingestion endpoints.

**Observability & feedback**
- No metrics: chunking time, embedding time, Qdrant upsert latency, failures per stage.

**Production tradeoffs**
- Current approach is simple and fast to build, but will not scale to large files and increases PHI risk.

---

### Workers (`app/workers`)

**Planning & task decomposition**
- Thin tasks exist; orchestration delegated to orchestrators.

**Tool use & orchestration**
- `@track_job_ledger` decorator computes content hash and attempts idempotency, but ledger semantics are overloaded:
  - `items_indexed` is used for different meanings (e.g., chunks created vs PHI detected).
  - Rich results (report pointers) are not persisted.
- Transcript task runs an async orchestrator using event loop reuse/new loop logic. This is fragile under Celery worker concurrency and can break in subtle ways.

**Memory & context**
- Passing full file payloads through broker is a critical scalability issue.

**Evaluation loops**
- No worker-level tests for retries, timeouts, DLQ correctness, idempotency semantics.

**Safety**
- No explicit redaction policy for error payloads stored in DLQ.

**Observability**
- No task-level metrics; Flower exists but does not replace structured tracing and metrics.

---

### RAG (`app/rag`)

**Planning & task decomposition**
- Pipeline structure exists (analyzer → expansion → vector search → graph → rerank → generator).
- However, responsibilities blur: generation is treated as part of “retrieval tool” output in some contexts, which reduces enforceability.

**Tool use & orchestration**
- Query analysis relies on OpenAI and uses fallbacks that can degrade retrieval quality silently.
- Graph retriever is `async` but uses sync Neo4j sessions (latent event-loop blocking).

**Memory & context management**
- RAG “context” is built as a large string; no token-aware truncation at boundary besides some truncations.
- No “source-of-truth” artifact schema (source IDs, hashes, immutability).

**Retrieval & grounding**
- Generator prompt allows answering from “general knowledge” when context is absent. For compliance-sensitive systems, this is unacceptable: it should return “insufficient sources” rather than speculate.
- Sources are returned by `/rag/query`, but downstream agent tooling may discard them, and there is no enforcement that answers include citations.

**Evaluation loops**
- No retrieval evals (nDCG/MRR), no prompt-injection tests for retrieved content, no hallucination detection gates.

**Safety**
- No policy boundary between “retrieved text” and “instructions”: injection risk is untreated.

**Observability**
- No retrieval stage metrics, no trace spans across Qdrant/Neo4j/OpenAI.

---

### Compliance (`app/compliance`)

**Planning & task decomposition**
- Orchestrator coordinates PHI detection → report generation → redacted ingestion → graph ingestion (in concept).
- The extraction service uses structured outputs (good direction).

**Tool use & orchestration**
- Compliance report generation exists but report persistence is not implemented as a stable artifact accessible by API.
- Graph ingestion uses pointer storage pattern, but encryption is not truly implemented; MinIO is not configured securely by default.

**Memory & context**
- Sensitive transcript text is handled directly in process memory; storage is performed as JSON blobs.
- No explicit retention policy for stored transcript blobs.

**Retrieval & grounding**
- Regulation retriever grounds compliance analysis in retrieved regulations (good), but there is no guarantee the underlying regulations corpus is complete, versioned, or immutable.

**Evaluation loops**
- No end-to-end verification: “extract PHI spans → audit log event → compliance report persisted → report retrievable”.
- No adversarial tests for PHI detection misses, false positives, or LLM output validation.

**Guardrails & safety**
- Audit trail is intended to be tamper-evident, but schema drift breaks that promise.
- Report retrieval endpoint is unimplemented; this encourages consumers to rely on transient outputs.

**Observability**
- No standardized audit correlation IDs linking: upload → job → transcript_id → report_id → graph nodes.

---

### Core / Infrastructure (`shorui_core`, `db`, `docker-compose.yml`)

**Planning & orchestration**
- Core provides singleton connectors (Qdrant/Neo4j/OpenAI/MinIO). Useful for simplicity but can create lifecycle issues.

**Safety**
- Docker-compose uses default credentials, exposes ports broadly, and MinIO runs without TLS.
- Settings provide defaults appropriate for local dev but unsafe for production.

**Observability**
- Loguru is configured but there’s no PHI-safe logging policy enforcement.
- No tracing/metrics integration (OpenTelemetry).

**Production tradeoffs**
- Singleton connectors reduce overhead but complicate multi-tenant isolation, testing, and connection lifecycle management.
- Runtime “auto-migrations” in services are convenient but create drift and unpredictability; prefer explicit migrations.

---

## Refactoring Recommendations (Patterns + Reasoning + Tradeoffs)

### P0: Change the “unit of work” to **artifact pointers**, not raw payloads

**Recommendation**
- On upload endpoints:
  1) stream file to object storage (MinIO/S3)
  2) enqueue Celery task with `{job_id, project_id, storage_pointer, metadata}`
- Workers download the payload from storage when needed.

**Patterns used**
- **Outbox/Pointer-based workflows**: queue references, not data.
- **Idempotency keys**: content hash stored in DB keyed by tenant/project.

**Why**
- Prevents Redis broker overload and reduces PHI propagation surface.
- Enables large file support and better resilience (retries don’t resend bytes).

**Tradeoffs**
- Requires object storage availability for ingestion path.
- Needs stronger lifecycle controls for stored objects (TTL, deletion, encryption).

---

### P0: Make audit logging real: **single schema + migrations + hash chain**

**Recommendation**
- Choose one `audit_events` schema (prefer `db/init-db.sql` tamper-evident version).
- Remove runtime schema creation from `AuditService` (or gate it to dev-only).
- Enforce append-only semantics and compute/store `event_hash` and `previous_hash`.

**Patterns used**
- **Write-ahead audit ledger** (append-only, hash chained).
- **Migrations-as-code** (Alembic or equivalent) instead of runtime DDL.

**Why**
- HIPAA-grade auditability requires predictable schema and tamper evidence.

**Tradeoffs**
- Adds migration tooling and operational discipline.
- Requires careful performance indexing and retention strategy.

---

### P0: Implement “report as artifact” end-to-end

**Recommendation**
- Persist compliance results:
  - `transcripts` table (metadata + pointer to encrypted blob)
  - `compliance_reports` table (report JSON + linkage to transcript_id + versioning)
- Implement `GET /compliance/clinical-transcripts/{id}/report`.
- Update job ledger to store `result_pointer` (or `report_id`) rather than overloading `items_indexed`.

**Patterns used**
- **Artifact store** (immutable-ish records with IDs).
- **Eventual consistency** between async tasks and API retrieval.

**Why**
- Makes the system usable as a product: clients can retrieve stable outputs reliably.
- Enables evaluation, replay, and audits.

**Tradeoffs**
- Requires schema design, migrations, and storage capacity planning.

---

### P1: Build a shared **Service Runtime** layer (timeouts, retries, budgets, correlation IDs)

**Recommendation**
- Introduce a small shared runtime library in `shorui_core`:
  - HTTP client wrapper (httpx async) with retries/backoff, circuit breakers.
  - DB wrapper with pooling + explicit timeouts.
  - Correlation ID propagation for all requests and logs.

**Patterns used**
- **Bulkheads + circuit breakers** for downstream dependencies.
- **Budget propagation** (deadlines, max retries, max concurrency).

**Why**
- Services today fail “loudly and inconsistently” with little telemetry.
- A single runtime layer prevents ad hoc reliability code.

**Tradeoffs**
- Initial complexity and refactor cost.
- Requires consistent adoption across services to pay off.

---

### P1: Make “grounding enforceable” in RAG

**Recommendation**
- Separate retrieval and generation contracts:
  - Retrieval returns structured sources.
  - Generation must cite sources; if sources are empty → “insufficient information”.
- Remove “answer from general knowledge if no context” behavior in compliance-sensitive paths.
- Add prompt-injection hygiene for retrieved text.

**Patterns used**
- **Defense-in-depth grounding**: retrieve → cite → validate.
- **Untrusted data handling**: retrieved content treated as untrusted input.

**Why**
- Prevents hallucinated CFR citations and unsafe compliance advice.

**Tradeoffs**
- Some answers become “I don’t know” until corpus is complete.
- Requires product alignment that accuracy beats coverage.

---

### P2: Evaluation loops and operational excellence

**Recommendation**
- Add per-service eval suites:
  - ingestion: indexing correctness + idempotency + payload schema
  - rag: retrieval quality + injection resilience
  - compliance: PHI detection coverage + structured output validation + report persistence
  - workers: retry/DLQ correctness + timeouts
- Add OpenTelemetry tracing + metrics (latency, errors, queue depth).

**Patterns used**
- **Contract tests** between services (schemas and invariants).
- **Golden tests** for high-stakes flows.

**Why**
- You can’t safely iterate on LLM and retrieval logic without regression protection.

**Tradeoffs**
- Requires test data management (especially PHI-safe synthetic data).
- Adds CI runtime cost.

---

## Suggested Refactor Sequence (Low-Risk, Highest ROI)

1) **Stop sending bytes through Celery**: upload to storage, enqueue pointers.
2) **Unify audit schema**: remove runtime DDL drift; implement hash-chain or drop the claim.
3) **Persist compliance reports** and implement report retrieval endpoint.
4) **Standardize job ledger semantics**: result pointers, typed fields, consistent meaning.
5) **Enforce grounding in RAG**: retrieval artifacts + citation enforcement; remove “general knowledge” mode for compliance.
6) **Introduce shared runtime**: timeouts/retries/budgets/correlation IDs.
7) Add tracing/metrics + regression suites.

