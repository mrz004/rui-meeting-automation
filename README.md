# Mail Automation (Email → Gemini → Teams)

Minimal backend that:

1. Creates a meeting request with attendee emails + a fixed time
2. Sends emails (default: Gmail SMTP)
3. Polls the inbox for new replies (default: Gmail IMAP polling)
4. Uses Gemini API to classify replies as accepted/declined
5. When **all** attendees accept, creates a Teams meeting (Microsoft Graph calendar event)

## Prerequisites

- Python 3.10+
- Google account (Gmail) with **2FA enabled** + a **Gmail App Password** (for SMTP/IMAP)
- Microsoft 365 tenant + an Entra ID (Azure AD) App Registration (used to create the Teams meeting link)

Note: The original Microsoft Graph webhook mode is still available, but the default setup is Gmail + polling (no webhook required).

## Microsoft Graph permissions (App-only)

### For Teams meeting creation (Graph calendar event)

In App Registration → **API permissions** → Microsoft Graph → **Application permissions**:

- `Calendars.ReadWrite`

(Depending on your tenant policies, you may also need online meeting permissions such as `OnlineMeetings.ReadWrite.All`.)

Then **Grant admin consent**.

### Only if using Microsoft Graph mail/webhook mode (`MAIL_MODE=graph`)

In App Registration → **API permissions** → Microsoft Graph → **Application permissions**:

- `Mail.Send`
- `Mail.Read`
- `Subscriptions.ReadWrite.All`

## Setup

1. Create `.env` from `.env.example`

2. Fill in (default: Gmail + polling + Teams link):

- `MAIL_MODE=gmail_imap`
- `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`
- `POLL_INTERVAL_SECONDS` (optional)
- `TEAMS_TENANT_ID`, `TEAMS_CLIENT_ID`, `TEAMS_CLIENT_SECRET`, `TEAMS_ORGANIZER_UPN`
- `GEMINI_API_KEY`

3. Install deps

- `pip install -r requirements.txt`

4. Run API

- From the repo root:
    - `uvicorn app.main:app --reload --port 8000`
    - or `python -m app`

Avoid running `python app/main.py` from inside the `app/` folder, since that breaks package imports.

## Notes for Gmail app passwords

Gmail SMTP/IMAP in this project uses an App Password.

- Enable 2-Step Verification on the Google account
- Create an App Password and put it in `GMAIL_APP_PASSWORD`

## (Optional) Microsoft Graph webhook mode

If you set `MAIL_MODE=graph`, the app uses Graph to send mail + receive webhook notifications.

In that mode you also need:

- `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`
- `SENDER_USER_PRINCIPAL_NAME`
- `PUBLIC_BASE_URL` (public HTTPS URL, e.g. ngrok)
- `GRAPH_CLIENT_STATE`

And you must create a subscription:

- `POST http://localhost:8000/admin/subscriptions`

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
