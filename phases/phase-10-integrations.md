# Phase 10 — Multi-Channel Integrations

## Objectives
Connect the chat engine to external messaging platforms: WhatsApp, Telegram, and Instagram DM. Each channel forwards messages into the same unified chat processing pipeline (Phase 6) and delivers AI responses back through the originating channel.

## Dependencies
- Phase 6 (chat pipeline — `ChatService.handle_message()`)
- Phase 2 (auth — org identified by API key, not JWT)
- Phase 3 (conversations table, channel field)

## Estimated Duration
4–5 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | Unified `ChannelAdapter` abstraction | New channels added without touching chat service |
| 2 | WhatsApp webhook (`POST /webhooks/whatsapp`) | Messages from WhatsApp processed and replied to |
| 3 | Telegram webhook (`POST /webhooks/telegram`) | Messages from Telegram processed and replied to |
| 4 | Instagram DM webhook (`POST /webhooks/instagram`) | Architecture ready; handler stubbed |
| 5 | Website embed script | `<script src="/widget.js">` embeds chat widget on any site |
| 6 | Webhook secret validation | All incoming webhooks verified via HMAC signature |
| 7 | Channel status in admin settings | Admin sees which channels are connected |

---

## Channel Architecture

### Unified Message Format

All channels normalize their payloads into a single internal format before passing to `ChatService`:

```python
from dataclasses import dataclass

@dataclass
class IncomingMessage:
    channel: str              # "whatsapp" | "telegram" | "instagram" | "web"
    external_conversation_id: str   # channel-specific thread/chat ID
    visitor_id: str           # phone number, telegram user ID, etc.
    text: str
    org_id: str
    metadata: dict = None     # channel-specific extras
```

### Channel Adapter Interface
```python
# backend/integrations/base_channel.py
from abc import ABC, abstractmethod

class ChannelAdapter(ABC):
    @abstractmethod
    async def parse_webhook(self, payload: dict, headers: dict) -> IncomingMessage | None:
        """Parse raw webhook payload → IncomingMessage. Return None to skip."""
        ...

    @abstractmethod
    async def send_message(self, conversation_id: str, text: str, metadata: dict) -> None:
        """Deliver message back through this channel."""
        ...

    @abstractmethod
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Validate webhook origin."""
        ...
```

### Channel Registry
```python
# backend/integrations/registry.py
from backend.integrations.whatsapp import WhatsAppAdapter
from backend.integrations.telegram import TelegramAdapter
from backend.integrations.instagram import InstagramAdapter

CHANNEL_ADAPTERS: dict[str, type[ChannelAdapter]] = {
    "whatsapp": WhatsAppAdapter,
    "telegram": TelegramAdapter,
    "instagram": InstagramAdapter,
}
```

---

## Webhook Processing Flow

```
External platform sends POST to /api/v1/webhooks/{channel}
         │
         ▼
1. Look up org by webhook token (X-Org-Token header or URL param)
2. Adapter.verify_signature(payload, signature_header)
   └─ 403 if invalid
3. Adapter.parse_webhook(payload) → IncomingMessage
   └─ Return 200 immediately (platforms retry on slow responses)
4. Enqueue message for background processing
5. Background worker: ChatService.handle_message(incoming_message)
6. Adapter.send_message(reply_text)
```

**Critical**: Webhook endpoints MUST return `200 OK` within 5 seconds or the platform retries. AI processing happens in a background task.

```python
# backend/routes/webhooks.py
@router.post("/{channel}")
async def webhook(
    channel: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    org = await get_org_by_webhook_token(request)
    adapter = CHANNEL_ADAPTERS[channel]()

    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not adapter.verify_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    incoming = await adapter.parse_webhook(payload, dict(request.headers))

    if incoming:
        background_tasks.add_task(process_channel_message, incoming, org.id)

    return {"status": "ok"}   # Always 200 immediately
```

---

## WhatsApp Integration (Meta Cloud API)

### Webhook Verification (GET request from Meta)
```python
@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403)
```

### WhatsApp Adapter
```python
import hashlib, hmac

class WhatsAppAdapter(ChannelAdapter):
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        expected = "sha256=" + hmac.new(
            settings.WHATSAPP_APP_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def parse_webhook(self, payload: dict, headers: dict) -> IncomingMessage | None:
        try:
            entry = payload["entry"][0]["changes"][0]["value"]
            if "messages" not in entry:
                return None
            msg = entry["messages"][0]
            if msg["type"] != "text":
                return None
            phone = msg["from"]
            text = msg["text"]["body"]
            waid = entry["metadata"]["phone_number_id"]
            return IncomingMessage(
                channel="whatsapp",
                external_conversation_id=phone,
                visitor_id=phone,
                text=text,
                org_id="",   # filled by webhook route from org lookup
                metadata={"phone_number_id": waid},
            )
        except (KeyError, IndexError):
            return None

    async def send_message(self, conversation_id: str, text: str, metadata: dict) -> None:
        phone_number_id = metadata["phone_number_id"]
        to = conversation_id
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": text},
                },
            )
```

