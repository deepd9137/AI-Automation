# Phase 12 — SaaS Readiness

## Objectives
Transform the single-tenant MVP into a fully multi-tenant SaaS product: Stripe billing, subscription plan enforcement, org onboarding flow, public marketing/pricing page, and the operational systems needed to acquire, retain, and bill customers autonomously.

## Dependencies
- Phases 1–11 complete and hardened

## Estimated Duration
5–7 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | Stripe integration | Plans created in Stripe, checkout flow works |
| 2 | Subscription enforcement middleware | Features gated by org's active plan |
| 3 | Billing dashboard for admins | Shows current plan, usage, upgrade/downgrade |
| 4 | Org self-signup flow | Anyone can register, get free plan, upgrade |
| 5 | Usage limits enforced | Token quotas, doc limits, user seat limits |
| 6 | Stripe webhook handler | Subscription changes reflected in DB in real-time |
| 7 | Public pricing page | Displays plan tiers, links to signup |
| 8 | Org onboarding wizard | First-time setup: upload docs, connect channel, test chat |
| 9 | Automated welcome email | Sent 1 minute after signup |
| 10 | Admin super-dashboard | Internal view: all orgs, MRR, churn rate |

---

## Subscription Plans

| Feature | Free | Starter ($49/mo) | Pro ($149/mo) | Enterprise |
|---|---|---|---|---|
| Monthly token limit | 100K | 1M | 10M | Custom |
| Documents | 5 | 50 | Unlimited | Unlimited |
| Team seats | 1 | 3 | 10 | Custom |
| Channels | Web only | Web + 1 channel | All channels | All channels |
| Appointments | ❌ | ✅ | ✅ | ✅ |
| Analytics | Basic | Full | Full + export | Full + export |
| Support | Email | Priority email | Slack | Dedicated CSM |

---

## Stripe Integration

### Setup

1. Create products + prices in Stripe dashboard (or via Stripe CLI):
```bash
stripe products create --name="Starter" --description="Up to 1M tokens/month"
stripe prices create --product=prod_xxx --unit-amount=4900 --currency=usd --recurring[interval]=month
```

2. Store `STRIPE_PRICE_ID_STARTER`, `STRIPE_PRICE_ID_PRO` in `.env`.

### Checkout Flow

```python
# backend/routes/billing.py
import stripe
from backend.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

@router.post("/billing/checkout")
async def create_checkout(
    plan: str,
    current_user=Depends(require_role("org_admin")),
    db=Depends(get_db),
):
    price_map = {
        "starter": settings.STRIPE_PRICE_ID_STARTER,
        "pro":     settings.STRIPE_PRICE_ID_PRO,
    }
    price_id = price_map.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.FRONTEND_URL}/dashboard/billing?success=true",
        cancel_url=f"{settings.FRONTEND_URL}/dashboard/billing",
        client_reference_id=str(current_user.org_id),
        customer_email=current_user.email,
        metadata={"org_id": str(current_user.org_id)},
    )
    return {"checkout_url": session.url}
```

### Stripe Webhook Handler

```python
@router.post("/billing/webhook")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400)

    match event["type"]:
        case "checkout.session.completed":
            await handle_checkout_completed(event["data"]["object"], db)
        case "invoice.paid":
            await handle_invoice_paid(event["data"]["object"], db)
        case "customer.subscription.updated":
            await handle_subscription_updated(event["data"]["object"], db)
        case "customer.subscription.deleted":
            await handle_subscription_cancelled(event["data"]["object"], db)

    return {"received": True}

async def handle_checkout_completed(session: dict, db) -> None:
    org_id = session["metadata"]["org_id"]
    stripe_customer_id = session["customer"]
    stripe_sub_id = session["subscription"]
    # Look up plan from subscription items
    sub = stripe.Subscription.retrieve(stripe_sub_id)
    plan = get_plan_from_price_id(sub["items"]["data"][0]["price"]["id"])
    await update_org_subscription(db, org_id, plan, stripe_customer_id, stripe_sub_id)
```

---

## Plan Enforcement Middleware

```python
# backend/auth/plan_guard.py
from fastapi import HTTPException
from backend.models.billing import PLAN_LIMITS

PLAN_LIMITS = {
    "free":       {"max_documents": 5,  "max_seats": 1,  "channels": ["web"]},
    "starter":    {"max_documents": 50, "max_seats": 3,  "channels": ["web", "whatsapp"]},
    "pro":        {"max_documents": None, "max_seats": 10, "channels": ["web", "whatsapp", "telegram", "instagram"]},
    "enterprise": {"max_documents": None, "max_seats": None, "channels": ["*"]},
}

def require_plan(*plans: str):
    async def checker(current_user=Depends(get_current_user), db=Depends(get_db)):
        org_plan = await get_org_plan(db, current_user.org_id)
        if org_plan not in plans:
            raise HTTPException(
                status_code=402,
                detail=f"This feature requires a {' or '.join(plans)} plan. Please upgrade.",
            )
        return current_user
    return checker

# Usage:
@router.post("/scheduling/book")
async def book_appointment(
    current_user=Depends(require_plan("starter", "pro", "enterprise")),
    ...
):
    ...
```

