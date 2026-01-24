# North-Star Architecture for a Production-Grade Agentic System

This document describes a “north-star” architecture for Shorui AI’s agent system that follows system design best practices and production-ready agentic patterns, with HIPAA-adjacent constraints (PHI risk, retention, auditability). It emphasizes enforceable boundaries, structured artifacts, and observable behavior.

---

## Design Goals (Non-Negotiables)

1) **Enforce safety outside the model**
- Prompts guide behavior; policy enforces it.

2) **Make tool use deterministic and auditable**
- Standardized execution path, validated I/O, budgets, metrics, traceability.

3) **Ground outputs in verifiable sources**
- Retrieval produces artifacts; generation must cite them.

4) **Bound memory and sensitive data**
- TTL, summarization, deletion semantics, encryption, access controls.

5) **Operate reliably under partial failures**
- Timeouts, retries/backoff, circuit breakers, bulkheads, load shedding.

---

## High-Level Architecture

### Core Components

1) **Agent API (FastAPI boundary)**
- Responsibilities:
  - AuthN/AuthZ, tenant/project resolution, request validation (size/type limits), rate limiting.
  - Secure file ingestion (uploads → `file_id`, never raw file paths).
  - Response shaping (no chain-of-thought; safe “actions taken” only).
- Guarantees:
  - Every request is associated with a principal (`user_id`/`tenant_id`) and a `request_id`.
  - No raw PHI logging by default.

2) **Agent Runtime (Orchestrator / State Machine)**
- Responsibilities:
  - Executes the agent workflow (plan → act → synthesize → verify → respond).
  - Enforces budgets (max wall-time, tool calls, tokens) and cancellation.
  - Produces **internal events** (structured) for observability; not user-visible reasoning traces.
- Implementation options:
  - LangGraph StateGraph, Temporal, or a custom orchestrator depending on scale.

3) **Policy Engine (Model-Independent Guardrails)**
- Responsibilities:
  - Tool allowlists and parameter constraints (e.g., `file_id` ownership checks).
  - Output safety checks (no PHI leakage, no internal traces, scope enforcement).
  - Retention policy enforcement (what is stored, for how long, how it’s deleted).

4) **Tool Runtime (Single Gateway for All Tool Calls)**
- Responsibilities:
  - Enforced timeouts, retries with backoff+jitter, circuit breakers.
  - Concurrency limits per tool and per tenant.
  - Schema validation for tool inputs/outputs.
  - Correlation IDs propagation + tracing + metrics.
  - Centralized redaction policy for logs and error messages.

5) **Memory & Artifact Stores**
- **Conversation memory store**:
  - Bounded context (summarize/trim), TTL, deletion endpoints, encryption at rest.
  - Stores minimal necessary information; avoids PHI when possible.
- **Artifact store** (sensitive content):
  - Encrypted storage for transcripts/documents; referenced by pointers/IDs.
  - Managed by a first-class **Artifact Registry**.
  - Access controlled by tenant/project/user (mandatory `tenant_id`).
  - Audit events for access (especially PHI-bearing artifacts).

6) **Retrieval System (RAG as Artifact Producer)**
- Responsibilities:
  - Returns structured retrieval results: documents, snippets, metadata, scores.
  - Does not “decide” final user answers in a way that bypasses citation enforcement.

7) **Observability & Evaluation**
- Observability:
  - Distributed tracing (API → runtime → tool runtime → downstream services).
  - Metrics: latency, error rates, retries, tool calls, token/cost, cache hits.
- Evaluation:
  - Regression suite: grounding/citations, refusal behavior, injection resilience, PHI leakage.
  - Online signals: citation presence, tool error rates, latency SLOs.

---

## Request Lifecycle (End-to-End)

1) Client sends message to Agent API with `session_id` and optional uploads.
2) API authenticates, resolves `tenant_id` + `project_id`, stores uploads, returns `file_id`s.
3) Runtime loads bounded memory for `(tenant_id, session_id)` and creates a `RunContext`:
   - `{request_id, user_id, tenant_id, project_id, budgets, policy_profile}`
4) Runtime executes:
   - **Plan** (internal) → **Act** (tools via Tool Runtime) → **Synthesize** → **Verify** (policy + grounding) → **Respond**
5) Response returns:
   - `answer` + `citations` (+ optional safe `actions_taken` without raw tool outputs).

