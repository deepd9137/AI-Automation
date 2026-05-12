# Phase 8 — Appointment Scheduling

## Objectives
Integrate Google Calendar and Calendly to let the AI assistant fetch available slots, book meetings on behalf of leads, send confirmation emails, and display appointment history in the dashboard.

## Dependencies
- Phase 2 (auth — OAuth tokens stored per org)
- Phase 3 (appointments table, integrations table)
- Phase 6 (chat system — booking triggered from conversation)
- Phase 7 (lead must exist before booking appointment)

## Estimated Duration
3–4 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | Google Calendar OAuth flow | Admin connects calendar via `/integrations/google-calendar/connect` |
| 2 | Calendly OAuth flow | Admin connects Calendly account |
| 3 | `GET /scheduling/slots` — available times | Returns next N available slots in lead's timezone |
| 4 | `POST /scheduling/book` — create appointment | Event created in external calendar, saved in DB |
| 5 | Confirmation email sent | Lead receives email with calendar invite details |
| 6 | AI chat integration | Bot can offer/book slots within conversation |
| 7 | Appointment calendar view in dashboard | Shows booked appointments in calendar grid |
| 8 | `PATCH /scheduling/appointments/{id}` — cancel/reschedule | Cancels external event, updates DB |

---

## Architecture

### Files to Create
```
backend/
├── integrations/
│   ├── __init__.py
│   ├── google_calendar.py      # Google Calendar API wrapper
│   ├── calendly.py             # Calendly API wrapper
│   └── base_calendar.py        # CalendarProvider ABC
├── services/
│   └── scheduling_service.py   # business logic
├── routes/
│   ├── integrations.py         # OAuth connect/disconnect
│   └── scheduling.py           # slots + booking endpoints
└── utils/
    └── email.py                # confirmation email sender
```

---

## Calendar Provider Abstraction

```python
# backend/integrations/base_calendar.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TimeSlot:
    start: datetime
    end: datetime
    timezone: str

@dataclass
class BookingResult:
    external_id: str
    title: str
    start: datetime
    end: datetime
    meet_link: str | None
    confirmation_url: str | None

class CalendarProvider(ABC):
    @abstractmethod
    async def get_available_slots(
        self,
        access_token: str,
        days_ahead: int = 7,
        slot_duration_minutes: int = 30,
    ) -> list[TimeSlot]: ...

    @abstractmethod
    async def book_appointment(
        self,
        access_token: str,
        slot: TimeSlot,
        attendee_email: str,
        attendee_name: str,
        title: str,
        description: str = "",
    ) -> BookingResult: ...

    @abstractmethod
    async def cancel_appointment(self, access_token: str, event_id: str) -> None: ...
```

---

## Google Calendar Integration

### OAuth Flow
```python
# backend/integrations/google_calendar.py
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from backend.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_oauth_flow() -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                "redirect_uris": [settings.GOOGLE_CALENDAR_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )
```

### Available Slots Algorithm
```python
async def get_available_slots(self, access_token: str, days_ahead: int = 7) -> list[TimeSlot]:
    service = self._build_service(access_token)

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    # Fetch existing events (busy times)
    events = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    busy_periods = [
        (parse_datetime(e["start"]["dateTime"]), parse_datetime(e["end"]["dateTime"]))
        for e in events.get("items", [])
        if "dateTime" in e.get("start", {})
    ]

    # Generate 30-min slots during business hours (9am-5pm)
    slots = []
    cursor = now.replace(hour=9, minute=0, second=0, microsecond=0)
    while cursor < end:
        slot_end = cursor + timedelta(minutes=30)
        if cursor.hour >= 9 and slot_end.hour <= 17 and cursor.weekday() < 5:
            if not any(b[0] < slot_end and b[1] > cursor for b in busy_periods):
                slots.append(TimeSlot(start=cursor, end=slot_end, timezone="UTC"))
        cursor += timedelta(minutes=30)

    return slots[:10]   # return next 10 available
```

---

## Calendly Integration

```python
# backend/integrations/calendly.py
import httpx

class CalendlyProvider(CalendarProvider):
    BASE_URL = "https://api.calendly.com"

    async def get_available_slots(self, access_token: str, **kwargs) -> list[TimeSlot]:
        async with httpx.AsyncClient() as client:
            # Get user URI
            me = await client.get(f"{self.BASE_URL}/users/me",
                                  headers={"Authorization": f"Bearer {access_token}"})
            user_uri = me.json()["resource"]["uri"]

            # Get event types
            event_types = await client.get(
                f"{self.BASE_URL}/event_types",
                params={"user": user_uri},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            # Get available times for first active event type
            # ... parse and return TimeSlot list
```

---

## Scheduling Service (`backend/services/scheduling_service.py`)

