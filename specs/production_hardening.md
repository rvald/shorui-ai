# Production Readiness Review & Hardening Checklist (Strict)

This document captures production-readiness gaps observed in the current Shorui AI agent system and a prioritized hardening checklist. It is intentionally strict and assumes HIPAA-adjacent operational expectations (PHI risk, auditability, retention, access control).

Scope reviewed:
- Specs: `specs/*.md`
- Agent API + runtime: `app/agent/*`, `agents/react_agent/*`
- RAG + Compliance integration points: `app/rag/*`, `app/compliance/*` (as they relate to grounding, tool I/O, and transcript handling)

---

## Executive Summary (Blockers)

These items should be treated as launch blockers for any environment that may process PHI.

1) **Chain-of-thought + tool output exposure to end users**
- The agent API returns `steps[].thought` and `steps[].observation` derived from model messages and tool messages.
- This can leak sensitive data (PHI), internal reasoning, system prompt behavior, tool error details, and security-sensitive operational data.
- A production-safe agent should not expose raw reasoning traces by default.

2) **Unsafe file handling enables arbitrary local file reads**
- The model is instructed to call `analyze_clinical_transcript` with “the file path”.
- The tool opens whatever path it is given.
- This creates a path exfiltration class vulnerability: if the model can be induced to pass an arbitrary path, the system can read local files and transmit contents to downstream services.

3) **PHI leakage via logs**
- User content is logged (message prefixes) and transcript metadata is logged.
- In HIPAA contexts, logging prompt/body content is typically disallowed unless redacted, access-controlled, and retained under policy.

4) **Async correctness / throughput risks**
- Blocking calls (`time.sleep`, sync HTTP, sync LLM invoke) run on async request paths.
- Under load this can stall the event loop, degrade latency, and cause cascading failures.

5) **Memory persistence lacks retention, minimization, and size controls**
- Redis checkpointing persists conversation history with no TTL, truncation, summarization, encryption model, or PHI retention policy.

6) **Grounding is structurally weak**
- The agent consumes a RAG endpoint that itself generates an answer via an LLM, but the agent doesn’t receive or enforce structured citations/sources.
- This increases hallucination and compliance risk.

---

## Findings by Rubric

### 1) Planning & task decomposition

Observed:
- The runtime graph is the minimal ReAct loop (agent ↔ tools) with no explicit planning node or plan validation.
- An “iterations” counter exists in state but is not enforced as a hard stop.
- The prompt encourages “reasoning before action” but this is not safely routed to internal-only telemetry; it becomes user-visible in current API design.

Production gaps:
- No deterministic budget controls (max tool calls, max wall-clock, max tokens).
- No explicit “plan → execute → verify” structure for high-stakes tasks (compliance analysis).
- No safe, internal-only plan trace for debugging.

Recommendations:
- Enforce hard limits at the workflow layer (max iterations, max tool calls, max runtime).
- Add an explicit planning step that produces a structured plan *internally*, not user-visible, and gate tool usage against it (optional).
- Add post-tool response validation (e.g., ensure answer references tool outputs/citations when tools were called).

### 2) Tool use & orchestration

Observed:
- Tools and clients frequently use synchronous I/O (`httpx.Client`), and transcript polling uses `time.sleep` in a tool invoked on an async path.
- No retries/backoff policies, no circuit breakers, no timeouts that are centrally managed, and no budgets per request.
- `project_id` is accepted at the API boundary but is not consistently plumbed through to tools/workflow (multi-tenant correctness gap).

Production gaps:
- Event loop blocking (scalability + latency).
- Inconsistent tenant scoping (data boundary risk).
- No idempotency keys or correlation IDs for tool calls.
- No centralized tool policy (allowed tools, parameter validation, safe defaults).

Recommendations:
- Convert tools to async end-to-end (`httpx.AsyncClient`, `asyncio.sleep`, async LLM invocation).
- Add a shared “tool runtime” wrapper that enforces:
  - timeouts, retries with jitter, max concurrency
  - parameter validation and allowlists (especially for file IDs/paths)
  - metrics + tracing + correlation IDs
- Ensure `project_id` is part of the agent state and passed to every tool invocation explicitly.

### 3) Memory & context management

