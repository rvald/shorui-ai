# Component Spec: Service Runtime (Timeouts, Retries, Budgets, Correlation IDs)

This spec defines a shared “service runtime” layer in `shorui_core` used by all modules (ingestion, RAG, compliance, agents) to standardize reliability and operational safety: timeouts, retries/backoff, circuit breakers, budgets, and correlation IDs.

Status: Proposed (P1)

---

## 1) Problem Statement

Today, each module makes ad hoc DB/network calls with:
- inconsistent timeouts and retry behavior,
- limited correlation across services,
- insufficient metrics and structured errors,
- event-loop blocking risk from sync calls in async paths.

---

## 2) Goals

P1:
- Standardized outbound HTTP client (async, pooled).
- Standardized error model (retryable vs terminal, safe vs debug messages).
- Correlation ID propagation (`request_id`, `job_id`) across HTTP/task boundaries.
- Budget propagation (deadline, max retries, max tool calls).

P2:
- Circuit breakers, bulkheads, hedging for critical paths.
- Centralized rate limiting and tenant quotas hooks.

---

## 3) Runtime Interfaces (Logical)

### Request Context
`RunContext = {request_id, tenant_id, project_id, user_id?, deadline, budgets, policy_profile}`

### HTTP Client wrapper
- `get_http_client()` returns a shared `httpx.AsyncClient` with:
  - connection pooling
  - default timeouts
  - retry policy hooks
  - automatic headers: `X-Request-Id`, `X-Tenant-Id`, `X-Project-Id`

### Retry Policy
- exponential backoff + jitter
- max attempts per operation
- retry only on safe classes (timeouts, 429/5xx, connection errors)

### Error Model
`ServiceError = {code, message_safe, message_debug, retryable, cause, debug_id}`

---

## 4) Implementation Constraints

- Must be usable from sync and async contexts:
  - async-first implementation with sync adapters where needed.
- Must not log sensitive content by default (PHI-safe logging).

---

## 5) Observability

P1 minimum:
- Metrics:
  - request latency (p50/p95/p99)
  - outbound HTTP latency by service
  - retries, timeouts, error codes
- Traces:
  - spans around outbound calls and queue boundaries

---

## 6) Acceptance Criteria

P1:
- All service-to-service HTTP calls go through the runtime wrapper.
- Correlation IDs appear consistently in logs/traces.
- Standardized error classification drives retry decisions.

---

## 7) Open Questions

1) Do you prefer OpenTelemetry from the start, or a minimal internal tracing format first?
2) Should retry policy be global or per-service/per-endpoint configurable?

