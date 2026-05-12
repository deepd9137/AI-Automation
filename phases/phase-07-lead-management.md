# Phase 7 — Lead Management

## Objectives
Build the complete lead lifecycle: scoring engine, hot/warm/cold categorization, admin CRUD, status pipeline, CSV export, and the lead management UI. Leads created in Phase 6 become actionable here.

## Dependencies
- Phase 2 (auth — only org_admin/agent can manage leads)
- Phase 3 (leads table)
- Phase 6 (chat system creates leads via LeadExtractionService)

## Estimated Duration
3–4 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | Lead scoring engine | Score 0–100 calculated on create/update |
| 2 | Hot/warm/cold categorization | Derived from score automatically |
| 3 | `GET /leads` with filters/search/sort | Returns paginated, filterable list |
| 4 | `GET /leads/{id}` with conversation link | Full lead detail with history |
| 5 | `PATCH /leads/{id}` — update status/notes | Status transitions validated |
| 6 | `GET /leads/export` — CSV download | All leads for org, filterable by date |
| 7 | Lead management table UI | Sortable, filterable, action buttons |
| 8 | Lead detail drawer/page | Full profile, conversation replay, status actions |

---

## Lead Scoring Engine

### Scoring Criteria

| Field | Condition | Points |
|---|---|---|
| `email` | present | +20 |
| `phone` | present | +15 |
| `name` | present | +10 |
| `budget` | > 0 | +15 |
| `urgency` | `immediate` | +25 |
| `urgency` | `this_week` | +15 |
| `urgency` | `this_month` | +8 |
| `urgency` | `exploring` | +2 |
| `service_interest` | present | +10 |
| `budget` | > 5000 | +5 bonus |
| Max score | | 100 |

### Categorization

| Score Range | Category |
|---|---|
| 70–100 | `hot` |
| 40–69 | `warm` |
| 0–39 | `cold` |

### Implementation (`backend/services/lead_service.py`)

```python
from backend.schemas.lead import LeadCreate, LeadOut
from backend.repositories.lead_repo import LeadRepository

def calculate_score(data: dict) -> int:
    score = 0
    if data.get("email"):         score += 20
    if data.get("phone"):         score += 15
    if data.get("name"):          score += 10
    if data.get("service_interest"): score += 10
    budget = data.get("budget") or 0
    if budget > 0:                score += 15
    if budget > 5000:             score += 5
    urgency_scores = {"immediate": 25, "this_week": 15, "this_month": 8, "exploring": 2}
    score += urgency_scores.get(data.get("urgency", ""), 0)
    return min(score, 100)

def categorize(score: int) -> str:
    if score >= 70:  return "hot"
    if score >= 40:  return "warm"
    return "cold"

class LeadService:
    def __init__(self, repo: LeadRepository):
        self.repo = repo

    async def create_lead(self, org_id: str, data: dict) -> LeadOut:
        score = calculate_score(data)
        data["score"] = score
        data["category"] = categorize(score)
        data["org_id"] = org_id
        lead = await self.repo.create(data)
        return LeadOut.model_validate(lead)

    async def update_lead(self, lead_id: str, org_id: str, updates: dict) -> LeadOut:
        # Recalculate score if scoring fields changed
        scoring_fields = {"email", "phone", "name", "budget", "urgency", "service_interest"}
        if updates.keys() & scoring_fields:
            current = await self.repo.get_by_id(lead_id, org_id)
            merged = {**current.__dict__, **updates}
            updates["score"] = calculate_score(merged)
            updates["category"] = categorize(updates["score"])
        lead = await self.repo.update(lead_id, org_id, updates)
        return LeadOut.model_validate(lead)
```

---

## Status Machine

```
new ──────► contacted ──► qualified ──► converted
 │                │            │
 └──────────────► lost ◄───────┘
```

Valid transitions:
```python
VALID_TRANSITIONS = {
    "new":       {"contacted", "lost"},
    "contacted": {"qualified", "lost"},
    "qualified": {"converted", "lost"},
    "converted": set(),
    "lost":      set(),
}

def validate_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())
```

