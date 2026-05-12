# Phase 11 — Production Hardening

## Objectives
Harden the platform for real traffic: add Redis caching, rate limiting, comprehensive logging, monitoring, security hardening, load testing, and complete CI/CD pipeline. Nothing new is built — everything existing is made production-grade.

## Dependencies
- Phases 1–10 complete and functionally tested

## Estimated Duration
4–5 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | Redis caching layer | Analytics queries and slot lookups cached |
| 2 | Rate limiting on all endpoints | `slowapi` enforces per-IP and per-org limits |
| 3 | Structured JSON logging (all services) | Every request logged with trace ID |
| 4 | Sentry error tracking | All unhandled exceptions reported |
| 5 | Health check endpoints | `/health` and `/readiness` respond correctly |
| 6 | Database connection pooling tuned | PgBouncer or SQLAlchemy pool sized for load |
| 7 | Security headers on all responses | CSP, HSTS, X-Frame-Options set |
| 8 | Load test passing | 50 concurrent chat requests under 3s p95 |
| 9 | GitHub Actions deploys to staging + prod | Push to `main` = auto deploy |
| 10 | Automated DB backup configured | Daily snapshot, 7-day retention |

---

## Redis Caching

### What to Cache

| Data | TTL | Cache Key |
|---|---|---|
| Analytics overview | 60s | `analytics:{org_id}:{period}` |
| Available calendar slots | 5min | `slots:{org_id}` |
| Org settings + plan | 5min | `org:{org_id}:settings` |
| Active prompt templates | 10min | `prompt:{org_id}:{name}` |

### Cache Layer (`backend/core/cache.py`)

```python
import redis.asyncio as redis
import json
from backend.core.config import settings

pool = redis.ConnectionPool.from_url(settings.REDIS_URL, max_connections=20)

class Cache:
    def __init__(self):
        self._redis = redis.Redis(connection_pool=pool)

    async def get(self, key: str) -> dict | None:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: dict, ttl: int) -> None:
        await self._redis.setex(key, ttl, json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def invalidate_pattern(self, pattern: str) -> None:
        async for key in self._redis.scan_iter(match=pattern):
            await self._redis.delete(key)

cache = Cache()
```

### Cache Usage in Analytics
```python
async def get_overview(org_id: str, period: str, db) -> dict:
    cache_key = f"analytics:{org_id}:{period}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    result = await _compute_overview(org_id, period, db)
    await cache.set(cache_key, result, ttl=60)
    return result
```

---

## Rate Limiting

### Global Limits (via `slowapi`)

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)