```python
from backend.repositories.appointment_repo import AppointmentRepository
from backend.repositories.integration_repo import get_integration
from backend.integrations.google_calendar import GoogleCalendarProvider
from backend.integrations.calendly import CalendlyProvider
from backend.utils.email import send_confirmation_email
from backend.utils.crypto import decrypt_token

PROVIDERS: dict[str, type] = {
    "google_calendar": GoogleCalendarProvider,
    "calendly": CalendlyProvider,
}

class SchedulingService:
    def __init__(self, repo: AppointmentRepository):
        self.repo = repo

    async def get_provider(self, org_id: str, db) -> tuple:
        # Try providers in priority order
        for provider_name in ["google_calendar", "calendly"]:
            integration = await get_integration(db, org_id, provider_name)
            if integration and integration.is_active:
                token = decrypt_token(integration.access_token)
                return PROVIDERS[provider_name](), token, provider_name
        raise ValueError("No active calendar integration configured")

    async def get_slots(self, org_id: str, db) -> list[dict]:
        provider, token, _ = await self.get_provider(org_id, db)
        slots = await provider.get_available_slots(token)
        return [{"start": s.start.isoformat(), "end": s.end.isoformat(), "timezone": s.timezone}
                for s in slots]

    async def book(
        self,
        org_id: str,
        lead_id: str,
        slot: TimeSlot,
        lead_email: str,
        lead_name: str,
        db,
    ) -> dict:
        provider, token, provider_name = await self.get_provider(org_id, db)
        result = await provider.book_appointment(
            token, slot,
            attendee_email=lead_email,
            attendee_name=lead_name,
            title=f"Consultation with {lead_name}",
        )

        appointment = await self.repo.create({
            "org_id": org_id,
            "lead_id": lead_id,
            "external_id": result.external_id,
            "title": result.title,
            "start_time": result.start,
            "end_time": result.end,
            "timezone": slot.timezone,
            "location": result.meet_link,
            "status": "scheduled",
        })

        await send_confirmation_email(
            to=lead_email,
            name=lead_name,
            start=result.start,
            meet_link=result.meet_link,
        )

        return {"appointment_id": str(appointment.id), "meet_link": result.meet_link}
```

---

## AI Chat Booking Flow

The chat system (Phase 6) is extended to detect booking intent:

```
User: "I'd like to schedule a call"
AI:   "Great! Here are some available times: ..."
      [Slot 1: Thursday May 15, 2pm EST]
      [Slot 2: Friday May 16, 10am EST]
      "Which works for you?"
User: "Thursday at 2pm"
AI:   [calls POST /scheduling/book internally]
      "Done! I've booked your consultation for Thursday May 15 at 2pm EST.
       A confirmation has been sent to your email."
```

**Prompt addition** (appended to `faq_assistant` prompt when slots are injected):
```
If the user wants to schedule an appointment, present the following available slots:
{available_slots}
When the user selects a slot, respond with: [BOOK_SLOT:{slot_index}]
```

The chat service parses `[BOOK_SLOT:0]`, maps it to the slot, calls `SchedulingService.book()`, and replaces the signal with a confirmation message.

---

## OAuth Connection Flow

```
Admin clicks "Connect Google Calendar"
  → GET /api/v1/integrations/google-calendar/connect
  → Redirects to Google OAuth consent page

Google redirects back to:
  → GET /api/v1/integrations/google-calendar/callback?code=...
  → Exchange code for tokens
  → Encrypt tokens, store in integrations table
  → Redirect to dashboard with success message
```

Token storage:
- `access_token` and `refresh_token` encrypted with AES-256 using `cryptography` library.
- Encryption key from `settings.ENCRYPTION_KEY` (never in DB).

---

## API Endpoints

```
GET    /api/v1/integrations                             — list connected integrations
GET    /api/v1/integrations/google-calendar/connect    — OAuth redirect
GET    /api/v1/integrations/google-calendar/callback   — OAuth callback
DELETE /api/v1/integrations/{provider}                 — disconnect

GET    /api/v1/scheduling/slots                        — available slots
POST   /api/v1/scheduling/book                         — book appointment
GET    /api/v1/scheduling/appointments                 — list appointments
GET    /api/v1/scheduling/appointments/{id}            — get one
PATCH  /api/v1/scheduling/appointments/{id}            — cancel/reschedule
```

---

## Frontend: Calendar View

```
frontend/app/dashboard/appointments/
└── page.tsx     # calendar grid + upcoming list
```

Uses `@fullcalendar/react` to display booked appointments. Clicking an event shows lead info and meeting link.

---

## Validation Checklist