---

## API Endpoints

```
GET    /api/v1/leads
  Query params: category, status, assigned_to, search, sort_by, order, page, limit
  Returns: { items: [Lead], total, page, limit }

GET    /api/v1/leads/{id}
  Returns: Lead + conversation_summary

POST   /api/v1/leads
  Body: LeadCreate (manual creation from admin)
  Returns: Lead

PATCH  /api/v1/leads/{id}
  Body: LeadUpdate (status, notes, assigned_to, any field)
  Returns: updated Lead

DELETE /api/v1/leads/{id}
  Soft delete (deleted_at set)

GET    /api/v1/leads/export
  Query: format=csv, date_from, date_to, category
  Returns: CSV file download (Content-Disposition: attachment)
```

### Pagination Standard
```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def from_query(cls, items, total, page, limit):
        return cls(items=items, total=total, page=page, limit=limit,
                   pages=ceil(total / limit))
```

### Lead Schemas (`backend/schemas/lead.py`)
```python
from pydantic import BaseModel, EmailStr
from decimal import Decimal

class LeadCreate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    budget: Decimal | None = None
    urgency: str | None = None
    service_interest: str | None = None
    conversation_id: str | None = None

class LeadUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    budget: Decimal | None = None
    urgency: str | None = None
    service_interest: str | None = None
    status: str | None = None
    assigned_to: str | None = None
    notes: str | None = None

class LeadOut(BaseModel):
    id: str
    org_id: str
    name: str | None
    email: str | None
    phone: str | None
    budget: Decimal | None
    urgency: str | None
    service_interest: str | None
    score: int
    category: str
    status: str
    assigned_to: str | None
    notes: str | None
    conversation_id: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
```

---

## CSV Export Implementation

```python
import csv
import io
from fastapi.responses import StreamingResponse

async def export_leads_csv(org_id: str, db) -> StreamingResponse:
    leads = await LeadRepository(db).list_all_for_export(org_id)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "name", "email", "phone", "budget", "urgency",
        "service_interest", "score", "category", "status",
        "assigned_to", "notes", "created_at",
    ])
    writer.writeheader()
    for lead in leads:
        writer.writerow({
            "id": str(lead.id),
            "name": lead.name or "",
            "email": lead.email or "",
            # ... etc
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
```

---

## Frontend: Lead Management UI

### Pages
```
frontend/app/dashboard/leads/
├── page.tsx              # lead table page
└── [id]/page.tsx         # lead detail page
```

### Lead Table (`dashboard/leads/page.tsx`)

Components used:
- ShadCN `DataTable` with sortable columns
- `Badge` for category (hot=red, warm=yellow, cold=blue)
- `Select` for status filter
- `Input` for search
- `Button` for export CSV

Column config:
```typescript
const columns: ColumnDef<Lead>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "email", header: "Email" },
  { accessorKey: "category",
    cell: ({ row }) => <CategoryBadge category={row.original.category} /> },
  { accessorKey: "score",
    cell: ({ row }) => <ScoreBar score={row.original.score} /> },
  { accessorKey: "status",
    cell: ({ row }) => <StatusSelect lead={row.original} /> },
  { accessorKey: "created_at", header: "Created" },
  { id: "actions",
    cell: ({ row }) => <LeadActions lead={row.original} /> },
];
```

### Lead Detail Drawer
Slides in from the right when a row is clicked. Shows:
- Full contact info (editable inline)
- Score breakdown (which fields contributed)
- Conversation transcript (linked from Phase 6)
- Status action buttons (Progress to next stage / Mark Lost)
- Notes field (auto-save on blur)
- Appointment history (Phase 8 data)

---

## Validation Checklist