Observed:
- Redis checkpointing persists messages by `thread_id` with no lifecycle controls.
- No context window management (summarize/trim), no TTL, no deletion API, no user identity binding.

Production gaps:
- Unbounded growth (cost + reliability).
- Potential PHI retention beyond policy.
- No encryption/field-level redaction for stored messages.
- Session tokens (UUIDs) are effectively bearer tokens with no auth binding.

Recommendations:
- Define and enforce a retention policy (TTL) per environment (dev/stage/prod).
- Add summarization/truncation strategy to keep context bounded.
- Store only what’s necessary (minimize PHI; store pointers to encrypted blobs when needed).
- Require authentication; bind session/thread IDs to a user/tenant identity; add session revocation.

### 4) Retrieval & grounding

Observed:
- The agent uses a tool that calls `/rag/query` which performs both retrieval and generation, and returns a single answer string to the agent tool.
- The tool discards the `sources` data that the RAG endpoint returns.
- Compliance analysis has its own RAG-ish regulation retrieval and batching logic, but at the agent layer grounding is not enforceable.

Production gaps:
- “Double-LLM” pipeline (RAG generates answer; agent re-answers) increases drift/hallucination risk.
- No structured citation enforcement at the agent output boundary.
- No injection-hardening strategy (retrieved content can include prompt-injection).

Recommendations:
- Prefer retrieval-only tool output (documents + metadata), then generate the final answer once, with strict “use only retrieved context” constraints.
- Return structured sources/citations to the agent layer and enforce a response schema that includes citations where applicable.
- Add prompt-injection hygiene: strip/escape tool outputs, label them as untrusted, and apply policy-based formatting.

### 5) Evaluation loops

Observed:
- Minimal tests exist for HTTP clients; no agent behavior tests exist (tool selection, grounding, refusal policy, injection resilience).
- No offline evaluation dataset or regression harness described.

Production gaps:
- No automated detection of regression in safety/grounding/compliance behavior.
- No golden tests for “must cite tool outputs when tool called”.
- No load/perf tests for agent endpoints.

Recommendations:
- Add an eval harness:
  - scenario suite (PHI transcript, regulation queries, adversarial injections, non-HIPAA queries)
  - pass/fail assertions (tool usage, citations, refusal correctness, no sensitive leakage)
- Add tracing-based online evaluation signals: tool error rate, retries, hallucination heuristics (e.g., citation presence), latency budgets.

### 6) Guardrails & safety

Observed:
- Agent API currently exposes internal traces (`steps`).
- File uploads are written to `/tmp/agent_uploads` without encryption, TTL cleanup, or explicit access controls.
- Tools accept user-controlled-like parameters (file path) without strict server-side enforcement.
- No authN/authZ/rate limiting shown on agent endpoints.

Production gaps:
- High risk of PHI exposure and data exfiltration.
- No policy enforcement for “only HIPAA-related topics” beyond prompt text.
- No sandboxing at tool boundary (filesystem/network constraints).

Recommendations:
- Remove/disable chain-of-thought exposure; provide a redacted “actions list” at most.
- Switch from “file path” to “file_id” and resolve via server-side allowlisted storage.
- Encrypt uploaded content at rest; implement TTL cleanup; don’t persist raw uploads beyond processing needs.
- Add authN/authZ and per-tenant rate limiting; add request size limits and content-type enforcement.
- Add a policy layer that enforces topic and data handling constraints independent of the model prompt.

### 7) Observability & feedback

Observed:
- Logging exists but no structured tracing/metrics.
- No correlation IDs across agent→tools→services.
- No token/cost accounting.

Production gaps:
- Hard to debug failures or prove compliance posture.
- No operational SLOs or alerting hooks.

Recommendations:
- Add OpenTelemetry tracing (request → tool calls → downstream service calls).
- Emit structured metrics: latency, tool call counts, error rates, retries, token usage, queue depth.
- Add correlation IDs and propagate them through HTTP headers.
- Implement PHI-safe logging and audit logging distinct from application logs.

### 8) Production tradeoffs & architecture notes

Observed:
- The system is a “microservice-like monolith” with HTTP boundaries between components.
- That’s acceptable, but it increases operational failure modes without resilience patterns.

Production gaps:
- Without retries/budgets/circuit breakers, partial outages become full outages.
- Without strong tenant scoping, cross-project leakage is possible.

