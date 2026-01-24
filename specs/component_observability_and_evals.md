# Component Spec: Observability & Evaluation (Production Agentic System)

This spec defines production-grade observability (tracing/metrics/logging) and evaluation loops (offline regression + online signals) across the full system, not just the agent.

Status: Proposed (P1/P2)

---

## 1) Problem Statement

The system lacks:
- end-to-end correlation IDs and distributed tracing,
- actionable metrics (latency, error rates, queue depth, token/cost),
- systematic evaluation loops (grounding, PHI leakage, retrieval quality, regression).

Without this, production incidents are hard to debug and correctness/safety regressions will go unnoticed.

---

## 2) Goals

P1:
- Correlated logs and traces across: API → workers → storage → DBs → LLM.
- Metrics for ingestion, compliance, RAG, and agent runtime.

P2:
- Continuous evaluation harness with CI gates and “canary” online checks.

---

## 3) Logging Policy (PHI-Safe)

Rules:
- Never log raw transcript text, PHI spans, or retrieved content.
- Log only:
  - `request_id`, `job_id`, `tenant_id`, `project_id`
  - lengths/sizes, counts, durations, error codes
- Sensitive strings (filenames) are either omitted or hashed by policy.

---

## 4) Tracing (Recommended: OpenTelemetry)

### Required spans
- inbound request span (FastAPI)
- job enqueue span
- worker execution span
- outbound spans to:
  - Postgres
  - MinIO
  - Qdrant
  - Neo4j
  - OpenAI/RunPod

### Required propagation
- `request_id` in headers and Celery task headers.

---

## 5) Metrics (Minimum Set)

### Ingestion
- upload sizes (histogram)
- task durations by stage
- indexing throughput (points/sec)
- failures by stage

### Compliance
- PHI spans detected distribution
- LLM call latency + failures
- report generation latency

### RAG
- retrieval latency
- empty-retrieval rate
- citation compliance rate (if enforced)

### Workers
- queue depth
- retry counts
- DLQ volume

### Cost
- LLM token usage by endpoint/tenant (where available)

---

## 6) Evaluation Loops

### Offline regression (CI)
- ingestion: idempotency + pointer contract + schema checks
- compliance: structured output validation + report persistence + PHI redaction invariants
- rag: retrieval-only correctness + injection resilience + “no sources ⇒ no answer”
- agent: tool selection + refusal correctness + no sensitive leakage

### Online signals (prod)
- citation presence rate
- empty retrieval rate
- error budgets (SLOs)
- anomaly detection on PHI counts and latency

---

## 7) Acceptance Criteria

P1:
- Every request/job has `request_id` and is traceable across services.
- Core metrics are exported and queryable.
- PHI-safe logging policy is enforced in code review and by lint/checks where feasible.

---

## 8) Open Questions

1) What metrics backend do you prefer (Prometheus/OpenTelemetry Collector/Datadog)?
2) Do you want eval gating strictness in CI from day one (block merges) or phased (warn-only → block)?