- [ ] Lead created by chat has correct score calculated
- [ ] `urgency=immediate` + `email present` + `phone present` = score ≥ 60 = `warm`
- [ ] Transition `new → converted` returns `400` (invalid transition)
- [ ] Export CSV contains all leads, no other org's data
- [ ] Search by email finds lead case-insensitively
- [ ] `agent` role cannot delete leads (returns `403`)
- [ ] Lead score recalculated when `urgency` is updated via `PATCH`
- [ ] Pagination: 25 leads with `limit=10` returns 3 pages

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Score algorithm too simple → low accuracy | Make weights configurable per org via settings table |
| LLM extraction misses fields → incomplete lead | Score reflects what's available; admin can fill gaps manually |
| CSV export times out for large lead sets | Stream response, paginate DB query by 500 rows |

## Rollback Strategy
Leads are the primary business data. Do not drop the leads table. Status changes are reversible — an admin can manually move leads back. For schema changes: Alembic `downgrade` only if column added (non-destructive). Never drop the leads table in a rollback.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-7-lead-management
```

### Commit Checkpoints

```bash
# After scoring engine + categorization logic
git add backend/services/lead_service.py
git commit -m "feat(leads): add lead scoring engine (0-100) and hot/warm/cold categorization"

# After status machine + transition validation
git commit -m "feat(leads): add lead status machine with valid transition enforcement"

# After lead repository
git add backend/repositories/lead_repo.py
git commit -m "feat(leads): add LeadRepository with pagination and org-scoped queries"

# After REST API endpoints (CRUD + export)
git add backend/routes/leads.py backend/schemas/lead.py
git commit -m "feat(leads): add lead CRUD, search, filter, pagination, and CSV export endpoints"

# After lead table UI
git add frontend/app/dashboard/leads/page.tsx
git commit -m "feat(leads): add sortable, filterable lead management table with category badges"

# After lead detail drawer
git add frontend/app/dashboard/leads/\[id\]/
git commit -m "feat(leads): add lead detail page with inline editing and status actions"
```

### Verify Score Calculations Before Merging
```bash
# Quick scoring sanity check via API
curl -X POST http://localhost:8000/api/v1/leads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Jane","email":"jane@co.com","phone":"555-1234","budget":5000,"urgency":"immediate","service_interest":"coaching"}'
# Expected: score=90, category="hot"
```

### Merge to Develop
```bash
git push -u origin feature/phase-7-lead-management

gh pr create \
  --title "feat: Phase 7 — Lead Management" \
  --body "Lead scoring, status machine, CRUD API with pagination, CSV export, lead table + detail UI." \
  --base develop
```

---

## Definition of Done

Phase 7 is **complete** when every item below is checked.

### Code Quality
- [ ] Score calculation is a pure function — no DB calls inside `calculate_score()`
- [ ] Status transition validation runs before every `PATCH` — no direct status field writes
- [ ] No business logic in route handlers — all in `LeadService`
- [ ] CSV export streams the response — never loads all leads into memory at once

### Functionality
- [ ] Lead created by chat (Phase 6) has correct score calculated automatically
- [ ] `urgency=immediate` + `email` + `phone` + `name` = score ≥ 65 = `warm` or `hot`
- [ ] `PATCH` with `urgency` change recalculates score and updates `category`
- [ ] Invalid transition (`new → converted`) returns `400` with explanation
- [ ] Search by email is case-insensitive
- [ ] `viewer` role cannot `POST`, `PATCH`, or `DELETE` leads (returns `403`)
- [ ] CSV export contains correct headers and all org leads, no other org's data
- [ ] Pagination: 25 leads, `limit=10` → 3 pages, `page=3` has 5 items

### Testing
- [ ] `pytest backend/tests/test_leads.py -v` — all tests pass
- [ ] Score calculation unit tests cover all scoring field combinations
- [ ] Status machine tests cover all valid AND invalid transitions
- [ ] Test coverage for `services/lead_service.py` ≥ 85%

### What is NOT Acceptable
- Score not recalculated when scoring fields are updated
- Status transition bypassed by writing directly to the `status` field without validation
- `agent` or `viewer` roles able to delete leads
- CSV export that loads all rows into a Python list before writing
