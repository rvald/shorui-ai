# Component Spec: User Authentication (Login Flow)

This spec defines the user authentication system for multi-tenant production deployment. It enables user login, self-service registration, and secure session management.

Status: Proposed (P1)

---

## 1) Problem Statement

The current auth system uses API keys for service-to-service authentication, but lacks:
- User-facing login experience for the frontend
- Self-service registration for new users
- Secure session management with HttpOnly cookies
- Multi-tenant user isolation

---

## 2) Goals

P1:
- Direct authentication (email/password) with secure credential storage
- JWT access tokens with HttpOnly cookie storage
- Self-service user registration
- Logout invalidates auth sessions AND agent sessions

P2:
- OAuth2/OIDC integration (Google, Okta)
- Password reset flow
- Email verification
- MFA support

---

## 3) Design Decisions

| Decision | Choice | Rationale |
|:---------|:-------|:----------|
| Auth Strategy | Direct Auth | Simpler, full control |
| Token Storage | HttpOnly cookies | XSS protection |
| Registration | Self-service | Users can sign up |
| Logout Behavior | Invalidate all sessions | HIPAA data minimization |
| Access Token TTL | 15 min | High-security standard |
| Refresh Token TTL | 1 day | Balance security/UX |
| Agent Sessions | Ephemeral (in-memory) | Future: add persistence |

---

## 4) Database Schema

### Users Table

```sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_tenant ON users(tenant_id);
```

### Refresh Tokens Table

```sql
CREATE TABLE refresh_tokens (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
```

---

## 5) API Contracts

### POST /auth/register

Self-service user registration.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "tenant_name": "Acme Corp"
}
```

**Response (201):**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "tenant_id": "acme-corp"
}
```

**Behavior:**
- Creates new tenant if `tenant_name` is new
- Hashes password with bcrypt
- Returns user info (no tokens—must login)

---

### POST /auth/login

Authenticate and receive tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 900,
  "user": {
    "user_id": "uuid",
    "email": "user@example.com",
    "tenant_id": "acme-corp",
    "role": "user"
  }
}
```

**Cookies Set:**
- `refresh_token`: HttpOnly, Secure, SameSite=Strict, Max-Age=86400

---

### POST /auth/refresh

Refresh access token using refresh cookie.

**Request:** No body (refresh_token from cookie)

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 900
}
```

---

### POST /auth/logout

Logout and invalidate sessions.

**Request:** No body (uses cookie)

**Response (200):**
```json
{
  "message": "Logged out successfully"
}
```

**Behavior:**
1. Revokes refresh token in DB
2. Clears refresh_token cookie
3. Invalidates all agent sessions for user

---

### GET /auth/me

Get current user info.

**Response (200):**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "tenant_id": "acme-corp",
  "role": "user"
}
```

---

## 6) JWT Structure

### Access Token Payload

```json
{
  "sub": "user-uuid",
  "tenant_id": "acme-corp",
  "email": "user@example.com",
  "role": "user",
  "scopes": ["ingest:write", "rag:read", "compliance:read"],
  "iat": 1706172300,
  "exp": 1706173200
}
```

### Signing

- Algorithm: HS256
- Secret: `JWT_SECRET` env var (256-bit minimum)

---

## 7) Middleware Changes

Update `AuthMiddleware` to accept:

1. `X-API-Key` header (existing, for services)
2. `Authorization: Bearer {jwt}` (new, for users)
3. `refresh_token` cookie (for token refresh)

Priority order: API Key → Bearer Token → Cookie

---

## 8) Frontend Changes

### New Components

| Component | Path | Description |
|:----------|:-----|:------------|
| `LoginPage` | `/src/pages/Login.tsx` | Email/password form |
| `RegisterPage` | `/src/pages/Register.tsx` | Signup form |
| `AuthContext` | `/src/context/AuthContext.tsx` | Token state management |
| `authApi` | `/src/api/authApi.ts` | Auth API client |

### Auth Flow

1. Check for access token on app load
2. If missing, check refresh cookie via `/auth/refresh`
3. If refresh fails, redirect to `/login`
4. Auto-refresh access token before expiry

### API Client Update

```typescript
// All fetch calls include credentials for cookies
fetch(url, {
  credentials: 'include',  // Send cookies
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
});
```

---

## 9) CORS Configuration

Required for HttpOnly cookies cross-origin:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://yourdomain.com"],
    allow_credentials=True,  # Required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 10) Security Considerations

| Concern | Mitigation |
|:--------|:-----------|
| Password Storage | bcrypt with cost factor 12 |
| XSS | HttpOnly cookies, no token in localStorage |
| CSRF | SameSite=Strict cookie + CORS |
| Token Leakage | Short-lived access tokens (15 min) |
| Brute Force | Rate limiting on login endpoint |
| Session Fixation | New refresh token on each login |

---

## 11) Implementation Plan

### Phase 1: Backend Auth (P1)
- [ ] Add users table migration
- [ ] Add refresh_tokens table migration
- [ ] Create `UserService` (register, authenticate, get_by_id)
- [ ] Create `JwtService` (create_access_token, verify_token)
- [ ] Create auth routes (/register, /login, /refresh, /logout, /me)
- [ ] Update middleware to accept Bearer tokens

### Phase 2: Frontend Auth (P1)
- [ ] Create AuthContext with token management
- [ ] Create Login and Register pages
- [ ] Update agentApi to include credentials
- [ ] Add auto-refresh logic
- [ ] Add logout functionality

### Phase 3: Integration (P1)
- [ ] Wire agent session invalidation to logout
- [ ] Configure CORS for production
- [ ] Add rate limiting to auth endpoints
- [ ] Test full flow end-to-end

---

## 12) Acceptance Criteria

P1:
- Users can self-register with email/password
- Users can login and receive HttpOnly refresh cookie
- Access tokens are short-lived (15 min) and auto-refresh
- Logout invalidates refresh token AND agent sessions
- Frontend redirects to login when not authenticated
- API returns 401 for unauthenticated requests when enabled

---

## 13) Open Questions

1. Should we email users on registration (welcome email)? No
2. Do we need email verification before allowing login? Future enhancement
3. Should admins be able to create users on behalf of tenants? Future enhancement
