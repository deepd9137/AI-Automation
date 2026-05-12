# Phase 4 — AI Integration Layer

## Objectives
Wire OpenAI into the backend as a managed service layer. Establish the LLM client, prompt management system, token tracking, cost controls, and hallucination guards. This phase does **not** build the RAG pipeline — it establishes the primitives that the RAG pipeline (Phase 5) and chat system (Phase 6) will use.

## Dependencies
- Phase 1 (project scaffold)
- Phase 2 (auth — org_id available on every request)
- Phase 3 (DB layer — token usage persisted)

## Estimated Duration
2–3 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | `AIClient` singleton with retry + timeout | All OpenAI calls go through it |
| 2 | `PromptManager` — loads, versions, renders system prompts | Prompts live in DB, not hardcoded strings |
| 3 | Token usage logger | Every LLM call records prompt/completion tokens to DB |
| 4 | Cost guard middleware | Org over monthly token budget gets `429` |
| 5 | Streaming support | `/chat/stream` endpoint returns SSE |
| 6 | Embedding service | `get_embedding(text)` returns `list[float]` |
| 7 | `POST /admin/prompts` CRUD | Admin can edit system prompts without redeploy |

---

## Architecture

### Files to Create
```
backend/
├── ai/
│   ├── __init__.py
│   ├── client.py           # OpenAI client wrapper
│   ├── embeddings.py       # embedding generation
│   ├── prompts.py          # prompt loader + renderer
│   ├── token_tracker.py    # usage logging
│   └── cost_guard.py       # budget enforcement
├── models/
│   └── prompt_template.py  # ORM model
├── schemas/
│   └── ai.py
└── routes/
    └── prompts.py
```

---

## AI Client (`backend/ai/client.py`)

```python
import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from backend.core.config import settings
from backend.core.logging import logger

class AIClient:
    def __init__(self):
        self._client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=30.0,
            max_retries=0,   # we manage retries via tenacity
        )

    @retry(
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        stream: bool = False,
    ):
        model = model or settings.OPENAI_CHAT_MODEL
        logger.info("llm_call", model=model, message_count=len(messages))
        return await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
        )

    @retry(
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            input=text,
            model=settings.OPENAI_EMBEDDING_MODEL,
        )
        return response.data[0].embedding

ai_client = AIClient()   # singleton
```

---

## Prompt Management System

### Database Table
```sql
CREATE TABLE prompt_templates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID REFERENCES organizations(id) ON DELETE CASCADE,  -- NULL = global default
    name        VARCHAR(100) NOT NULL,                -- e.g. "faq_assistant", "lead_qualifier"
    version     INTEGER NOT NULL DEFAULT 1,
    content     TEXT NOT NULL,                        -- Jinja2 template
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    variables   JSONB NOT NULL DEFAULT '[]',          -- [{name, required, description}]
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_id, name, version)
);
```

### Default System Prompts (seeded)

**`faq_assistant`**
```
You are a professional customer support assistant for {{ business_name }}.
Answer questions using only the provided context documents.
If the answer is not in the context, say: "I don't have that information — would you like me to connect you with a team member?"
Always be concise, professional, and helpful.
Cite your sources when relevant (e.g., "According to our pricing page...").
```

**`lead_qualifier`**
```
You are a friendly sales assistant for {{ business_name }}.
Your goal is to understand the customer's needs and qualify them as a potential lead.
Collect: name, email, phone (optional), budget range, urgency, service interest.
Ask ONE question at a time. Do not overwhelm the customer.
Once you have all key information, respond with: [LEAD_CAPTURED]
```

### Prompt Renderer (`backend/ai/prompts.py`)
```python
from jinja2 import Environment, BaseLoader
from sqlalchemy.ext.asyncio import AsyncSession
from backend.repositories.prompt_repo import get_active_prompt

jinja = Environment(loader=BaseLoader(), autoescape=False)

async def render_prompt(
    name: str,
    variables: dict,
    org_id: str,
    db: AsyncSession,
) -> str:
    template_row = await get_active_prompt(db, name=name, org_id=org_id)
    if not template_row:
        raise ValueError(f"No active prompt template: {name}")
    tmpl = jinja.from_string(template_row.content)
    return tmpl.render(**variables)
```