---

## Usage Limit Enforcement

```python
# backend/services/limit_service.py
async def check_document_limit(org_id: str, org_plan: str, db) -> None:
    limit = PLAN_LIMITS[org_plan]["max_documents"]
    if limit is None:
        return
    count = await count_documents(db, org_id)
    if count >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Document limit ({limit}) reached. Upgrade to upload more.",
        )

async def check_seat_limit(org_id: str, org_plan: str, db) -> None:
    limit = PLAN_LIMITS[org_plan]["max_seats"]
    if limit is None:
        return
    count = await count_org_users(db, org_id)
    if count >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Team seat limit ({limit}) reached. Upgrade for more seats.",
        )
```

---

## Onboarding Wizard

### Frontend Flow
```
frontend/app/onboarding/
├── page.tsx        — redirects to step 1
├── step-1/page.tsx — upload first document
├── step-2/page.tsx — test the AI with a question
├── step-3/page.tsx — connect a channel (optional)
└── step-4/page.tsx — invite team member (optional)
```

### Onboarding State in DB
```sql
ALTER TABLE organizations ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE organizations ADD COLUMN onboarding_step INTEGER NOT NULL DEFAULT 1;
```

After `step-4`, set `onboarding_completed = true` and redirect to dashboard.

**Skip allowed** — users can skip directly to dashboard and return later via Settings → Setup Guide.

---

## Billing Dashboard UI

```
frontend/app/dashboard/billing/page.tsx
```

Sections:
1. **Current Plan** — plan name, renewal date, monthly cost
2. **Usage** — tokens used / limit (progress bar), docs used / limit, seats used / limit
3. **Upgrade/Downgrade** — plan comparison table with CTA buttons
4. **Payment Method** — Stripe customer portal link
5. **Invoice History** — list from Stripe API

```typescript
// Usage section
function UsageSection({ usage, limits }) {
  return (
    <Card>
      <CardHeader><CardTitle>Usage This Month</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <UsageBar label="AI Tokens" used={usage.tokens} limit={limits.tokens} />
        <UsageBar label="Documents" used={usage.documents} limit={limits.documents} />
        <UsageBar label="Team Seats" used={usage.seats} limit={limits.seats} />
      </CardContent>
    </Card>
  );
}

function UsageBar({ label, used, limit }) {
  const pct = limit ? (used / limit) * 100 : 0;
  const color = pct > 90 ? "destructive" : pct > 70 ? "warning" : "default";
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span>{label}</span>
        <span>{used.toLocaleString()} / {limit ? limit.toLocaleString() : "∞"}</span>
      </div>
      <Progress value={pct} className={`h-2 ${color}`} />
    </div>
  );
}
```

---

## Automated Welcome Email

Triggered by `checkout.session.completed` Stripe webhook (or on free signup):

```python
# backend/utils/email.py
async def send_welcome_email(to: str, name: str, org_name: str, plan: str) -> None:
    # Uses SendGrid or Resend
    await send_email(
        to=to,
        subject=f"Welcome to the platform, {name}!",
        template="welcome",
        variables={
            "name": name,
            "org_name": org_name,
            "plan": plan,
            "dashboard_url": f"{settings.FRONTEND_URL}/dashboard",
            "docs_url": f"{settings.FRONTEND_URL}/docs",
        },
    )
```

---

## Internal Super-Admin Dashboard

Accessible only to `super_admin` role. Shows:
- All organizations (name, plan, created_at, MRR contribution)
- Total MRR and MoM growth
- Churned orgs last 30 days
- Token usage across all orgs
- Error rate from Sentry
- System health summary

```
/api/v1/internal/orgs             — list all orgs (super_admin only)
/api/v1/internal/mrr              — MRR summary
/api/v1/internal/usage            — aggregate token usage
```

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Stripe webhook missed → plan not updated | Idempotent webhook handler + background sync job every hour |
| Free user abuses by creating multiple orgs | Rate-limit registration by email domain + IP |
| Plan downgrade causes data loss anxiety | Downgrade is soft — over-limit docs become read-only, not deleted |
| Stripe test mode left in production | Use env var `STRIPE_LIVE_MODE=true` as explicit flag; CI checks |

