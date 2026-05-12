# Phase 3 — Database Layer

## Objectives
Define and migrate the complete PostgreSQL schema, establish SQLAlchemy ORM models, set up Alembic migrations, and implement the repository pattern so all subsequent phases write zero raw SQL outside `repositories/`.

## Dependencies
- Phase 1 (project scaffolding)
- Phase 2 (users + organizations tables already created by auth migrations)

## Estimated Duration
2–3 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | All 12 tables migrated via Alembic | `alembic upgrade head` runs cleanly on fresh DB |
| 2 | SQLAlchemy ORM models for every table | Full type annotations, relationships defined |
| 3 | Repository classes for every table | No raw SQL outside `repositories/` |
| 4 | Async DB session factory | All queries use `AsyncSession` |
| 5 | Soft-delete mixin applied to all entity tables | `deleted_at IS NULL` filter applied globally |
| 6 | Seed script for local development | `scripts/seed.sh` populates demo org + user |
| 7 | ER diagram generated | `scripts/generate-erd.sh` produces PNG |

---

## Complete Schema

### Entity Relationship Overview
```
organizations ──< users
organizations ──< conversations
organizations ──< documents
organizations ──< leads
organizations ──< integrations
organizations ──< billing_subscriptions
conversations ──< messages
conversations ──> leads (optional)
leads ──< appointments
leads ──< automation_logs
documents ──< embeddings_metadata
users ──< notifications
```

### Full SQL Definitions