---

## Key Contracts (Make It Enforceable)

### Run Context (Propagated Everywhere)
- `request_id`, `tenant_id`, `project_id`, `user_id`
- `budgets`: `{max_wall_ms, max_tool_calls, max_tokens, deadline}`
- `policy_profile`: environment + tenant-specific constraints

### Tool Interface (Typed, Not “Stringly”)
- Input: Pydantic schema (validated)
- Output: Pydantic schema (validated)
- Errors: structured `{type, retryable, safe_message, debug_id}`

### Retrieval Artifact
- `results[]`: `{content_snippet, source_id, filename, page, score, metadata}`
- `query_analysis`: `{intent, keywords, expansions}`
- No tool should return “final compliance advice” without sources.

---

## Patterns Used (and Why)

1) **Hexagonal / Ports-and-Adapters**
- Why: lets the runtime and policy remain stable while swapping LLM providers, storage, and retrieval backends.
- Outcome: better testability, lower blast radius of infrastructure changes.

2) **Single Tool Gateway (Tool Runtime)**
- Why: prevents “ad hoc” network/file calls from proliferating; makes reliability and safety consistent.
- Outcome: uniform timeouts/retries/metrics and easier incident response.

3) **Policy-as-Code**
- Why: prompt-only guardrails fail under injection and distribution shift.
- Outcome: enforceable constraints and predictable compliance posture.

4) **Artifact-Based Architecture**
- Why: tool outputs should be inspectable, storable, and auditable; not ephemeral strings.
- Outcome: supports citations, debugging, replay, and evaluation.

5) **Budgeting / Deadline Propagation**
- Why: agent loops can runaway; budgets prevent cost and latency explosions.
- Outcome: predictable SLOs and stable multi-tenant operation.

6) **Defense-in-Depth for Grounding**
- Why: retrieval corpora can contain injections; LLMs can hallucinate.
- Outcome: “retrieve → cite → verify” with schema checks and fallbacks.

7) **Observability-First**
- Why: agentic systems fail in ways that are hard to reproduce; logs alone are insufficient.
- Outcome: traces + metrics + replayable artifacts enable fast diagnosis.

---

## Tradeoffs (Explicit)

1) **More structure, less “magic”**
- Tradeoff: upfront engineering effort (schemas, policies, wrappers).
- Benefit: predictable behavior, easier debugging, safer operation.

2) **Retrieval-only vs RAG-generated answers**
- Tradeoff: slightly more runtime complexity (you generate once in the runtime).
- Benefit: single point of truth for grounding/citations and reduced hallucination risk.

3) **Bounded memory vs full chat history**
- Tradeoff: less verbatim conversational recall.
- Benefit: mandatory `tenant_id` isolation, stable context sizes, lower cost.

4) **Strict tool validation may reduce capability**
- Tradeoff: the model can’t “freestyle” parameters.
- Benefit: prevents exfiltration classes (paths, URLs) and tenant boundary violations.

5) **More services vs monolith**
- Tradeoff: service boundaries add network failure modes and operational cost.
- Benefit: independent scaling and isolation if you invest in resilience.
- Recommendation: keep logical boundaries; choose physical boundaries based on team maturity and SLO needs.

---

## Failure Modes & Mitigations (Examples)

- Downstream retrieval outage → degrade gracefully:
  - Tool Runtime circuit-breaks, runtime returns “insufficient sources” response (policy-enforced).
- Tool returns empty sources → enforce “unknown” response:
  - Runtime validation prevents speculative answers.
- Long-running transcript analysis → async job + polling:
  - Runtime returns a job handle and avoids blocking the event loop.
- Prompt injection in retrieved text:
  - Treat tool outputs as untrusted data; policy forbids following instructions from sources.

---

## Incremental Migration Plan (Low-Risk)

1) **Stop leakage**: remove chain-of-thought traces from API responses; implement PHI-safe logging.
2) **Tool Runtime wrapper**: centralize timeouts/retries/metrics + strict input validation (introduce `file_id`).
3) **Retrieval as artifact**: change regulation tool to return sources; move generation to runtime with citation enforcement.
4) **Bound memory**: TTL + summarization + deletion semantics; bind sessions to identity.
5) **Add eval + OTel**: regression suite + tracing/metrics; bake into CI/CD gates.