Recommendations:
- Decide on service boundaries intentionally:
  - If truly monolithic: call internal modules directly and avoid HTTP hops.
  - If service-based: invest in resilience + contracts + SLIs between services.

---

## Production Hardening Checklist (Prioritized)

### P0 — Launch blockers (security/compliance/correctness)

- [ ] **Disable chain-of-thought exposure**: remove or strictly redact `steps[].thought` and `steps[].observation` in agent responses.
- [ ] **Replace file path tool inputs with file IDs**:
  - The model must never choose filesystem paths.
  - Store uploads in controlled storage and resolve IDs server-side via allowlist.
- [ ] **Implement upload retention controls**:
  - Encrypt at rest (or store in an approved encrypted object store).
  - TTL cleanup job for temporary files; delete immediately after ingestion where possible.
  - Enforce max file size and content type.
- [ ] **PHI-safe logging**:
  - Stop logging user prompts/transcripts; use structured metadata only (lengths, request IDs, tenant IDs).
  - Add redaction utilities; ensure logs are access-controlled and retention-managed.
- [ ] **Enforce workflow budgets**:
  - max iterations, max tool calls, max wall-clock time per request, and cancellation propagation.
- [ ] **Fix multi-tenant scoping**:
  - Add `project_id` to agent state and ensure it is passed to all tools consistently.
- [ ] **Authentication & authorization on agent endpoints**:
  - Bind sessions to user identity; revoke sessions; rotate keys.
  - Add rate limiting and abuse controls.

### P1 — Reliability, grounding, and operational safety

- [ ] **Make tools async end-to-end**:
  - Use `httpx.AsyncClient` with connection pooling.
  - Replace `time.sleep` with `asyncio.sleep`.
  - Use async LLM calls or run sync calls in a threadpool with bounded executor.
- [ ] **Centralize tool runtime policy**:
  - timeouts, retries with backoff+jitter, circuit breaking, and per-tool concurrency limits.
  - parameter validation with allowlists (e.g., `file_id` ownership, tenant boundaries).
- [ ] **Strengthen grounding**:
  - Use retrieval-only outputs for RAG tools (documents + source metadata).
  - Generate the final response once, with enforced citations.
  - Add response schema validation: citations required when retrieval used; “unknown” required when no sources.
- [ ] **Injection resilience**:
  - Treat retrieved content as untrusted; isolate it from instructions.
  - Add a policy that forbids following instructions found in retrieved content.
- [ ] **Session/memory controls**:
  - TTL in Redis, memory size caps, summarization, and deletion endpoints.
  - Avoid storing PHI in checkpoints where possible; store pointers to encrypted blobs.

### P2 — Observability, testing, and lifecycle

- [ ] **Tracing**: implement OpenTelemetry traces across agent, tools, and downstream services; propagate correlation IDs.
- [ ] **Metrics**: expose latency, error rates, tool call counts, retries, token usage, queue depth, and cache hit rates.
- [ ] **Auditability**:
  - Separate security/compliance audit logs from application logs.
  - Ensure audit logs are tamper-evident and queryable by tenant.
- [ ] **Evaluation harness**:
  - regression suite for tool selection, grounding, refusal behavior, injection attacks, and PHI leakage checks.
  - add golden tests for “tool called ⇒ answer references tool output + citations”.
- [ ] **Load testing**:
  - concurrency tests for `/agent` endpoints; ensure no event loop blocking.
- [ ] **Runbooks**:
  - incident playbooks for tool/service degradation, backlog growth, model errors, and data handling incidents.

---

## Suggested Implementation Roadmap (Concrete)

1) Remove user-facing `steps` (or replace with a minimal “actions taken” list without raw text).
2) Replace “file paths” with upload IDs and ownership checks.
3) Introduce a `ToolRuntime` wrapper (timeouts/retries/metrics) and convert tools to async.
4) Refactor RAG tool to return `{documents, sources}` and enforce citations at response boundary.
5) Add workflow budgets and cancellation; add TTL/summarization for Redis checkpointing.
6) Add auth + rate limiting; define retention policies and a PHI-safe logging standard.
7) Add eval harness + observability (OTel + metrics) and bake into CI.

