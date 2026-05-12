# Phase 1 — Project Setup

## Objectives
Bootstrap the monorepo, establish tooling, configure environments, and ensure every developer (or AI agent) can run the full stack locally within 15 minutes of cloning.

## Dependencies
None — this is the foundation phase.

## Estimated Duration
1–2 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | Monorepo root with `backend/` and `frontend/` | Directories exist, `.gitignore` in place |
| 2 | Backend: FastAPI skeleton boots | `GET /health` returns `{"status":"ok"}` |
| 3 | Frontend: Next.js skeleton boots | `localhost:3000` renders a page |
| 4 | Docker Compose wires all services | `docker compose up` starts postgres + backend + frontend |
| 5 | Pre-commit hooks installed | `ruff`, `black`, `mypy`, `eslint` run on `git commit` |
| 6 | `.env.example` committed | All variables documented, no defaults containing real secrets |
| 7 | CI pipeline green on first push | GitHub Actions lint + type-check job passes |

---

## Folder Structure to Create

```
/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py            # FastAPI app factory
│   ├── core/
│   │   ├── config.py          # Pydantic BaseSettings — reads .env
│   │   └── logging.py         # Structured JSON logger setup
│   ├── routes/
│   │   └── health.py
│   ├── tests/
│   │   └── test_health.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pyproject.toml         # ruff + black + mypy config
│   └── Dockerfile
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   ├── lib/
│   │   └── api.ts             # Axios/fetch base client
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── .eslintrc.json
│   └── Dockerfile
│
├── infrastructure/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── nginx/
│       └── nginx.conf
│
├── scripts/
│   ├── setup.sh               # One-command dev bootstrap
│   └── validate-env.sh        # Checks all required vars are set
│
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   └── PULL_REQUEST_TEMPLATE.md
│
├── .env.example
├── .gitignore
└── README.md
```

---

## Architecture Detail

### Backend App Factory (`backend/api/main.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.routes.health import router as health_router

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Engagement Assistant",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api/v1")
    return app

app = create_app()
```

### Config (`backend/core/config.py`)
All environment variables go through Pydantic `BaseSettings`. Missing required vars raise at startup — fail fast.
```python
from pydantic_settings import BaseSettings
from typing import list

class Settings(BaseSettings):
    DATABASE_URL: str
    OPENAI_API_KEY: str
    JWT_SECRET: str
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()
```

### Docker Compose (`infrastructure/docker-compose.yml`)
```yaml
version: "3.9"
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: engagement_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  backend:
    build: ../backend
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    env_file: ../.env
    ports: ["8000:8000"]
    depends_on: [postgres]

  frontend:
    build: ../frontend
    command: npm run dev
    ports: ["3000:3000"]
    depends_on: [backend]

volumes:
  pgdata:
```

### CI Pipeline (`.github/workflows/ci.yml`)
```yaml
name: CI
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r backend/requirements-dev.txt
      - run: ruff check backend/
      - run: mypy backend/
      - run: pytest backend/tests/ -v

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - run: cd frontend && npx tsc --noEmit
```

---

## Pre-commit Hooks (`pyproject.toml` excerpt)
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "UP"]

[tool.black]
line-length = 100

[tool.mypy]
strict = true
```

Frontend: `.eslintrc.json` extends `"next/core-web-vitals"` and `"typescript-eslint/recommended"`.

---

## Environment Variables (`.env.example`)
```
# App
ENVIRONMENT=development
SECRET_KEY=change-me

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/engagement_db

# AI
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o

# Auth
JWT_SECRET=change-me-32-chars-minimum
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Vector DB
CHROMA_PERSIST_DIR=./data/chroma

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1

# CORS
ALLOWED_ORIGINS=["http://localhost:3000"]
```

---

## Validation Checklist

