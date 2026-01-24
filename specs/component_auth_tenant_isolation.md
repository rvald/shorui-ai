# Component Spec: AuthN/AuthZ & Tenant Isolation (Production Hardening)

This spec introduces authentication, authorization, and tenant isolation as enforceable system boundaries. It defines how `tenant_id` is derived, how sessions/jobs/artifacts are bound to identity, and how access to PHI-bearing resources is controlled.

Status: Proposed (P0/P1)

---

## 1) Problem Statement

Services currently accept `project_id` as a parameter but do not enforce identity-based access control. Session IDs behave like bearer tokens, and sensitive resources (uploads, reports, audit logs) can be accessed without strong authorization boundaries.

---

## 2) Goals

P0:
- Require authentication for all non-health endpoints in production.
- Bind `tenant_id` to authenticated identity (no client-supplied tenant).
- Enforce authorization checks on all PHI-bearing endpoints (transcripts/reports/audit).

P1:
- Role-based access control (RBAC) and least privilege service accounts.
- Rate limiting and quotas per tenant/user.

---

## 3) Identity Model (Logical)

### Principal
- `user_id`
- `tenant_id`
- `roles[]`

### Project
- `project_id` scoped to `tenant_id`
- membership: users can be members of projects with roles.

---

## 4) Auth Mechanisms (Options)

Option A: JWT (OIDC)
- Good for enterprise integrations.

Option B: API keys (tenant-scoped)
- Simpler for internal deployments; rotate keys; limited granularity.

Option C: Session cookies (web UI)
- Frontend-friendly; still needs CSRF handling and API protection.

### Baseline choice (least effort, v1)
**Use tenant-scoped API keys** for v1:
- Fastest path to enforce “no anonymous access” in production.
- Works for backend-to-backend and early UI development.
- Supports incremental hardening (rotation, scopes, per-project membership).

Upgrade path:
- Add JWT/OIDC later for end-user SSO.
- Keep API keys for service-to-service and automation.

This spec mandates the *properties* regardless of auth mechanism:
- authenticated principal available in request context
- **Mandatory `tenant_id` derivation**: server MUST derive `tenant_id` from principal; no default "fallback" tenant is allowed in production.
- all data access is filtered by `tenant_id` + `project_id`

---

## 5) Authorization Rules (Minimum)

P0:
- Transcript upload: requires `ingest:write`
- Transcript/report retrieval: requires `compliance:read`
- Audit log query: requires `audit:read` (admin by default)
- RAG query over a project: requires `rag:read` for that project

All checks must enforce:
- `tenant_id` match
- `project_id` membership

---

## 6) Session Binding (Agent + Jobs)

- `session_id` must be bound to `user_id`/`tenant_id` (no anonymous long-lived sessions in prod).
- Job records store `created_by_user_id` and `tenant_id`.
- Artifacts store `tenant_id`/`project_id` and are not fetchable without authorization.

---

## 7) Rate Limiting / Abuse Controls

Minimum:
- per-tenant and per-user rate limits on:
  - upload endpoints (size + frequency)
  - LLM-backed endpoints (cost control)
- request body size limits at gateway.

---

## 8) Acceptance Criteria

P0:
- Production mode rejects unauthenticated requests to protected endpoints.
- `tenant_id` is never accepted from the client; it is derived from auth.
- All PHI-bearing endpoints enforce tenant/project membership checks.

---

## 9) Open Questions

1) What’s your preferred auth strategy for v1 (JWT/OIDC vs API keys)?
2) Should audit log access be tenant-admin only, or also available to project admins?