# backend/api/main.py
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
```

### Per-Endpoint Limits

| Endpoint | Limit | Key |
|---|---|---|
| `POST /auth/login` | 5/min | per IP |
| `POST /auth/register` | 3/min | per IP |
| `POST /chat/message` | 60/min | per visitor_id |
| `POST /documents/upload` | 10/hour | per org |
| `GET /analytics/*` | 30/min | per org |
| `POST /webhooks/*` | 1000/min | per org (channel traffic) |

```python
@router.post("/message")
@limiter.limit("60/minute", key_func=lambda request: request.json().get("visitor_id", get_remote_address(request)))
async def chat_message(request: Request, ...):
    ...
```

---

## Structured Logging

### Setup (`backend/core/logging.py`)

```python
import structlog
import logging

def configure_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )

logger = structlog.get_logger()
```

### Request Logging Middleware

```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "http_request",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        response.headers["X-Trace-Id"] = trace_id
        return response
```

### Log Fields Standard

Every log entry must include: `trace_id`, `org_id` (where available), `event`, `level`, `timestamp`.

Business events to log explicitly:
- `lead_created`: `{lead_id, org_id, score, category}`
- `document_ingested`: `{document_id, org_id, chunk_count, duration_ms}`
- `llm_call`: `{org_id, model, prompt_tokens, completion_tokens}`
- `appointment_booked`: `{appointment_id, lead_id, org_id}`
- `webhook_received`: `{channel, org_id, trace_id}`

---

## Error Tracking (Sentry)

```python
# backend/api/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    environment=settings.ENVIRONMENT,
    traces_sample_rate=0.1,   # 10% of requests traced
    integrations=[FastApiIntegration(), SqlalchemyIntegration()],
)
```

Sentry scope enrichment — add org_id on every request:
```python
with sentry_sdk.push_scope() as scope:
    scope.set_tag("org_id", current_user.org_id)
```

---

## Health & Readiness Endpoints

```python
@router.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}

@router.get("/readiness")
async def readiness(db: AsyncSession = Depends(get_db)):
    # Check DB connection
    await db.execute(text("SELECT 1"))
    # Check Redis
    await cache._redis.ping()
    return {"status": "ready", "db": "ok", "cache": "ok"}
```

Used by Docker HEALTHCHECK and Kubernetes liveness probes.

---

## Security Headers

```python
from starlette.middleware.trustedhost import TrustedHostMiddleware

# backend/api/main.py
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
    )
    return response
```

---

## CI/CD Pipeline

### GitHub Actions: Staging Deploy (`.github/workflows/deploy-staging.yml`)

```yaml
name: Deploy to Staging
on:
  push:
    branches: [develop]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r backend/requirements-dev.txt
      - run: ruff check backend/
      - run: mypy backend/
      - run: pytest backend/tests/ -v --cov=backend --cov-report=xml
      - uses: codecov/codecov-action@v3

  deploy-backend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Railway (staging)
        run: railway up --service backend-staging
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}

  deploy-frontend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm ci && npm run build
      - name: Deploy to Vercel (preview)
        run: vercel deploy --prebuilt --token=${{ secrets.VERCEL_TOKEN }}
```

### Production Deploy (`.github/workflows/deploy-prod.yml`)
Triggered on `main` push or version tag `v*.*.*`. Same as staging but promotes to production environments after manual approval gate.

---

## Load Testing

### Target Metrics

| Scenario | Concurrent Users | P95 Response Time | Error Rate |
|---|---|---|---|
| Chat message (RAG) | 50 | < 3s | < 0.1% |
| Analytics dashboard | 100 | < 500ms | 0% |
| Document upload | 10 | < 5s | 0% |

### Locust Test (`tests/load/locustfile.py`)

```python
from locust import HttpUser, task, between

class ChatUser(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        res = self.client.post("/api/v1/auth/login",
                               json={"email": "test@org.com", "password": "testpass"})
        self.token = res.json()["access_token"]

    @task(3)
    def send_chat_message(self):
        self.client.post(
            "/api/v1/chat/message",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"message": "What are your pricing plans?", "channel": "web"},
        )

    @task(1)
    def view_dashboard(self):
        self.client.get(
            "/api/v1/analytics/overview",
            headers={"Authorization": f"Bearer {self.token}"},
        )
```

Run: `locust -f tests/load/locustfile.py --headless -u 50 -r 10 --run-time 60s`

---

## Database Backup

Railway/Render provides automated daily snapshots. Additionally:

```bash
# scripts/backup-db.sh (runs via GitHub Actions cron)
pg_dump $DATABASE_URL | gzip | \
  aws s3 cp - "s3://backups-bucket/$(date +%Y-%m-%d).sql.gz"
```

Retention: 7 daily, 4 weekly, 3 monthly snapshots.

---

## Validation Checklist

- [ ] `GET /readiness` returns 200 when all dependencies are healthy
- [ ] `GET /readiness` returns 503 when Postgres is down
- [ ] All 401/403/422/429/500 errors are logged with trace_id and appear in Sentry
- [ ] Load test: 50 concurrent chat users, p95 < 3s, 0 errors
- [ ] Rate limit: 6th login attempt returns `429`
- [ ] Analytics cached — second request within 60s does not hit DB
- [ ] Security headers present on every response (verify with `curl -I`)
- [ ] Push to `develop` triggers staging deploy within 3 minutes
- [ ] Push to `main` requires manual approval before production deploy
- [ ] DB backup cron runs and backup appears in S3

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Redis unavailable | Cache is optional — fall through to DB on `redis.RedisError` |
| Sentry DSN exposed in logs | Environment variable only; never in code or git |
| Load test reveals DB bottleneck | Add indexes in Phase 3; consider read replica |
| Railway/Render cold start delay | Set min instances = 1 on paid plan |

## Rollback Strategy
All hardening changes are additive middleware/config. Rollback = redeploy previous commit. Feature flags: `CACHE_ENABLED`, `RATE_LIMITING_ENABLED` in settings to disable without redeploy.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-11-production-hardening
```

### Commit Checkpoints

```bash
# After Redis cache layer
git add backend/core/cache.py
git commit -m "feat(hardening): add Redis cache layer with TTL-based invalidation"

# After cache applied to analytics + slots
git commit -m "feat(hardening): cache analytics overview (60s) and calendar slots (5min)"

# After slowapi rate limiting on all endpoints
git add backend/core/rate_limit.py
git commit -m "feat(hardening): add per-IP and per-org rate limiting via slowapi + Redis"

# After structured JSON logging + request middleware
git add backend/core/logging.py backend/api/middleware.py
git commit -m "feat(hardening): add structlog JSON logging with trace_id on every request"

# After Sentry integration
git commit -m "feat(hardening): integrate Sentry error tracking with org_id scope tagging"

# After security headers middleware
git commit -m "feat(hardening): add HSTS, CSP, X-Frame-Options, and referrer-policy headers"

# After health + readiness endpoints
git add backend/routes/health.py
git commit -m "feat(hardening): add /readiness endpoint checking DB and Redis liveness"

# After CI/CD deploy pipelines
git add .github/workflows/deploy-staging.yml .github/workflows/deploy-prod.yml
git commit -m "ci: add staging auto-deploy and production manual-approval deploy workflows"

# After load test scripts
git add tests/load/locustfile.py
git commit -m "test(load): add Locust load test for 50 concurrent chat users"

# After DB backup script + cron
git add scripts/backup-db.sh .github/workflows/backup.yml
git commit -m "chore(ops): add daily DB backup to S3 via GitHub Actions cron"
```

### Run Load Test Before Merging
```bash
# Start the full stack
docker compose up -d

# Run load test (requires locust installed)
locust -f tests/load/locustfile.py \
  --headless -u 50 -r 10 --run-time 60s \
  --host http://localhost:8000

# Check results: p95 < 3000ms, failure rate < 0.1%
```

### Merge to Develop
```bash
git push -u origin feature/phase-11-production-hardening

gh pr create \
  --title "feat: Phase 11 — Production Hardening" \
  --body "Redis caching, rate limiting, structured logging, Sentry, security headers, CI/CD deploy pipelines, load test passing." \
  --base develop

# After merge, deploy to staging:
git checkout develop && git pull
# GitHub Actions will auto-deploy to staging
```

---

## Definition of Done

Phase 11 is **complete** when every item below is checked.

### Code Quality
- [ ] Every log entry includes `trace_id` and `org_id` (where available)
- [ ] Cache is optional — code falls through to DB on `redis.RedisError` without crashing
- [ ] Rate limit decorators applied to all auth, chat, and upload endpoints
- [ ] `SENTRY_DSN` in environment variables — Sentry only initialised if DSN present

### Functionality
- [ ] `GET /readiness` returns `200` when DB + Redis healthy
- [ ] `GET /readiness` returns `503` when Postgres is unreachable
- [ ] Analytics second request within 60s does NOT hit DB (verified via query log)
- [ ] 6th login attempt within 1 minute returns `429 Too Many Requests`
- [ ] Unhandled exception appears in Sentry with correct `org_id` tag
- [ ] All 9 security headers present on every response (`curl -I` verified)

### Performance (Load Test — must pass all three)
- [ ] 50 concurrent chat users: p95 response time < 3000ms
- [ ] 100 concurrent analytics users: p95 response time < 500ms
- [ ] Error rate < 0.1% under load test conditions

### CI/CD
- [ ] Push to `develop` triggers staging deploy and completes within 5 minutes
- [ ] Push to `main` requires manual approval before production deploy
- [ ] Staging deployment URL tested and working after auto-deploy

### Operations
- [ ] DB backup cron runs and backup file appears in S3/storage
- [ ] `alembic upgrade head` runs automatically on deploy (not manually)

### What is NOT Acceptable
- Rate limiting that raises an unhandled exception when Redis is down (must degrade gracefully)
- Sentry that logs sensitive data (passwords, tokens, raw SQL with values)
- Load test failure hidden by increasing thresholds — fix the root cause
- Staging deploy that requires manual SSH intervention