- [ ] `docker compose up` starts without errors
- [ ] `curl http://localhost:8000/api/v1/health` returns `200 {"status":"ok"}`
- [ ] `localhost:3000` renders without console errors
- [ ] `git commit` triggers pre-commit hooks and they pass on clean code
- [ ] GitHub Actions CI runs and passes on push
- [ ] `.env.example` has every variable used in `config.py`
- [ ] `scripts/validate-env.sh` errors if `OPENAI_API_KEY` is not set

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Port conflicts on dev machine | Document in README; add `ports` override in `docker-compose.override.yml` |
| Python version mismatch | Pin `python-version = "3.11"` in pyproject and CI |
| Node version drift | `.nvmrc` at repo root pinned to `20` |

## Rollback Strategy
Phase 1 is pure scaffolding — no data, no users. Any broken state can be fixed by deleting generated files and re-running `scripts/setup.sh`.

---

## Git Workflow

### Branch
```bash
git checkout -b feature/phase-1-project-setup
```

### Commit Checkpoints
Commit after each milestone — never batch all changes into one end-of-phase commit.

```bash
# After monorepo scaffold + .gitignore + .env.example
git add backend/ frontend/ infrastructure/ scripts/ .gitignore .env.example
git commit -m "feat(setup): scaffold monorepo with backend and frontend directories"

# After FastAPI skeleton boots with /health
git add backend/
git commit -m "feat(setup): add FastAPI app factory with health endpoint"

# After Next.js skeleton boots
git add frontend/
git commit -m "feat(setup): add Next.js skeleton with TailwindCSS and ShadCN"

# After Docker Compose is wired and tested
git add infrastructure/
git commit -m "feat(setup): add Docker Compose for postgres, backend, frontend"

# After pre-commit hooks + linting config
git add pyproject.toml .eslintrc.json .pre-commit-config.yaml
git commit -m "chore(setup): add ruff, black, mypy, eslint pre-commit hooks"

# After CI pipeline passes
git add .github/
git commit -m "ci: add GitHub Actions lint + type-check + test workflow"
```

### Merge to Develop
```bash
# Push branch
git push -u origin feature/phase-1-project-setup

# Open PR → develop (do not merge to main directly)
gh pr create \
  --title "feat: Phase 1 — Project Setup" \
  --body "Scaffolds monorepo, Docker Compose, CI pipeline, pre-commit hooks. All checklist items pass." \
  --base develop

# After PR approved and merged:
git checkout develop && git pull
```

---

## Definition of Done

Phase 1 is **complete** when every item below is checked. Do not begin Phase 2 until all pass.

### Code Quality
- [ ] All Python files pass `ruff check backend/` with zero errors
- [ ] All Python files pass `mypy backend/` with zero errors (strict mode)
- [ ] All TypeScript files pass `npx tsc --noEmit` with zero errors
- [ ] `npm run lint` passes with zero errors
- [ ] No hardcoded secrets, API keys, or passwords in any file
- [ ] `.env.example` has every variable referenced in `config.py` and `next.config.ts`

### Functionality
- [ ] `docker compose up` starts all services without errors on a clean machine
- [ ] `GET /api/v1/health` returns `{"status": "ok"}` with HTTP 200
- [ ] `GET http://localhost:3000` renders without browser console errors
- [ ] `GET /readiness` (if added) is wired to docker HEALTHCHECK
- [ ] `scripts/validate-env.sh` exits non-zero when `OPENAI_API_KEY` is missing

### Testing & CI
- [ ] `pytest backend/tests/test_health.py -v` passes
- [ ] GitHub Actions CI workflow runs and is green on the branch
- [ ] Pre-commit hooks fire on `git commit` and block commits with lint errors

### Documentation
- [ ] `README.md` has one-command local setup instructions
- [ ] `CLAUDE.md` updated if folder structure changed

### What is NOT Acceptable
- Skipping pre-commit hook setup ("I'll add it later")
- Committing with `--no-verify`
- `.env` file committed to git (not just `.env.example`)
- Docker Compose that only works on the author's machine