## Rollback Strategy
Stripe integration is additive. To rollback billing:
1. Set `BILLING_ENABLED=false` feature flag — enforces no limits.
2. Stripe webhooks return 200 without processing (safe — Stripe doesn't know).
3. No user data is lost. Plan in DB reverts to "free" via admin script if needed.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-12-saas-readiness
```

### Commit Checkpoints

```bash
# After Stripe products/prices created + billing_subscriptions table
git add backend/alembic/versions/010_create_billing_subscriptions.py
git commit -m "feat(saas): migration — add billing_subscriptions table"

# After checkout session endpoint
git add backend/routes/billing.py
git commit -m "feat(saas): add Stripe checkout session creation endpoint"

# After Stripe webhook handler (all subscription events)
git commit -m "feat(saas): add Stripe webhook handler for checkout and subscription lifecycle events"

# After plan enforcement middleware + PLAN_LIMITS config
git add backend/auth/plan_guard.py
git commit -m "feat(saas): add require_plan() dependency and plan limits enforcement"

# After usage limit checks (tokens, documents, seats)
git add backend/services/limit_service.py
git commit -m "feat(saas): add document, seat, and token limit enforcement per plan"

# After onboarding wizard UI
git add frontend/app/onboarding/
git commit -m "feat(saas): add 4-step onboarding wizard for new organizations"

# After billing dashboard UI
git add frontend/app/dashboard/billing/
git commit -m "feat(saas): add billing dashboard with usage bars, plan comparison, and upgrade CTA"

# After welcome email
git commit -m "feat(saas): send automated welcome email on checkout.session.completed"

# After internal super-admin dashboard
git add frontend/app/internal/ backend/routes/internal.py
git commit -m "feat(saas): add internal super-admin dashboard for org and MRR overview"

# Version tag on merge to main
# (after PR merged to develop → staging tested → PR to main → approved)
git tag -a v1.0.0 -m "Initial SaaS release — AI Customer Engagement Platform"
git push origin v1.0.0
```

### Stripe Test Before Merging
```bash
# Forward Stripe webhooks to local dev
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# In separate terminal, trigger test checkout
stripe trigger checkout.session.completed

# Verify: org plan updated to "starter" in DB within 10 seconds
psql $DATABASE_URL -c "SELECT plan FROM billing_subscriptions WHERE org_id='...';"
```

### Release to Production
```bash
git push -u origin feature/phase-12-saas-readiness

# PR to develop (staging)
gh pr create \
  --title "feat: Phase 12 — SaaS Readiness" \
  --body "Stripe billing, plan enforcement, usage limits, onboarding wizard, billing UI, welcome email. Full platform MVP complete." \
  --base develop

# After staging validated → PR to main (production)
gh pr create \
  --title "release: v1.0.0 — Initial SaaS Release" \
  --body "All 12 phases complete. Load tested. Security reviewed. Stripe billing live." \
  --base main
```

---

## Definition of Done

Phase 12 is **complete** — and the **full platform is shippable** — when every item below is checked.

### Code Quality
- [ ] `require_plan()` used on every feature endpoint that is plan-gated
- [ ] Stripe webhook handler is idempotent (safe to receive duplicate events)
- [ ] `STRIPE_LIVE_MODE` env var explicitly required in production settings
- [ ] Plan limits defined in one place (`PLAN_LIMITS` dict) — no scattered `if plan == "free"` checks

### Billing Functionality
- [ ] Free plan user blocked from booking appointments (returns `402` with upgrade message)
- [ ] Free plan user at 100K token limit returns `429` with upgrade message
- [ ] Stripe checkout completes → org plan updated in DB within 10 seconds (via webhook)
- [ ] Subscription cancelled in Stripe → org downgraded to free within 10 seconds
- [ ] Billing dashboard shows token usage matching `token_usage` table (within 5%)
- [ ] Downgraded org's over-limit documents become read-only, not deleted

### Onboarding
- [ ] New user signup → welcome email received within 2 minutes
- [ ] Onboarding wizard guides user to: upload 1 doc → test chat → (optionally) connect channel
- [ ] User can skip onboarding wizard and access dashboard directly

### Security
- [ ] Stripe webhook rejected with invalid signature returns `400`
- [ ] Internal super-admin endpoints return `403` for `org_admin` role
- [ ] `STRIPE_SECRET_KEY` only in `settings` — never logged or returned in API response

### Full Platform Checklist
- [ ] All 12 phase individual checklists pass
- [ ] Backend test coverage ≥ 80% overall
- [ ] Load test: 50 concurrent chat users, p95 < 3s, error rate < 0.1%
- [ ] No Sentry HIGH/CRITICAL errors in staging over 48h of test traffic
- [ ] Security scan: `bandit -r backend/` shows no HIGH severity issues; `npm audit --audit-level=high` clean
- [ ] `docker compose up` cold-starts full stack in < 2 minutes
- [ ] CI/CD deploys to staging in < 5 minutes on push to `develop`
- [ ] At least one real org onboarded end-to-end (docs uploaded, chat tested, lead created)
- [ ] `v1.0.0` tag pushed; GitHub Release created with changelog

### What is NOT Acceptable
- Stripe `LIVE_MODE` keys used in staging/development environments
- Plan limits that can be bypassed by calling endpoints without the `require_plan()` guard
- Stripe webhook that silently swallows subscription cancellation events
- Launching to production without the load test passing
