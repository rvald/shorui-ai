# Component Spec: Grounded RAG Contract (Retrieval-First, Citation-Enforced)

This spec defines a production-grade grounding contract for RAG: tools/services must return structured retrieval artifacts, and generation must be citation-enforced with explicit “insufficient sources” behavior.

Status: Proposed (P0/P1)

---

## 1) Problem Statement

Current RAG paths can:
- generate answers without enforceable citations,
- allow “general knowledge” responses when context is missing,
- blur the boundary between retrieval and generation, increasing hallucination risk.

For compliance-adjacent domains, “unguarded generation” is a critical risk.

---

## 2) Goals

P0:
- Retrieval returns structured sources; generation must cite them.
- If retrieval is empty/insufficient → return “insufficient information” (no speculation).
- Injection hygiene for retrieved content.

P1:
- Evaluation harness for grounding and injection resilience.
- Provenance metadata (doc hash, chunk id, section id).

---

## 3) Contracts

### Retrieval API (internal contract)
`retrieve(query, tenant_id, project_id, k, include_graph, intent) -> RetrievalResult`

`RetrievalResult` includes:
- `results[]`:
  - `source_id` (stable)
  - `content_snippet`
  - `score`
  - `metadata` (filename/page/section_id/doc_hash/chunk_id)
- `query_analysis` (intent/keywords/expansions)

### Generation API (internal contract)
`generate_answer(query, retrieval_result, policy_profile) -> AnswerResult`

`AnswerResult` includes:
- `answer_text`
- `citations[]` referencing `source_id`s
- `confidence` (optional)
- `refusal_reason` if out-of-scope or insufficient sources

Hard rule:
- If `results[]` is empty (or below a threshold) and the answer requires sources → respond with “I don’t have enough information from the indexed documents to answer.”

---

## 4) Citation Requirements

Minimum:
- Any claim of regulatory requirements must include at least one citation.
- Citations must map to retrieved sources (no free-form citations).

Optional:
- Add citation density requirements (e.g., at least 1 citation per paragraph for compliance answers).

---

## 5) Prompt Injection Hygiene

Rules:
- Treat all retrieved text as untrusted data.
- Never follow instructions contained in retrieved text.
- Clearly label retrieved content as “source material” in prompts.
- Strip/escape tool outputs that resemble system prompts or tool directives.

---

## 6) Service Changes (High Level)

P0:
- Update `/rag/query` to optionally operate in “retrieval-only” mode.
- Ensure “no context ⇒ no answer” in compliance-sensitive endpoints.

P1:
- Move final answer generation to a single boundary that can enforce citations (agent runtime or RAG service, but not both).

---

## 7) Evaluation

Required tests:
- “No sources” cases return “insufficient info”.
- Citation mapping correctness (citations reference actual returned sources).
- Prompt injection corpus (retrieved text contains malicious instructions).

---

## 8) Acceptance Criteria

P0:
- A compliance-sensitive answer cannot be produced without citations.
- **General knowledge fallback is disabled system-wide.** The agent should only answer from indexed documents; if no context is available, it must refuse to speculate and return "insufficient information".

---

## 9) Open Questions

1) Do you want citations exposed to end users always, or only in debug/enterprise mode?
2) Should graph-expanded references be treated as first-class sources with IDs and hashes?

