# Mail Automation (Email → Gemini → Teams)

Minimal backend that:

1. Creates a meeting request with attendee emails + a fixed time
2. Sends emails via Microsoft Graph
3. Receives Microsoft Graph webhook notifications for new inbox messages
4. Uses Gemini API to classify replies as accepted/declined
5. When **all** attendees accept, creates a Teams meeting (Graph calendar event)

## Prerequisites

- Python 3.10+
- Microsoft 365 tenant + an Entra ID (Azure AD) App Registration
- A publicly reachable HTTPS URL for the webhook (e.g. ngrok)

## Microsoft Graph permissions (App-only)

In App Registration → **API permissions** → Microsoft Graph → **Application permissions**:

- `Mail.Send`
- `Mail.Read`
- `Calendars.ReadWrite`
- `Subscriptions.Read.All`

Then **Grant admin consent**.

## Setup

1. Create `.env` from `.env.example`

2. Fill in:

- `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`
- `SENDER_USER_PRINCIPAL_NAME` (the mailbox to send from and monitor)
- `PUBLIC_BASE_URL` (must be public HTTPS, e.g. `https://xxxx.ngrok-free.app`)
- `GRAPH_CLIENT_STATE` (any random string)
- `GEMINI_API_KEY`

3. Install deps

- `pip install -r requirements.txt`

4. Run API

- `uvicorn app.main:app --reload --port 8000`

## Expose webhook (dev)

Microsoft Graph must reach your webhook URL.

Example with ngrok:

- `ngrok http 8000`
- Set `PUBLIC_BASE_URL` to the `https://...` URL ngrok prints

## Create a subscription

Graph subscriptions expire and must be renewed periodically.

- `POST http://localhost:8000/admin/subscriptions`

This registers the webhook at:

- `PUBLIC_BASE_URL/graph/notifications`

## Create a meeting request

- `POST http://localhost:8000/requests`

Example body:

```json
{
    "subject": "Design sync",
    "body": "Quick sync on the new flow.",
    "attendees": ["a@contoso.com", "b@contoso.com"],
    "start_iso": "2026-02-27T15:00:00",
    "end_iso": "2026-02-27T15:30:00",
    "timezone": "UTC"
}
```

The email contains a token like:

- `RequestId: <uuid>`

Attendees can reply "Yes" / "No". The system will classify the reply with Gemini.

## Check status

- `GET http://localhost:8000/requests/{request_id}`

If all attendees accept, status becomes `SCHEDULED` and a Teams meeting is created.

## Notes / limitations (first version)

- Correlation uses `RequestId: <uuid>` in the reply body/subject (simple and robust)
- Webhook processing is minimal; for production you’d want retries + a queue
- Subscription renewal is not automated yet