---

## Telegram Integration

### Webhook Registration
```bash
# Set webhook (run once per deployment)
curl https://api.telegram.org/bot{TOKEN}/setWebhook \
  -d url=https://api.yourdomain.com/api/v1/webhooks/telegram \
  -d secret_token={TELEGRAM_WEBHOOK_SECRET}
```

### Telegram Adapter
```python
class TelegramAdapter(ChannelAdapter):
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        # Telegram sends X-Telegram-Bot-Api-Secret-Token header
        return signature == settings.TELEGRAM_WEBHOOK_SECRET

    async def parse_webhook(self, payload: dict, headers: dict) -> IncomingMessage | None:
        message = payload.get("message")
        if not message or "text" not in message:
            return None
        return IncomingMessage(
            channel="telegram",
            external_conversation_id=str(message["chat"]["id"]),
            visitor_id=str(message["from"]["id"]),
            text=message["text"],
            org_id="",
            metadata={"chat_id": message["chat"]["id"]},
        )

    async def send_message(self, conversation_id: str, text: str, metadata: dict) -> None:
        chat_id = metadata["chat_id"]
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
```

---

## Instagram DM (Architecture Only for MVP)

Instagram DM uses the same Meta Webhooks infrastructure as WhatsApp. The adapter is stubbed:

```python
class InstagramAdapter(ChannelAdapter):
    async def parse_webhook(self, payload: dict, headers: dict) -> IncomingMessage | None:
        # TODO Phase 10.5: implement Instagram message parsing
        # Instagram uses same Graph API webhook format as WhatsApp
        # Requires Instagram Business Account + Facebook App
        return None

    async def send_message(self, conversation_id: str, text: str, metadata: dict) -> None:
        # TODO Phase 10.5
        pass
```

---

## Website Embed Script

### How It Works
A Next.js API route serves a small JavaScript snippet. When included on any website, it renders the chat widget as a floating button.

```javascript
// public/widget.js (served from Next.js)
(function() {
  const orgId = document.currentScript.getAttribute("data-org-id");
  const iframe = document.createElement("iframe");
  iframe.src = `https://app.yourdomain.com/embed/chat?org=${orgId}`;
  iframe.style.cssText = "position:fixed;bottom:20px;right:20px;width:380px;height:600px;border:none;z-index:9999;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.2)";
  document.body.appendChild(iframe);
})();
```

Customer adds to their site:
```html
<script src="https://app.yourdomain.com/widget.js" data-org-id="your-org-id"></script>
```

### Embed Route
```
frontend/app/embed/chat/page.tsx   — standalone chat widget (no nav, minimal UI)
```

Security: embed page is served from the same domain, so no CORS issues. CSP header restricts the iframe to trusted origins.

---

## Org Webhook Token

Each org has a unique `webhook_token` (UUID). It's included in the webhook URL:
```
POST /api/v1/webhooks/whatsapp?org_token={token}
```
This maps the inbound webhook to the correct org without requiring JWT auth on a public endpoint.

```sql
ALTER TABLE organizations ADD COLUMN webhook_token UUID DEFAULT gen_random_uuid() UNIQUE;
```

---

## Admin Settings: Channel Connection UI

```
frontend/app/dashboard/settings/integrations/page.tsx
```

| Channel | Status | Action |
|---|---|---|
| Website Widget | ✅ Active | Copy embed code |
| WhatsApp | ❌ Not connected | Connect (shows setup guide) |
| Telegram | ✅ Active | Disconnect |
| Instagram | 🔶 Coming Soon | — |

---

## Validation Checklist

- [ ] WhatsApp webhook verification GET request returns challenge
- [ ] Sending a message via WhatsApp triggers AI response (end-to-end)
- [ ] Invalid HMAC signature on WhatsApp webhook returns `403`
- [ ] Telegram bot responds within 5 seconds of user message
- [ ] Two orgs receive separate responses to same incoming text (no cross-talk)
- [ ] Website embed script renders floating widget on a plain HTML page
- [ ] Webhook endpoint returns `200` within 500ms (processing is in background)
- [ ] WhatsApp message longer than 4096 chars split into multiple messages

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Meta Webhooks retries on slow response | Background task + immediate 200 response |
| WhatsApp business approval delay | Test via WhatsApp sandbox during development |
| Telegram bot token compromised | Store as encrypted secret; rotate via BotFather |
| Embed widget causes CSP violations on customer site | Document required CSP changes; provide `frame-src` directive |

## Rollback Strategy
Channels are additive. Disconnect integration via admin settings to stop receiving webhooks. No data loss — past conversations preserved in DB. Redeploy without channel adapter to fully disable.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-10-integrations
```

