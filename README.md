# AI Customer Engagement & Lead Conversion Assistant

An AI-powered SaaS platform for coaches, consultants, and small businesses. Answers FAQs via RAG, qualifies leads, books appointments, and automates follow-ups across WhatsApp, Telegram, and web.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, TypeScript, TailwindCSS, ShadCN UI |
| Backend | FastAPI, Python 3.11 |
| AI / RAG | OpenAI, LangChain, ChromaDB |
| Database | PostgreSQL 15 |
| Cache | Redis 7 |
| Auth | JWT + refresh tokens |

## Quick Start

```bash
# 1. Clone and enter
git clone <repo-url> && cd bussi

# 2. Bootstrap (creates .env, installs deps, sets up pre-commit)
./scripts/setup.sh

# 3. Fill in required secrets in .env
#    DATABASE_URL, OPENAI_API_KEY, JWT_SECRET

# 4. Start all services
cd infrastructure && docker compose up
```

- Backend API + docs: http://localhost:8000/api/docs
- Frontend: http://localhost:3000

## Common Commands

```bash
# Backend
cd backend
source .venv/bin/activate
uvicorn api.main:app --reload          # dev server
pytest tests/ -v                       # run tests
ruff check .                           # lint
mypy .                                 # type check
alembic upgrade head                   # run migrations

# Frontend
cd frontend
npm run dev                            # dev server
npm run build                          # production build
npm run lint                           # lint
npx tsc --noEmit                       # type check
```

## Project Structure

```
bussi/
├── backend/       FastAPI app, services, repositories, AI/RAG
├── frontend/      Next.js app, dashboard, chat widget
├── infrastructure/ Docker Compose, nginx config
├── scripts/       Dev utilities
├── phases/        Phase-by-phase build specifications
└── .github/       CI/CD workflows, PR template
```

## Development Phases

See `phases/` directory for detailed specs of all 12 build phases.
