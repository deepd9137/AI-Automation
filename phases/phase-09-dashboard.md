# Phase 9 — Admin Dashboard

## Objectives
Build the complete admin frontend: analytics overview, lead pipeline, conversation history, document management, settings, and all supporting backend aggregation endpoints.

## Dependencies
- Phase 2 (auth — dashboard requires login)
- Phase 6 (conversations data)
- Phase 7 (leads data)
- Phase 8 (appointments data)
- Phase 5 (documents data)

## Estimated Duration
4–5 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | Analytics overview page | KPI cards with real DB data |
| 2 | Lead pipeline board | Kanban-style with drag-drop status change |
| 3 | Conversation history browser | Searchable, filterable transcript viewer |
| 4 | Document upload & management page | Upload, processing status, delete |
| 5 | Settings page | Prompt editor, AI behavior, integrations, team members |
| 6 | Responsive layout | Works on tablet (768px+) |
| 7 | `GET /analytics/overview` API | Aggregated stats with time-range filter |
| 8 | Navigation sidebar | Collapsible, active route highlighting |

---

## Backend: Analytics API

### Endpoint: `GET /api/v1/analytics/overview`

Query params: `period=7d|30d|90d|all`

```python
# backend/routes/analytics.py
@router.get("/overview")
async def get_overview(
    period: str = "30d",
    current_user=Depends(require_role("org_admin", "agent")),
    db: AsyncSession = Depends(get_db),
):
    org_id = current_user.org_id
    date_from = get_date_from_period(period)

    return {
        "conversations": {
            "total": await count_conversations(db, org_id, date_from),
            "by_channel": await count_by_channel(db, org_id, date_from),
            "trend": await daily_trend(db, org_id, "conversations", date_from),
        },
        "leads": {
            "total": await count_leads(db, org_id, date_from),
            "hot": await count_leads_by_category(db, org_id, "hot", date_from),
            "warm": await count_leads_by_category(db, org_id, "warm", date_from),
            "cold": await count_leads_by_category(db, org_id, "cold", date_from),
            "conversion_rate": await calculate_conversion_rate(db, org_id, date_from),
            "trend": await daily_trend(db, org_id, "leads", date_from),
        },
        "appointments": {
            "total": await count_appointments(db, org_id, date_from),
            "upcoming": await count_upcoming_appointments(db, org_id),
        },
        "ai_usage": {
            "total_tokens": await sum_tokens(db, org_id, date_from),
            "cost_estimate_usd": await estimate_cost(db, org_id, date_from),
        },
    }
```

### Additional Analytics Endpoints
```
GET /api/v1/analytics/overview           — KPI summary
GET /api/v1/analytics/leads/funnel       — pipeline stage counts
GET /api/v1/analytics/conversations/daily — 30-day message volume
GET /api/v1/analytics/tokens/monthly     — token usage per day for billing
```

---

## Frontend Architecture

### Layout & Routing
```
frontend/app/
├── (auth)/
│   ├── login/page.tsx
│   └── register/page.tsx
└── dashboard/
    ├── layout.tsx              ← sidebar + topbar wrapper
    ├── page.tsx                ← analytics overview (default)
    ├── leads/
    │   ├── page.tsx            ← lead table (from Phase 7)
    │   └── [id]/page.tsx       ← lead detail
    ├── conversations/
    │   ├── page.tsx            ← conversation list
    │   └── [id]/page.tsx       ← transcript view
    ├── appointments/
    │   └── page.tsx            ← calendar view (from Phase 8)
    ├── documents/
    │   └── page.tsx            ← upload + list
    └── settings/
        ├── page.tsx            ← general settings
        ├── prompts/page.tsx    ← AI prompt editor
        ├── integrations/page.tsx ← connect calendar/channels
        └── team/page.tsx       ← user management
```

### Sidebar Component
```typescript
// frontend/components/dashboard/Sidebar.tsx
const NAV_ITEMS = [
  { label: "Overview",       href: "/dashboard",              icon: LayoutDashboard },
  { label: "Leads",          href: "/dashboard/leads",         icon: Users },
  { label: "Conversations",  href: "/dashboard/conversations", icon: MessageSquare },
  { label: "Appointments",   href: "/dashboard/appointments",  icon: Calendar },
  { label: "Documents",      href: "/dashboard/documents",     icon: FileText },
  { label: "Settings",       href: "/dashboard/settings",      icon: Settings },
];
```

---

## Analytics Overview Page

### KPI Cards