---

## Token Tracking (`backend/ai/token_tracker.py`)

```python
from backend.database.session import AsyncSessionFactory
from backend.models.token_usage import TokenUsage
from datetime import datetime, timezone

async def record_usage(
    org_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    conversation_id: str | None = None,
) -> None:
    async with AsyncSessionFactory() as db:
        record = TokenUsage(
            org_id=org_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            conversation_id=conversation_id,
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(record)
        await db.commit()
```

### Token Usage Table
```sql
CREATE TABLE token_usage (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    conversation_id     UUID REFERENCES conversations(id),
    model               VARCHAR(50) NOT NULL,
    prompt_tokens       INTEGER NOT NULL,
    completion_tokens   INTEGER NOT NULL,
    total_tokens        INTEGER NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_token_usage_org_month ON token_usage(org_id, recorded_at);
```

---

## Cost Guard (`backend/ai/cost_guard.py`)

```python
from fastapi import HTTPException
from sqlalchemy import func, select
from backend.models.token_usage import TokenUsage
from backend.core.config import settings

PLAN_MONTHLY_TOKEN_LIMITS = {
    "free": 100_000,
    "starter": 1_000_000,
    "pro": 10_000_000,
    "enterprise": None,   # unlimited
}

async def check_token_budget(org_id: str, org_plan: str, db) -> None:
    limit = PLAN_MONTHLY_TOKEN_LIMITS.get(org_plan)
    if limit is None:
        return
    result = await db.execute(
        select(func.sum(TokenUsage.total_tokens)).where(
            TokenUsage.org_id == org_id,
            func.date_trunc("month", TokenUsage.recorded_at) == func.date_trunc("month", func.now()),
        )
    )
    used = result.scalar() or 0
    if used >= limit:
        raise HTTPException(status_code=429, detail="Monthly AI token limit reached. Upgrade your plan.")
```

---

## Streaming SSE Endpoint

```python
# backend/routes/chat.py (preview — full in Phase 6)
from fastapi.responses import StreamingResponse
import json

async def stream_chat(request: ChatRequest, current_user=Depends(get_current_user)):
    async def event_generator():
        stream = await ai_client.chat_completion(messages=[...], stream=True)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'text': delta})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## Model Selection Strategy

| Use Case | Model | Rationale |
|---|---|---|
| FAQ answers | `gpt-4o` | Best reasoning, citation accuracy |
| Lead qualification | `gpt-4o-mini` | Lower cost, sufficient for structured Q&A |
| Embeddings | `text-embedding-3-small` | Best cost/quality ratio for RAG |
| Fallback (cost saving) | `gpt-4o-mini` | Swap when org budget is at 80% |

Config-driven — model names come from `settings`, never hardcoded in business logic.

---

## Hallucination Prevention

1. **Temperature**: set to `0.3` for FAQ, `0.1` for lead extraction.
2. **System prompt constraint**: "Answer ONLY from provided context."
3. **Confidence score**: if top retrieved chunk similarity < 0.75, return fallback.
4. **Response validation**: parse LLM output with Pydantic before returning to user — if parsing fails, return safe fallback.
5. **Citation enforcement**: prompt instructs model to cite source; UI displays source chips.

---

## Admin Prompt Management API

```
GET    /api/v1/admin/prompts              — list all templates for org
GET    /api/v1/admin/prompts/{name}       — get active version
POST   /api/v1/admin/prompts             — create new template
PUT    /api/v1/admin/prompts/{id}        — update (creates new version, deactivates old)
DELETE /api/v1/admin/prompts/{id}        — soft delete
POST   /api/v1/admin/prompts/{id}/test   — test render with sample variables
```

---

## Validation Checklist

- [ ] `AIClient` retries on `RateLimitError` and succeeds on 3rd attempt in tests
- [ ] Token usage is recorded for every LLM call
- [ ] Org on `free` plan blocked after 100K tokens/month
- [ ] Prompt template renders correctly with Jinja2 variables
- [ ] Admin can update system prompt and next chat uses new version without restart
- [ ] Streaming endpoint returns SSE chunks in browser (tested with `curl -N`)
- [ ] `OPENAI_API_KEY` not present → startup fails with clear error

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| OpenAI outage | Retry with exponential backoff; surface degraded mode to user |
| Runaway token costs | Cost guard + Slack alert at 80% of monthly budget |
| Prompt injection via user input | Sanitize user messages; never interpolate raw user text into system prompt |
| Model deprecation | Model name in config, not hardcoded; upgrade in one place |

## Rollback Strategy
AI layer is stateless — no data to rollback. Disable AI endpoints by feature flag in `settings.FEATURES_AI_ENABLED = False`. Cost guard prevents financial damage during incidents.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-4-ai-integration
```

