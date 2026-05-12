# Phase 2 — Authentication System

## Objectives
Implement a production-grade JWT authentication system with RBAC foundations. Every subsequent phase depends on a working identity layer — get this right before writing any business logic.

## Dependencies
- Phase 1 complete (FastAPI app boots, DB container running)

## Estimated Duration
2–3 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | `POST /auth/register` creates user | Returns JWT pair, user stored in DB |
| 2 | `POST /auth/login` authenticates | Returns access + refresh tokens |
| 3 | `POST /auth/refresh` rotates tokens | Old refresh token invalidated |
| 4 | `POST /auth/logout` | Refresh token blacklisted |
| 5 | Auth middleware guards all non-public routes | `401` returned without valid token |
| 6 | RBAC roles: `super_admin`, `org_admin`, `agent`, `viewer` | Role stored on user, middleware checks it |
| 7 | Frontend login/register pages | Token stored in httpOnly cookie via API route |
| 8 | Password reset flow | Email-based OTP with 15-min expiry |

---

## Database Tables (Phase 2 creates these)

```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email       VARCHAR(255) UNIQUE NOT NULL,
    hashed_pw   TEXT NOT NULL,
    role        VARCHAR(50) NOT NULL DEFAULT 'agent',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ                      -- soft delete
);

CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,
    plan        VARCHAR(50) NOT NULL DEFAULT 'free',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ
);

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL,                   -- store hash, not plaintext
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE password_reset_otps (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    otp_hash    TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_users_org ON users(org_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
```

---

## Backend Architecture

### Files to Create
```
backend/
├── auth/
│   ├── __init__.py
│   ├── dependencies.py     # FastAPI Depends() for current_user
│   ├── jwt.py              # token creation/validation
│   ├── password.py         # bcrypt hashing
│   └── rbac.py             # role permission checker
├── routes/
│   └── auth.py             # register, login, refresh, logout, reset
├── services/
│   └── auth_service.py     # business logic (no DB queries here)
├── repositories/
│   └── user_repo.py        # all DB queries for users/tokens
├── models/
│   ├── user.py             # SQLAlchemy ORM model
│   └── organization.py
└── schemas/
    └── auth.py             # Pydantic DTOs
```

### JWT Strategy
- **Access token**: 60-minute expiry, signed with `HS256`, payload contains `sub` (user_id), `org_id`, `role`.
- **Refresh token**: 30-day expiry. Only the **hash** is stored in DB (SHA-256). On refresh, compare hash, check `revoked` flag, issue new pair, revoke old.
- Tokens are **never** stored in `localStorage`. Frontend stores them in memory (access) and sends them via `Authorization: Bearer` header. Refresh token lives in a `httpOnly SameSite=Strict` cookie set by a Next.js API route acting as BFF.

```python
# backend/auth/jwt.py
from datetime import datetime, timedelta, timezone
import jwt
from backend.core.config import settings

def create_access_token(user_id: str, org_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
```

### Auth Dependency (`backend/auth/dependencies.py`)
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.auth.jwt import decode_token
from backend.repositories.user_repo import get_user_by_id

bearer = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