```typescript
// frontend/app/dashboard/page.tsx
export default function DashboardPage() {
  const { data } = useSWR("/api/v1/analytics/overview?period=30d", fetcher);

  return (
    <div className="space-y-6">
      <PeriodSelector />                    {/* 7d | 30d | 90d */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard title="Total Conversations" value={data?.conversations.total} trend={...} />
        <KPICard title="Active Leads"        value={data?.leads.total} />
        <KPICard title="Hot Leads"           value={data?.leads.hot} color="red" />
        <KPICard title="Conversion Rate"     value={`${data?.leads.conversion_rate}%`} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <ConversationTrendChart data={data?.conversations.trend} />
        <LeadFunnelChart data={data?.leads} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <UpcomingAppointments />
        <RecentLeads />
      </div>
    </div>
  );
}
```

### KPI Card Component
```typescript
interface KPICardProps {
  title: string;
  value: number | string;
  trend?: { value: number; direction: "up" | "down" };
  color?: "default" | "red" | "green" | "yellow";
}

function KPICard({ title, value, trend, color = "default" }: KPICardProps) {
  return (
    <Card className="p-6">
      <p className="text-sm text-muted-foreground">{title}</p>
      <p className="text-3xl font-bold mt-1">{value ?? "—"}</p>
      {trend && (
        <TrendBadge value={trend.value} direction={trend.direction} />
      )}
    </Card>
  );
}
```

---

## Lead Pipeline Board

Kanban columns: New → Contacted → Qualified → Converted | Lost

```typescript
// frontend/app/dashboard/leads/pipeline/page.tsx
// Uses @hello-pangea/dnd (maintained fork of react-beautiful-dnd)

const COLUMNS = ["new", "contacted", "qualified", "converted", "lost"];

function LeadPipelineBoard({ leads }: { leads: Lead[] }) {
  const grouped = groupBy(leads, "status");

  async function onDragEnd(result: DropResult) {
    if (!result.destination) return;
    const leadId = result.draggableId;
    const newStatus = result.destination.droppableId;
    await updateLeadStatus(leadId, newStatus);  // PATCH /leads/{id}
  }

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <div className="flex gap-4 overflow-x-auto pb-4">
        {COLUMNS.map(col => (
          <PipelineColumn key={col} status={col} leads={grouped[col] ?? []} />
        ))}
      </div>
    </DragDropContext>
  );
}
```

---

## Document Upload Page

```typescript
// frontend/app/dashboard/documents/page.tsx
function DocumentsPage() {
  const [uploading, setUploading] = useState(false);

  async function onDrop(files: File[]) {
    setUploading(true);
    const formData = new FormData();
    formData.append("file", files[0]);
    const res = await fetch("/api/v1/documents/upload", { method: "POST", body: formData });
    const { document_id } = await res.json();
    // Start polling status
    pollDocumentStatus(document_id);
    setUploading(false);
  }

  return (
    <div>
      <Dropzone onDrop={onDrop} accept={{ "application/pdf": [], "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [], "text/plain": [] }}>
        {/* drag & drop zone */}
      </Dropzone>
      <DocumentTable />
    </div>
  );
}
```

Status polling: 2-second interval until `status === "ready"` or `"failed"`.

---

## Settings: Prompt Editor

```typescript
// frontend/app/dashboard/settings/prompts/page.tsx
function PromptEditor() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      {prompts.map(p => (
        <Card key={p.id}>
          <CardHeader>
            <CardTitle>{p.name}</CardTitle>
            <Badge variant="outline">v{p.version}</Badge>
          </CardHeader>
          <CardContent>
            {editing === p.id ? (
              <Textarea defaultValue={p.content} rows={10} />
            ) : (
              <pre className="text-sm bg-muted p-3 rounded">{p.content}</pre>
            )}
          </CardContent>
          <CardFooter>
            <Button onClick={() => setEditing(p.id)}>Edit</Button>
            <Button variant="outline">Test Render</Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
}
```

---

## Design System Conventions

| Token | Value |
|---|---|
| Primary color | Indigo 600 (`#4F46E5`) |
| Danger | Red 500 |
| Success | Green 500 |
| Warning | Amber 500 |
| Background | Slate 50 |
| Card | White, `shadow-sm`, `rounded-xl` |
| Font | Inter (via `next/font`) |
| Spacing unit | 4px (Tailwind default) |

ShadCN components used: `Button`, `Card`, `Badge`, `Table`, `Dialog`, `Sheet`, `Select`, `Input`, `Textarea`, `Tabs`, `Alert`.

All data fetching via SWR (`useSWR`). Mutations via direct `fetch` + optimistic UI updates.

---

## Loading & Error States

Every data-fetching component must handle:
```typescript
if (isLoading) return <Skeleton className="h-32 w-full" />;
if (error) return <Alert variant="destructive">Failed to load data. <Button onClick={retry}>Retry</Button></Alert>;
```

---

## Validation Checklist