### Commit Checkpoints

```bash
# After AIClient with retry logic
git add backend/ai/client.py
git commit -m "feat(ai): add OpenAI async client with tenacity retry and timeout"

# After embedding service
git add backend/ai/embeddings.py
git commit -m "feat(ai): add embedding generation service"

# After prompt_templates table + migration + PromptManager
git add backend/alembic/versions/007_create_prompt_templates.py backend/ai/prompts.py backend/models/prompt_template.py
git commit -m "feat(ai): add prompt_templates table, migration, and Jinja2 PromptManager"

# After token_usage table + tracker
git add backend/alembic/versions/008_create_token_usage.py backend/ai/token_tracker.py backend/models/token_usage.py
git commit -m "feat(ai): add token_usage table and usage recording service"

# After cost guard
git add backend/ai/cost_guard.py
git commit -m "feat(ai): add monthly token budget enforcement per org plan"

# After admin prompt CRUD endpoints
git add backend/routes/prompts.py
git commit -m "feat(ai): add admin CRUD endpoints for prompt template management"

# After seeding default prompt templates
git add scripts/seed_prompts.py
git commit -m "chore(ai): seed default faq_assistant and lead_qualifier prompt templates"
```

### Merge to Develop
```bash
git push -u origin feature/phase-4-ai-integration

gh pr create \
  --title "feat: Phase 4 — AI Integration Layer" \
  --body "OpenAI client, prompt manager, token tracking, cost guard, admin prompt CRUD. All checklist items pass." \
  --base develop
```

---

## Definition of Done

Phase 4 is **complete** when every item below is checked.

### Code Quality
- [ ] `AIClient` is a singleton — not instantiated per-request
- [ ] Model names come from `settings` — no hardcoded `"gpt-4o"` strings in business logic
- [ ] All OpenAI calls go through `AIClient` — no direct `openai.*` calls elsewhere
- [ ] Prompt templates use Jinja2 — no f-string interpolation with user input
- [ ] Token usage recorded for every LLM call, without exception

### Functionality
- [ ] `AIClient` retries on `RateLimitError` (verified via test with mock that fails twice)
- [ ] Org on `free` plan blocked at 100K tokens/month with clear `429` message
- [ ] Prompt template renders correctly with all required Jinja2 variables
- [ ] Admin can edit a prompt via API and next render uses new version
- [ ] Startup fails with `ValidationError` when `OPENAI_API_KEY` is not set

### Security
- [ ] User-supplied text never interpolated into system prompt (only into `role: user` message)
- [ ] API key only accessed via `settings.OPENAI_API_KEY` — never hardcoded
- [ ] Token budget check runs before every LLM call, not only on first call of the day

### Testing
- [ ] `pytest backend/tests/test_ai.py -v` — all tests pass
- [ ] Mock OpenAI in tests — no real API calls during CI
- [ ] Cost guard test: verify `429` returned after mocked cumulative token threshold

### What is NOT Acceptable
- Calling `openai.chat.completions.create()` directly in a route or service
- User message content injected into the system prompt string
- Missing token tracking on any code path that calls the LLM
- Hard-coded temperature or model names outside of `settings` or `AIClient`
