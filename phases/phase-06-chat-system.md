# Phase 6 — Chat System

## Objectives
Build the full conversational engine: conversation management, message persistence, RAG-augmented LLM responses, streaming, conversation memory, the embeddable frontend chat widget, and the lead extraction trigger that hands off to Phase 7.

## Dependencies
- Phase 2 (auth)
- Phase 3 (conversations, messages tables)
- Phase 4 (AI client, prompt manager, token tracker)
- Phase 5 (RAG retrieval service)

## Estimated Duration
4–5 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | `POST /chat/message` — stateful chat endpoint | Response uses RAG context + conversation history |
| 2 | `POST /chat/stream` — SSE streaming | Frontend renders tokens as they arrive |
| 3 | Conversation memory (sliding window) | Last 10 turns injected into LLM context |
| 4 | Citation metadata in response | `sources: [{filename, chunk_index, score}]` |
| 5 | Lead extraction trigger | Detects `[LEAD_CAPTURED]` signal in LLM output |
| 6 | Fallback response on low confidence | Returns canned message when RAG has no context |
| 7 | Chat widget (Next.js component) | Embeddable on any page via `<ChatWidget orgId="..." />` |
| 8 | Conversation history page in dashboard | Admin views full chat transcripts |

---

## Overall Request Lifecycle

```
POST /api/v1/chat/message
{
  "conversation_id": "uuid or null",
  "message": "What are your pricing plans?",
  "channel": "web",
  "visitor_id": "anon-abc123"
}

1. Resolve conversation
   └─ If no conversation_id: create new conversation record
   └─ If conversation_id: load + validate belongs to org

2. Save user message to DB

3. Load conversation history (last 10 messages)

4. RAG Retrieval
   └─ embed query
   └─ search org's ChromaDB collection
   └─ filter by score ≥ 0.75
   └─ if empty → use fallback response

5. Render system prompt (from PromptManager)
   └─ inject business_name, context_block

6. Build LLM messages array
   [system_prompt, ...history, user_message]

7. Call OpenAI (gpt-4o)

8. Parse response
   └─ extract [LEAD_CAPTURED] signal
   └─ extract citations from response text

9. Save assistant message + sources to DB

10. Record token usage

11. If [LEAD_CAPTURED] → trigger LeadExtractionService (async)

12. Return response to client
{
  "message": "Our pricing starts at $99/month...",
  "sources": [{"filename": "pricing.pdf", "score": 0.92}],
  "conversation_id": "uuid",
  "lead_captured": false
}
```

---

## Architecture

### Files to Create
```
backend/
├── services/
│   ├── chat_service.py         # orchestrates full chat flow
│   ├── conversation_service.py # create/get/close conversations
│   └── lead_extraction.py      # parses lead data from conversation
├── routes/
│   └── chat.py
└── schemas/
    └── chat.py
```

---

## Chat Service (`backend/services/chat_service.py`)

```python
from backend.ai.client import ai_client
from backend.ai.prompts import render_prompt
from backend.ai.token_tracker import record_usage
from backend.rag.retriever import RetrievalService
from backend.repositories.conversation_repo import (
    get_or_create_conversation, save_message, get_recent_messages
)
from backend.services.lead_extraction import LeadExtractionService

FALLBACK_RESPONSE = (
    "I don't have enough information to answer that right now. "
    "Would you like me to connect you with a team member?"
)
HISTORY_WINDOW = 10  # turns (user + assistant pairs)

class ChatService:
    def __init__(self, retriever: RetrievalService, lead_extractor: LeadExtractionService):
        self.retriever = retriever
        self.lead_extractor = lead_extractor

    async def handle_message(
        self,
        org_id: str,
        conversation_id: str | None,
        user_message: str,
        channel: str,
        visitor_id: str,
        db,
        business_name: str,
    ) -> dict:
        # 1. Conversation
        conversation = await get_or_create_conversation(
            db, org_id=org_id, conversation_id=conversation_id,
            channel=channel, visitor_id=visitor_id,
        )
        await save_message(db, conversation.id, org_id, role="user", content=user_message)

        # 2. History
        history = await get_recent_messages(db, conversation.id, limit=HISTORY_WINDOW * 2)
        history_msgs = [{"role": m.role, "content": m.content} for m in history]

        # 3. RAG
        results = await self.retriever.retrieve(user_message, org_id)
        context_block = self.retriever.build_context_block(results)

        if not results:
            await save_message(db, conversation.id, org_id, role="assistant", content=FALLBACK_RESPONSE)
            return {
                "message": FALLBACK_RESPONSE,
                "sources": [],
                "conversation_id": str(conversation.id),
                "lead_captured": False,
            }

        # 4. Prompt
        system_prompt = await render_prompt(
            name="faq_assistant",
            variables={"business_name": business_name, "context": context_block},
            org_id=org_id, db=db,
        )

        # 5. LLM call
        messages = [
            {"role": "system", "content": system_prompt},
            *history_msgs,
            {"role": "user", "content": user_message},
        ]
        response = await ai_client.chat_completion(messages=messages, temperature=0.3)
        assistant_text = response.choices[0].message.content
        usage = response.usage

        # 6. Persist + track
        sources = [{"filename": r.metadata["filename"], "score": r.score} for r in results]
        await save_message(db, conversation.id, org_id, role="assistant",
                           content=assistant_text, sources=sources,
                           tokens_used=usage.total_tokens)
        await record_usage(org_id, response.model, usage.prompt_tokens, usage.completion_tokens,
                           conversation_id=str(conversation.id))

        # 7. Lead signal
        lead_captured = False
        if "[LEAD_CAPTURED]" in assistant_text:
            assistant_text = assistant_text.replace("[LEAD_CAPTURED]", "").strip()
            await self.lead_extractor.extract_and_save(db, conversation.id, org_id, history_msgs)
            lead_captured = True

        return {
            "message": assistant_text,
            "sources": sources,
            "conversation_id": str(conversation.id),
            "lead_captured": lead_captured,
        }
```