```sql
-- Already created in Phase 2:
-- organizations, users, refresh_tokens, password_reset_otps

-- Documents & Knowledge Base
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    uploaded_by     UUID NOT NULL REFERENCES users(id),
    filename        TEXT NOT NULL,
    file_type       VARCHAR(20) NOT NULL,        -- pdf, docx, txt, faq, web
    file_size_bytes INTEGER NOT NULL,
    storage_path    TEXT NOT NULL,               -- S3/local path
    status          VARCHAR(30) NOT NULL DEFAULT 'pending',  -- pending, processing, ready, failed
    chunk_count     INTEGER,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE embeddings_metadata (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    org_id          UUID NOT NULL,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    vector_id       TEXT NOT NULL,               -- ID in ChromaDB/Pinecone
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Conversations & Messages
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    channel         VARCHAR(30) NOT NULL,        -- web, whatsapp, telegram, instagram
    external_id     TEXT,                        -- channel-specific conversation ID
    visitor_id      TEXT,                        -- anonymous or identified
    lead_id         UUID REFERENCES leads(id),
    status          VARCHAR(30) NOT NULL DEFAULT 'open',   -- open, closed, handoff
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    org_id          UUID NOT NULL,
    role            VARCHAR(20) NOT NULL,        -- user, assistant, system
    content         TEXT NOT NULL,
    tokens_used     INTEGER,
    sources         JSONB,                       -- [{doc_id, chunk_index, score}]
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Leads
CREATE TABLE leads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id),
    name            VARCHAR(255),
    email           VARCHAR(255),
    phone           VARCHAR(50),
    budget          NUMERIC(12, 2),
    urgency         VARCHAR(30),                 -- immediate, this_week, this_month, exploring
    service_interest TEXT,
    score           INTEGER NOT NULL DEFAULT 0,  -- 0–100
    category        VARCHAR(20) NOT NULL DEFAULT 'cold',   -- hot, warm, cold
    status          VARCHAR(30) NOT NULL DEFAULT 'new',    -- new, contacted, qualified, converted, lost
    assigned_to     UUID REFERENCES users(id),
    notes           TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

-- Appointments
CREATE TABLE appointments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    lead_id         UUID NOT NULL REFERENCES leads(id),
    external_id     TEXT,                        -- Google Calendar / Calendly event ID
    title           VARCHAR(255) NOT NULL,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    timezone        VARCHAR(100) NOT NULL,
    location        TEXT,
    status          VARCHAR(30) NOT NULL DEFAULT 'scheduled',  -- scheduled, completed, cancelled, no_show
    confirmation_sent BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

-- Automation / Follow-up
CREATE TABLE automation_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    lead_id         UUID REFERENCES leads(id),
    trigger_type    VARCHAR(50) NOT NULL,        -- inactivity_24h, appointment_reminder, discount
    channel         VARCHAR(30) NOT NULL,
    status          VARCHAR(30) NOT NULL,        -- pending, sent, failed, skipped
    scheduled_at    TIMESTAMPTZ NOT NULL,
    executed_at     TIMESTAMPTZ,
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Integrations
CREATE TABLE integrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider        VARCHAR(50) NOT NULL,        -- google_calendar, calendly, whatsapp, telegram
    access_token    TEXT,                        -- encrypted at rest
    refresh_token   TEXT,                        -- encrypted at rest
    token_expires_at TIMESTAMPTZ,
    config          JSONB NOT NULL DEFAULT '{}', -- provider-specific settings
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, provider)
);

-- Billing
CREATE TABLE billing_subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE UNIQUE,
    stripe_customer_id TEXT,
    stripe_sub_id   TEXT,
    plan            VARCHAR(50) NOT NULL DEFAULT 'free',    -- free, starter, pro, enterprise
    status          VARCHAR(30) NOT NULL DEFAULT 'active',  -- active, past_due, cancelled
    current_period_end TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Notifications
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    user_id         UUID REFERENCES users(id),
    type            VARCHAR(50) NOT NULL,        -- new_lead, appointment_booked, follow_up_sent
    title           TEXT NOT NULL,
    body            TEXT,
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Indexes
```sql
CREATE INDEX idx_conversations_org ON conversations(org_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_conversations_channel ON conversations(org_id, channel);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_leads_org ON leads(org_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_leads_category ON leads(org_id, category);
CREATE INDEX idx_leads_status ON leads(org_id, status);
CREATE INDEX idx_appointments_lead ON appointments(lead_id);
CREATE INDEX idx_automation_logs_scheduled ON automation_logs(scheduled_at, status);
CREATE INDEX idx_embeddings_document ON embeddings_metadata(document_id);
CREATE INDEX idx_notifications_user ON notifications(user_id, is_read);
```

---

## SQLAlchemy ORM Setup

### Async Session Factory (`backend/database/session.py`)
```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from backend.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=10,
    max_overflow=20,
    echo=settings.ENVIRONMENT == "development",
)

AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session
```

### Base Model Mixin (`backend/database/base.py`)
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func
from datetime import datetime

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
```

### Repository Pattern (`backend/repositories/lead_repo.py`)
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from backend.models.lead import Lead
from uuid import UUID

class LeadRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, lead_id: UUID, org_id: UUID) -> Lead | None:
        result = await self.db.execute(
            select(Lead).where(
                and_(Lead.id == lead_id, Lead.org_id == org_id, Lead.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    async def list_by_org(self, org_id: UUID, category: str | None = None) -> list[Lead]:
        query = select(Lead).where(and_(Lead.org_id == org_id, Lead.deleted_at.is_(None)))
        if category:
            query = query.where(Lead.category == category)
        result = await self.db.execute(query.order_by(Lead.created_at.desc()))
        return list(result.scalars().all())

    async def create(self, data: dict) -> Lead:
        lead = Lead(**data)
        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)
        return lead
```

---

## Alembic Setup

```
backend/
└── alembic/
    ├── env.py              # import all models, set target_metadata
    ├── versions/
    │   ├── 001_create_orgs_users.py
    │   ├── 002_create_conversations_messages.py
    │   ├── 003_create_documents_embeddings.py
    │   ├── 004_create_leads_appointments.py
    │   ├── 005_create_automation_integrations.py
    │   └── 006_create_billing_notifications.py
    └── alembic.ini
```

Run migrations:
```bash
cd backend
alembic upgrade head          # apply all
alembic downgrade -1          # rollback one
alembic revision --autogenerate -m "add_column_x"
```

---

## Multi-Tenant Isolation Strategy

Every query **must** include `org_id` in the `WHERE` clause. This is enforced via:
1. Repository methods always take `org_id` as a parameter.
2. Services always pull `org_id` from `current_user.org_id` (injected by auth dependency).
3. CI lint check: grep for raw `select(Model)` without `.where(Model.org_id ==` raises a warning.

Tenant data in ChromaDB is isolated via collection naming: `org_{org_id}`.

---

## Validation Checklist

- [ ] `alembic upgrade head` runs on a fresh empty DB without errors
- [ ] `alembic downgrade base` rolls back all migrations cleanly
- [ ] Repository tests pass with a real test DB (not mocked)
- [ ] Soft-deleted records not returned by any list query
- [ ] Cross-tenant data leak test: query for lead with wrong org_id returns `None`
- [ ] All ORM model fields are fully type-annotated
- [ ] `scripts/seed.sh` creates demo data and all FK constraints are satisfied

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Migration runs on prod with missing `asyncpg` | Lock `asyncpg` version in requirements.txt |
| Auto-generated migration misses index | Always review generated migration, add indexes manually |
| JSONB field grows unbounded | Add `pg_column_size()` monitoring alert at 50 KB |

## Rollback Strategy
`alembic downgrade base` drops all tables. For production, every migration must have a `downgrade()` function that reverses the change cleanly.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-3-database-layer
```

### Commit Checkpoints

```bash
# After async session factory + base ORM mixins
git add backend/database/
git commit -m "feat(db): add async SQLAlchemy session factory and base model mixins"

# After each migration file (commit individually)
git add backend/alembic/versions/001_create_orgs_users.py
git commit -m "feat(db): migration 001 — organizations and users tables"

git add backend/alembic/versions/002_create_conversations_messages.py
git commit -m "feat(db): migration 002 — conversations and messages tables"

git add backend/alembic/versions/003_create_documents_embeddings.py
git commit -m "feat(db): migration 003 — documents and embeddings_metadata tables"

git add backend/alembic/versions/004_create_leads_appointments.py
git commit -m "feat(db): migration 004 — leads and appointments tables"

git add backend/alembic/versions/005_create_automation_integrations.py
git commit -m "feat(db): migration 005 — automation_logs and integrations tables"

git add backend/alembic/versions/006_create_billing_notifications.py
git commit -m "feat(db): migration 006 — billing_subscriptions and notifications tables"

# After all ORM models written
git add backend/models/
git commit -m "feat(db): add SQLAlchemy ORM models for all 12 tables"

# After all repository classes written
git add backend/repositories/
git commit -m "feat(db): add repository pattern classes for all entities"

# After seed script
git add scripts/seed.sh
git commit -m "chore(db): add seed script for local development demo data"
```

### Migrate & Verify Before Merging
```bash
# Run migrations on local DB before opening PR
cd backend
alembic upgrade head

# Verify all tables exist
psql $DATABASE_URL -c "\dt"

# Run rollback test
alembic downgrade base
alembic upgrade head    # must work again cleanly
```

### Merge to Develop
```bash
git push -u origin feature/phase-3-database-layer

gh pr create \
  --title "feat: Phase 3 — Database Layer" \
  --body "Complete schema for all 12 tables, Alembic migrations, async ORM models, repository pattern. upgrade/downgrade tested." \
  --base develop
```

---

## Definition of Done

Phase 3 is **complete** when every item below is checked.

### Code Quality
- [ ] Zero raw SQL outside `repositories/` directory
- [ ] Every repository method accepts `org_id` and filters by it (tenant isolation)
- [ ] All ORM model fields fully type-annotated with `Mapped[T]`
- [ ] Soft-delete mixin applied to all entity tables (not junction/log tables)
- [ ] No `session.commit()` calls outside repository methods

### Migrations
- [ ] `alembic upgrade head` runs cleanly on a fresh empty DB
- [ ] `alembic downgrade base` rolls back all migrations without errors
- [ ] `alembic upgrade head` works again after `downgrade base`
- [ ] Every migration has a working `downgrade()` function (not `pass`)
- [ ] All required indexes are explicitly created in migrations (not relying on ORM)

### Functionality
- [ ] `scripts/seed.sh` creates demo org + admin user + sample data without FK errors
- [ ] Soft-deleted records not returned by any list query (verified with direct DB check)
- [ ] Cross-tenant leak test: `lead_repo.get_by_id(id, wrong_org_id)` returns `None`

### Testing
- [ ] `pytest backend/tests/test_repositories.py -v` — all repository tests pass
- [ ] Tests use a real test database (not mocked ORM), rolled back after each test
- [ ] Test coverage for repositories ≥ 80%

### What is NOT Acceptable
- `pass` in any `downgrade()` function
- Raw `session.execute(text("SELECT ..."))` outside repositories
- Missing `WHERE deleted_at IS NULL` filter on any list query
- Migration that cannot be rolled back cleanly