- [ ] Dashboard loads with real data within 2 seconds (DB query time < 500ms)
- [ ] KPI cards show correct numbers matching direct DB counts
- [ ] Lead pipeline drag-drop updates status in DB and re-renders immediately
- [ ] Document upload shows progress, transitions to "ready" without page refresh
- [ ] Prompt save creates new version in DB; next chat uses updated prompt
- [ ] Dashboard inaccessible without valid JWT (redirects to `/login`)
- [ ] Sidebar highlights active route correctly
- [ ] Responsive layout renders correctly on 768px viewport
- [ ] Token usage card stays within 5% of actual OpenAI bill

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Analytics queries slow on large datasets | Add DB indexes in Phase 3; add caching (Redis) in Phase 11 |
| SWR caches stale lead counts | Use `mutate()` after status changes; set `refreshInterval=30000` |
| Prompt editor breaks production AI | Add "test render" before save; version history allows rollback |

## Rollback Strategy
Dashboard is read-only with a few write operations (lead status, prompt edit). Rollback = redeploy previous frontend build (Vercel instant rollback). Backend analytics endpoints have no side effects.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-9-dashboard
```

### Commit Checkpoints

```bash
# After analytics aggregation queries + API endpoints
git add backend/routes/analytics.py backend/services/analytics_service.py
git commit -m "feat(dashboard): add analytics overview API with time-range filtering"

# After dashboard layout (sidebar + topbar)
git add frontend/app/dashboard/layout.tsx frontend/components/dashboard/
git commit -m "feat(dashboard): add responsive sidebar navigation and dashboard layout"

# After analytics overview page (KPI cards + charts)
git add frontend/app/dashboard/page.tsx frontend/components/dashboard/KPICard.tsx
git commit -m "feat(dashboard): add analytics overview with KPI cards and trend charts"

# After lead pipeline board (kanban)
git add frontend/app/dashboard/leads/pipeline/
git commit -m "feat(dashboard): add kanban lead pipeline board with drag-drop status update"

# After conversation history browser
git add frontend/app/dashboard/conversations/
git commit -m "feat(dashboard): add conversation history browser with transcript viewer"

# After document upload page
git add frontend/app/dashboard/documents/
git commit -m "feat(dashboard): add document upload page with processing status polling"

# After settings pages (prompts, integrations, team)
git add frontend/app/dashboard/settings/
git commit -m "feat(dashboard): add settings pages for prompts, integrations, and team members"
```

### Verify Data Accuracy Before Merging
```bash
# Compare KPI card counts against direct DB queries
psql $DATABASE_URL -c "SELECT COUNT(*) FROM leads WHERE org_id='...' AND deleted_at IS NULL;"
# Must match the "Total Leads" KPI card value
```

### Merge to Develop
```bash
git push -u origin feature/phase-9-dashboard

gh pr create \
  --title "feat: Phase 9 — Admin Dashboard" \
  --body "Analytics overview, lead pipeline kanban, conversation viewer, document upload, settings with prompt editor." \
  --base develop
```

---

## Definition of Done

Phase 9 is **complete** when every item below is checked.

### Code Quality
- [ ] All dashboard pages use SWR for data fetching — no `useEffect + fetch` anti-patterns
- [ ] Loading and error states handled in every data-fetching component
- [ ] No hardcoded org IDs or test data in any frontend component
- [ ] KPI values formatted with `toLocaleString()` — no raw numbers displayed
- [ ] Prompt editor shows version number and prompts save as new version (not overwrite)

### Functionality
- [ ] Dashboard inaccessible without valid JWT — redirects to `/login`
- [ ] KPI card values match direct DB counts within ±1 (timing edge case)
- [ ] Lead pipeline drag-drop updates status in DB and re-renders without page reload
- [ ] Document upload shows progress, transitions to "ready" status without page refresh
- [ ] Prompt save creates new version in DB; next chat message uses updated prompt
- [ ] Sidebar highlights active route correctly on all 6 main sections
- [ ] Period selector (7d/30d/90d) updates all KPI cards correctly

### Responsiveness
- [ ] Layout renders without horizontal scroll at 768px viewport width
- [ ] Sidebar collapses to icon-only on < 1024px viewport

### Performance
- [ ] Analytics overview page loads data in < 2 seconds (DB query time < 500ms)
- [ ] Lead table with 100 rows renders without visible lag

### Testing
- [ ] `pytest backend/tests/test_analytics.py -v` — all tests pass
- [ ] Analytics queries return correct counts for known seed data
- [ ] Frontend: key pages render without errors in CI (Next.js build passes)

### What is NOT Acceptable
- Dashboard page that shows data from another org (cross-tenant UI leak)
- Prompt edit that overwrites existing version (must create new version)
- Missing loading state (blank screen while data loads)
- Analytics numbers that don't match DB (off-by-more-than-1 discrepancy)
