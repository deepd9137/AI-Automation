# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **greenfield project** — no code exists yet. `first.md` contains the full product specification for an AI-powered Customer Engagement & Lead Conversion Assistant (SaaS MVP) targeting coaches, consultants, and small businesses.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js + TypeScript + TailwindCSS + ShadCN UI |
| Backend | FastAPI (Python) |
| AI / RAG | OpenAI API + LangChain + ChromaDB (Pinecone-ready) |
| Database | PostgreSQL |
| Auth | JWT |
| Deployment | Vercel (frontend), Railway/Render (backend) |

## Intended Architecture

```
backend/
├── api/          # FastAPI app entrypoint, middleware, rate limiting
├── routes/       # Route handlers (chat, leads, appointments, admin, auth)
├── services/     # Business logic layer (lead scoring, follow-up, booking)
├── agents/       # LangChain agents / orchestration logic
├── rag/          # Document ingestion, chunking, embedding, retrieval pipeline
├── database/     # SQLAlchemy models, Alembic migrations, session management
├── models/       # Pydantic schemas (request/response DTOs)
├── auth/         # JWT middleware, RBAC helpers
├── scheduler/    # Celery/APScheduler tasks for follow-up automation
├── integrations/ # Google Calendar, Calendly, WhatsApp, Telegram, Instagram
└── utils/        # Shared helpers

frontend/
├── app/          # Next.js App Router pages
├── components/   # Shared UI components (ShadCN-based)
├── dashboard/    # Admin dashboard: analytics, lead table, doc upload, settings
├── chat-widget/  # Floating embeddable chat widget
├── hooks/        # Custom React hooks
└── services/     # API client / fetch wrappers
```

## Core System Flow

1. User message → FastAPI receives request
2. Conversation manager loads session context
3. RAG pipeline retrieves relevant document chunks
4. LLM (OpenAI) generates answer with citations
5. Lead extraction analyzes intent → scores lead (hot/warm/cold)
6. If high-intent: collect lead info, suggest appointment
7. Persist conversation + lead data to PostgreSQL
8. Scheduler evaluates whether to trigger follow-up workflows

## Database Schema (to implement)

Tables: `users`, `businesses`, `documents`, `embeddings_metadata`, `conversations`, `messages`, `leads`, `appointments`, `automation_logs`

Multi-tenant: every row scoped to a `business_id` for SaaS isolation.

## Key Design Constraints

- **Multi-tenant from day one**: separate knowledge bases per business; all queries must be scoped by `business_id`.
- **Vector DB abstraction**: implement a `VectorStore` interface so ChromaDB can be swapped for Pinecone without changing the RAG pipeline.
- **Channel abstraction**: message ingestion should be channel-agnostic so WhatsApp/Telegram/Instagram/website share one processing pipeline.
- **RAG confidence threshold**: if retrieval confidence is below threshold, return a fallback response instead of hallucinating.
- **RBAC-ready**: auth layer should support role checks even if only `admin` role is active in MVP.

## Development Setup (to establish)

Once the project is scaffolded, expected commands will be:

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload

# Run a single test
pytest tests/path/to/test_file.py::test_function_name -v

# Frontend
cd frontend
npm install
npm run dev

# Lint / type check
npm run lint
npx tsc --noEmit        # frontend
ruff check backend/     # backend
mypy backend/           # backend
```

## Environment Variables (template in `.env.example`)

```
OPENAI_API_KEY=
DATABASE_URL=postgresql://...
JWT_SECRET=
CHROMA_PERSIST_DIR=
GOOGLE_CALENDAR_CLIENT_ID=
GOOGLE_CALENDAR_CLIENT_SECRET=
CALENDLY_API_KEY=
WHATSAPP_TOKEN=
TELEGRAM_BOT_TOKEN=
```