### Commit Checkpoints

```bash
# After ChannelAdapter ABC + IncomingMessage dataclass + registry
git add backend/integrations/base_channel.py backend/integrations/registry.py
git commit -m "feat(channels): add ChannelAdapter interface and channel registry"

# After unified webhook route (org lookup + signature verify + background dispatch)
git add backend/routes/webhooks.py
git commit -m "feat(channels): add unified webhook route with HMAC verification and background processing"

# After webhook_token column migration
git add backend/alembic/versions/009_add_webhook_token.py
git commit -m "feat(channels): migration — add webhook_token column to organizations"

# After WhatsApp adapter
git add backend/integrations/whatsapp.py
git commit -m "feat(channels): add WhatsApp adapter with Meta Cloud API signature verification"

# After Telegram adapter
git add backend/integrations/telegram.py
git commit -m "feat(channels): add Telegram adapter with bot webhook support"

# After Instagram stub
git add backend/integrations/instagram.py
git commit -m "feat(channels): add Instagram adapter stub (architecture ready, handler pending)"

# After website embed script
git add frontend/public/widget.js frontend/app/embed/
git commit -m "feat(channels): add embeddable website chat widget script"

# After channel status in admin settings UI
git add frontend/app/dashboard/settings/integrations/
git commit -m "feat(channels): add channel connection status in admin settings"
```

### Manual Test Before Merging
```bash
# Test WhatsApp webhook verification
curl -X GET "http://localhost:8000/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=$WHATSAPP_VERIFY_TOKEN&hub.challenge=test123"
# Expected: "test123"

# Test with invalid signature — must return 403
curl -X POST http://localhost:8000/api/v1/webhooks/whatsapp \
  -H "X-Hub-Signature-256: sha256=invalidsig" \
  -d '{"entry":[]}'
# Expected: 403

# Test website embed
# Add <script src="http://localhost:3000/widget.js" data-org-id="test-org"> to a plain HTML file
# Open in browser — floating chat button should appear
```

### Merge to Develop
```bash
git push -u origin feature/phase-10-integrations

gh pr create \
  --title "feat: Phase 10 — Multi-Channel Integrations" \
  --body "Unified ChannelAdapter pattern, WhatsApp + Telegram webhooks, website embed script. HMAC signature verified on all channels." \
  --base develop
```

---

## Definition of Done

Phase 10 is **complete** when every item below is checked.

### Code Quality
- [ ] Webhook route returns `200` immediately — AI processing in `BackgroundTasks`, never blocking
- [ ] All channel adapters implement the `ChannelAdapter` ABC — no duck typing
- [ ] Adding a new channel requires only: new adapter class + one line in `CHANNEL_ADAPTERS` registry
- [ ] Webhook token for org lookup is in URL param or header — never in JWT (public endpoint)

### Functionality
- [ ] WhatsApp webhook GET verification returns challenge correctly
- [ ] WhatsApp message end-to-end: send text → AI processes → reply delivered to WhatsApp
- [ ] Invalid HMAC signature on WhatsApp webhook returns `403`
- [ ] Telegram bot responds to message within 5 seconds
- [ ] Two orgs receive separate AI responses with their own knowledge bases
- [ ] Website embed script renders floating widget on a plain HTML page (no React required)
- [ ] Webhook endpoint returns `200` within 500ms (measured via curl timing)

### Security
- [ ] HMAC signature verified before any message processing on all channels
- [ ] Webhook token is org-specific UUID — not a shared secret
- [ ] `WHATSAPP_APP_SECRET` and `TELEGRAM_WEBHOOK_SECRET` only in `settings` — never in code

### Testing
- [ ] `pytest backend/tests/test_webhooks.py -v` — all tests pass
- [ ] Tests cover: valid message, invalid signature, unsupported message type (non-text)
- [ ] Cross-tenant test: two orgs with separate bots receive separate replies

### What is NOT Acceptable
- Webhook endpoint that takes > 1s to return 200 (platform will retry)
- Processing AI response synchronously in the webhook handler
- Missing HMAC verification (any channel)
- Hardcoded channel names outside the registry