---

## Lead Extraction Service (`backend/services/lead_extraction.py`)

```python
import json
from backend.ai.client import ai_client

EXTRACTION_PROMPT = """
From the conversation below, extract the lead details as JSON.
Fields: name, email, phone, budget, urgency, service_interest.
Use null for any field not mentioned. Return ONLY valid JSON.

Conversation:
{conversation}
"""

class LeadExtractionService:
    async def extract_and_save(self, db, conversation_id: str, org_id: str, history: list[dict]) -> None:
        conversation_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in history
        )
        prompt = EXTRACTION_PROMPT.format(conversation=conversation_text)
        response = await ai_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=300,
        )
        try:
            raw = response.choices[0].message.content
            # strip markdown code fences if present
            raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
            data = json.loads(raw)
        except (json.JSONDecodeError, KeyError):
            return   # extraction failed silently — lead not created

        from backend.repositories.lead_repo import LeadRepository
        repo = LeadRepository(db)
        await repo.create({
            "org_id": org_id,
            "conversation_id": conversation_id,
            "name": data.get("name"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "budget": data.get("budget"),
            "urgency": data.get("urgency"),
            "service_interest": data.get("service_interest"),
        })
```

---

## Conversation Memory Design

The LLM receives a **sliding window** of the last 10 turns (20 messages: 10 user + 10 assistant). This is pre-trimmed before calling the API to stay within the 128K token limit.

```
System Prompt     ~ 500 tokens
Context Block     ~ 2,500 tokens (5 chunks × 512 tokens)
History (10 turns)~ 2,000 tokens
User message      ~ 100 tokens
--------------------------
Total input       ~ 5,100 tokens (well within limits)
```

For very long conversations, older messages are archived (still in DB) but excluded from LLM context.

---

## Streaming Endpoint