- [ ] Google Calendar OAuth completes and tokens stored (encrypted) in integrations table
- [ ] `GET /scheduling/slots` returns ≥ 1 slot when calendar has free time next 7 days
- [ ] Booked appointment appears in Google Calendar within 5 seconds
- [ ] Confirmation email sent to lead's email after booking
- [ ] Booking overlapping slot returns `409 Conflict`
- [ ] Token refresh works when access token expires (Calendly tokens expire in 2 hours)
- [ ] Cancelling appointment updates status in DB and cancels Google Calendar event
- [ ] Org with no calendar integration connected returns clear `424 Dependency Required` error

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Google Calendar API quota (1000 req/100s) | Cache available slots for 5 minutes per org |
| Token expiry mid-conversation | Refresh token automatically using stored refresh_token |
| Calendly webhook vs polling | Use webhooks if available; fall back to polling every 5 min |
| Timezone mismatch | Store all times as UTC in DB; convert in API response using `pytz` |

## Rollback Strategy
If integration breaks: disconnect via DELETE endpoint (clears tokens). Appointments already booked remain in DB. Admin can cancel manually via calendar app. No DB migrations to rollback — appointments table created in Phase 3.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-8-scheduling
```

### Commit Checkpoints

```bash
# After CalendarProvider abstraction + token encryption util
git add backend/integrations/base_calendar.py backend/utils/crypto.py
git commit -m "feat(scheduling): add CalendarProvider ABC and token encryption utility"

# After Google Calendar OAuth flow + adapter
git add backend/integrations/google_calendar.py backend/routes/integrations.py
git commit -m "feat(scheduling): add Google Calendar OAuth connect/callback and slot fetching"

# After Calendly adapter
git add backend/integrations/calendly.py
git commit -m "feat(scheduling): add Calendly API adapter for slot retrieval"

# After SchedulingService (get slots + book)
git add backend/services/scheduling_service.py backend/repositories/appointment_repo.py
git commit -m "feat(scheduling): add SchedulingService for slot listing and appointment booking"

# After confirmation email
git add backend/utils/email.py
git commit -m "feat(scheduling): send confirmation email after successful booking"

# After chat integration (BOOK_SLOT signal)
git add backend/services/chat_service.py
git commit -m "feat(scheduling): integrate booking into chat via BOOK_SLOT signal"

# After scheduling API endpoints
git add backend/routes/scheduling.py
git commit -m "feat(scheduling): add slots, book, list, and cancel appointment endpoints"

# After calendar view UI
git add frontend/app/dashboard/appointments/
git commit -m "feat(scheduling): add appointment calendar view in admin dashboard"
```

### Test OAuth Flow Before Merging
```bash
# 1. Connect Google Calendar via browser OAuth flow
# 2. Call GET /scheduling/slots and verify real slots returned
# 3. Book a slot and verify event appears in Google Calendar
# 4. Check confirmation email delivered
# 5. Cancel appointment and verify Google Calendar event removed
```

### Merge to Develop
```bash
git push -u origin feature/phase-8-scheduling

gh pr create \
  --title "feat: Phase 8 — Appointment Scheduling" \
  --body "Google Calendar + Calendly OAuth, slot fetching, booking, confirmation email, AI chat integration, calendar UI." \
  --base develop
```

---

## Definition of Done

Phase 8 is **complete** when every item below is checked.

### Code Quality
- [ ] `CalendarProvider` is an abstract class — no direct Google API calls outside `GoogleCalendarProvider`
- [ ] OAuth tokens stored **encrypted** (AES-256) — never in plaintext in DB
- [ ] Provider selection is config-driven — no `if provider == "google"` in `SchedulingService`
- [ ] All times stored as UTC in DB — conversion to local timezone happens at API response layer

### Functionality
- [ ] Google Calendar OAuth completes and tokens stored in `integrations` table
- [ ] `GET /scheduling/slots` returns real available slots (no mocked data)
- [ ] Booking creates event in Google Calendar within 5 seconds
- [ ] Confirmation email received by lead after booking
- [ ] Booking an already-taken slot returns `409 Conflict`
- [ ] Cancelling appointment updates DB status and removes Google Calendar event
- [ ] Token auto-refresh works when Google access token expires (2-hour window)
- [ ] Org with no calendar connected returns clear `424 Dependency Required`

### Security
- [ ] OAuth tokens encrypted at rest (verified by checking DB column — should be opaque)
- [ ] `ENCRYPTION_KEY` comes from `settings` — never hardcoded

### Testing
- [ ] `pytest backend/tests/test_scheduling.py -v` — all tests pass
- [ ] Calendar API mocked in tests — no real Google/Calendly calls during CI
- [ ] Test covers: successful booking, duplicate slot conflict, missing integration

### What is NOT Acceptable
- OAuth tokens stored in plaintext in the `integrations` table
- Booking that does not create a real calendar event (no silent failures)
- Missing confirmation email on booking
- Google API called directly from `SchedulingService` (bypasses abstraction)