def require_role(*roles: str):
    async def checker(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return checker
```

### RBAC Permission Matrix

| Role | Read Own Data | Manage Leads | Upload Docs | Manage Users | Billing |
|---|---|---|---|---|---|
| `super_admin` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `org_admin` | ✅ | ✅ | ✅ | ✅ (own org) | ✅ |
| `agent` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `viewer` | ✅ | ❌ | ❌ | ❌ | ❌ |

### API Endpoints

```
POST /api/v1/auth/register
Body: { email, password, org_name }
Response: { access_token, user: { id, email, role, org_id } }

POST /api/v1/auth/login
Body: { email, password }
Response: { access_token } + Set-Cookie: refresh_token (httpOnly)

POST /api/v1/auth/refresh
Cookie: refresh_token
Response: { access_token } + rotated Set-Cookie

POST /api/v1/auth/logout
Cookie: refresh_token
Response: 204

POST /api/v1/auth/password-reset/request
Body: { email }
Response: 200 (always, prevents enumeration)

POST /api/v1/auth/password-reset/confirm
Body: { token, new_password }
Response: 200
```

### Schemas (`backend/schemas/auth.py`)
```python
from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str           # min 8 chars enforced with validator
    org_name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: str
    email: str
    role: str
    org_id: str

    model_config = {"from_attributes": True}
```

---

## Frontend Architecture

### Pages
```
frontend/app/
├── (auth)/
│   ├── login/page.tsx
│   ├── register/page.tsx
│   └── reset-password/page.tsx
└── api/
    ├── auth/login/route.ts       # BFF: sets httpOnly cookie
    ├── auth/refresh/route.ts
    └── auth/logout/route.ts
```

### Auth State (`frontend/lib/auth.ts`)
- Use Zustand store holding `{ user, accessToken }` in memory.
- On app boot, call `/api/auth/refresh` to get a new access token using the stored cookie — silent refresh.
- Axios interceptor automatically refreshes expired tokens before retrying the original request.

---

## Security Rules Enforced in This Phase

1. Passwords hashed with `bcrypt` (cost factor 12).
2. Refresh tokens stored as SHA-256 hashes only.
3. Token payload contains no PII beyond `user_id`.
4. Rate limit auth endpoints: 5 attempts/min per IP (use `slowapi`).
5. Password reset OTPs are 6-digit, expire in 15 minutes, single-use.
6. Email enumeration prevented — reset endpoint always returns 200.

---

## Validation Checklist

- [ ] `POST /auth/register` with duplicate email returns `409`
- [ ] `POST /auth/login` with wrong password returns `401`
- [ ] Accessing a protected route without a token returns `401`
- [ ] Accessing a protected route with an expired token returns `401`
- [ ] `org_admin` cannot access another org's data (tested with separate org fixture)
- [ ] `viewer` role returns `403` on lead mutation endpoints
- [ ] Refresh token is rotated on each use (old token rejected after refresh)
- [ ] 6th login attempt within 1 minute returns `429`
- [ ] All tests pass: `pytest backend/tests/test_auth.py -v`

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| JWT secret rotation breaks all sessions | Store secret version in token; support 2 active secrets during rotation |
| Refresh token theft | Short-lived access tokens + rotation-based refresh + revocation on logout |
| DB down at login | Return `503` with retry-after header; never expose raw exception |

## Rollback Strategy
Drop `users`, `organizations`, `refresh_tokens`, `password_reset_otps` tables. No business data exists yet.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-2-auth-system
```

### Commit Checkpoints

```bash
# After DB migration for users + organizations tables
git add backend/alembic/
git commit -m "feat(auth): add migrations for users and organizations tables"

# After JWT token creation/validation + password hashing
git add backend/auth/
git commit -m "feat(auth): add JWT token creation, validation, and bcrypt hashing"

# After register + login endpoints working
git add backend/routes/auth.py backend/services/auth_service.py backend/repositories/user_repo.py
git commit -m "feat(auth): implement register and login endpoints"

# After refresh + logout + token rotation
git commit -m "feat(auth): add refresh token rotation and logout with blacklist"

# After auth middleware + RBAC dependency
git add backend/auth/dependencies.py backend/auth/rbac.py
git commit -m "feat(auth): add get_current_user dependency and require_role RBAC guard"

# After password reset flow
git commit -m "feat(auth): add password reset OTP flow with 15-minute expiry"

# After frontend login/register pages + BFF cookie routes
git add frontend/app/\(auth\)/ frontend/app/api/auth/
git commit -m "feat(auth): add login and register pages with httpOnly cookie BFF"
```

### Merge to Develop
```bash
git push -u origin feature/phase-2-auth-system

gh pr create \
  --title "feat: Phase 2 — Authentication System" \
  --body "JWT auth, refresh token rotation, RBAC roles, password reset, frontend login/register. All checklist items pass." \
  --base develop
```

---

## Definition of Done

Phase 2 is **complete** when every item below is checked.

### Code Quality
- [ ] No business logic in route handlers — all logic lives in `auth_service.py`
- [ ] All Pydantic schemas use strict types (`EmailStr`, not plain `str` for email)
- [ ] No raw SQL — all queries go through `user_repo.py`
- [ ] All functions fully type-annotated (mypy strict passes)
- [ ] Passwords never logged, never returned in any API response

### Functionality
- [ ] `POST /auth/register` with valid data returns `201` + JWT access token
- [ ] `POST /auth/register` with duplicate email returns `409`
- [ ] `POST /auth/login` with correct credentials returns access token + sets httpOnly cookie
- [ ] `POST /auth/login` with wrong password returns `401`
- [ ] Protected endpoint without token returns `401`
- [ ] Protected endpoint with expired token returns `401`
- [ ] `viewer` role on a mutation endpoint returns `403`
- [ ] `org_admin` cannot access another org's data (cross-tenant test)
- [ ] Refresh token is revoked after use (old token rejected on second use)
- [ ] 6th login attempt within 1 minute returns `429`

### Security
- [ ] Passwords stored as bcrypt hash (cost 12) — never plaintext
- [ ] Refresh token stored as SHA-256 hash only — never plaintext
- [ ] JWT payload contains no PII beyond `user_id`, `org_id`, `role`
- [ ] Rate limiting on `/auth/login` and `/auth/register` verified manually

### Testing
- [ ] `pytest backend/tests/test_auth.py -v` — all tests pass
- [ ] Test coverage for auth module ≥ 85%
- [ ] Tests use real DB (not mocked), via pytest fixture with rollback

### What is NOT Acceptable
- Storing refresh tokens in plaintext in the database
- Skipping cross-tenant isolation tests
- `role` checks hardcoded in route handlers instead of using `require_role()`
- JWT secret shorter than 32 characters