```python
# backend/routes/chat.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

router = APIRouter(prefix="/chat")

@router.post("/stream")
async def stream_chat(request: ChatRequest, ...):
    async def generate():
        messages = await chat_service.build_messages(...)   # same as above, no final LLM call yet
        stream = await ai_client.chat_completion(messages=messages, stream=True)
        full_text = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            full_text += delta
            yield f"data: {json.dumps({'text': delta})}\n\n"

        # After stream completes, persist the full response
        await chat_service.post_stream_persist(full_text, ...)
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

---

## Frontend Chat Widget

### Component Structure
```
frontend/components/chat-widget/
├── ChatWidget.tsx        # root — handles open/close state
├── ChatWindow.tsx        # message list + input
├── Message.tsx           # renders user/assistant message bubble
├── SourceChips.tsx       # displays cited document sources
├── TypingIndicator.tsx   # animated "..." when streaming
└── useChat.ts            # hook: manages messages, calls API, handles SSE
```

### `useChat.ts`
```typescript
export function useChat(orgId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function sendMessage(text: string) {
    setIsLoading(true);
    setMessages(prev => [...prev, { role: "user", content: text }]);

    const response = await fetch(`/api/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, conversation_id: conversationId, org_id: orgId, channel: "web" }),
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let assistantText = "";

    setMessages(prev => [...prev, { role: "assistant", content: "" }]);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = decoder.decode(value).split("\n");
      for (const line of lines) {
        if (line.startsWith("data: ") && line !== "data: [DONE]") {
          const { text } = JSON.parse(line.slice(6));
          assistantText += text;
          setMessages(prev => [
            ...prev.slice(0, -1),
            { role: "assistant", content: assistantText },
          ]);
        }
      }
    }
    setIsLoading(false);
  }

  return { messages, sendMessage, isLoading, conversationId };
}
```

### Widget Embedding
The widget is a self-contained component. For external website embedding, a `<script>` tag approach is planned for Phase 10 (Integrations).

---

## API Endpoints

```
POST   /api/v1/chat/message              — synchronous response
POST   /api/v1/chat/stream               — SSE streaming response
GET    /api/v1/chat/conversations        — list org conversations
GET    /api/v1/chat/conversations/{id}   — get conversation with messages
PATCH  /api/v1/chat/conversations/{id}   — update status (close, handoff)
```

### Request/Response Schema
```python
class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    channel: str = "web"
    visitor_id: str | None = None

class ChatResponse(BaseModel):
    message: str
    sources: list[dict]
    conversation_id: str
    lead_captured: bool
```

---

## Validation Checklist

- [ ] FAQ question with matching document returns answer with citation
- [ ] Question with no matching context returns fallback (no hallucination)
- [ ] Conversation history preserved across 10+ turns (correct context window)
- [ ] `[LEAD_CAPTURED]` signal creates lead in DB and is stripped from response
- [ ] Streaming endpoint sends incremental tokens visible in browser DevTools
- [ ] Two orgs can chat simultaneously — no cross-tenant context leak
- [ ] Rate limit: 60 messages/minute per visitor (returns `429`)
- [ ] Chat widget opens/closes without page reload
- [ ] Source chips display correct filename for cited document

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM outputs `[LEAD_CAPTURED]` without real lead data | Lead extraction validates extracted JSON; skips if fields all null |
| Context window overflow on long conversations | Sliding window caps at 10 turns; archive older messages |
| Streaming connection drops mid-response | Client reconnects via SSE retry mechanism; partial message preserved in UI |
| Prompt injection via user message | User content in `role: user` slot only; never interpolated into system prompt |

## Rollback Strategy
Conversations and messages are append-only. Disable chat endpoints via feature flag. Re-enable after fix. No destructive rollback needed.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-6-chat-system
```

### Commit Checkpoints

```bash
# After conversation service (create/get/close)
git add backend/services/conversation_service.py backend/repositories/conversation_repo.py
git commit -m "feat(chat): add conversation lifecycle management service"

# After ChatService core (RAG + LLM + persist)
git add backend/services/chat_service.py
git commit -m "feat(chat): add ChatService orchestrating RAG retrieval and LLM response"

# After lead extraction service
git add backend/services/lead_extraction.py
git commit -m "feat(chat): add LeadExtractionService triggered by LEAD_CAPTURED signal"

# After synchronous chat endpoint
git add backend/routes/chat.py backend/schemas/chat.py
git commit -m "feat(chat): add POST /chat/message endpoint with RAG-augmented responses"

# After streaming SSE endpoint
git commit -m "feat(chat): add POST /chat/stream SSE endpoint for real-time token delivery"

# After fallback response logic
git commit -m "feat(chat): add low-confidence fallback when RAG returns no results"

# After frontend chat widget
git add frontend/components/chat-widget/
git commit -m "feat(chat): add embeddable ChatWidget component with streaming support"

# After conversation history page
git add frontend/app/dashboard/conversations/
git commit -m "feat(chat): add conversation history browser in admin dashboard"
```

### End-to-End Test Before Merging
```bash
# 1. Send a message that matches a document
# 2. Verify response includes citation
# 3. Send a message with no matching context — verify fallback
# 4. Send lead-qualifying messages — verify lead created in DB
# 5. Test streaming endpoint with curl
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What are your pricing plans?", "channel": "web"}'
```

### Merge to Develop
```bash
git push -u origin feature/phase-6-chat-system

gh pr create \
  --title "feat: Phase 6 — Chat System" \
  --body "RAG-augmented chat, conversation memory, streaming SSE, lead extraction trigger, chat widget. End-to-end flow tested." \
  --base develop
```

---

## Definition of Done

Phase 6 is **complete** when every item below is checked.

### Code Quality
- [ ] No LLM call logic in route handlers — all in `ChatService`
- [ ] `[LEAD_CAPTURED]` signal stripped from response before returning to user
- [ ] Fallback response is a constant — not an LLM-generated string (no token cost)
- [ ] System prompt never contains raw user message content
- [ ] Token usage recorded on every successful LLM call

### Functionality
- [ ] FAQ question answered with correct citation (`sources` field populated)
- [ ] Question with no RAG context returns fallback message (no LLM called)
- [ ] Conversation history (last 10 turns) correctly injected into LLM messages
- [ ] Lead created in DB when `[LEAD_CAPTURED]` detected in LLM output
- [ ] Two orgs chatting simultaneously do not share context or RAG results
- [ ] Streaming endpoint delivers tokens incrementally (verified in browser DevTools)
- [ ] Rate limit: 61st message/minute from same visitor returns `429`

### Performance
- [ ] Non-streaming response time p95 < 3s (with RAG retrieval included)
- [ ] Streaming first-token latency < 1s

### Testing
- [ ] `pytest backend/tests/test_chat.py -v` — all tests pass
- [ ] Mock OpenAI in tests — no real API calls during CI
- [ ] Test explicitly covers: FAQ hit, FAQ miss (fallback), lead extraction trigger
- [ ] Test coverage for `services/chat_service.py` ≥ 80%

### What is NOT Acceptable
- LLM called when RAG returns no results (costs tokens, risks hallucination)
- `[LEAD_CAPTURED]` signal visible in the response returned to the chat user
- Conversation history not preserved between requests to the same `conversation_id`
- No test for cross-tenant isolation in chat responses
