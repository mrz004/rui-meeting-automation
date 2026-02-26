from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from pydantic import ValidationError

from app.config import get_settings
from app.db import Db
from app.gemini_client import GeminiClient
from app.graph_client import GraphClient
from app.schemas import (
    CreateMeetingRequest,
    CreateSubscriptionResponse,
    GraphNotificationEnvelope,
    MeetingRequestStatus,
)
from app.utils import extract_request_id, strip_html

app = FastAPI(title="Mail Automation", version="0.1.0")


def _state(request: Request):
    if hasattr(request.app.state, "init_error"):
        raise HTTPException(
            status_code=503,
            detail="Service not configured. Set env vars in .env and restart. See /health.",
        )
    if not hasattr(request.app.state, "settings"):
        raise HTTPException(status_code=503, detail="Service not initialized")
    return request.app.state


@app.on_event("startup")
async def _startup() -> None:
    try:
        settings = get_settings()
    except ValidationError as e:
        # Let the server start so /health can explain what's missing.
        app.state.init_error = str(e)
        return
    app.state.settings = settings
    app.state.db = Db(settings.db_path)
    app.state.graph = GraphClient(
        tenant_id=settings.tenant_id,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
    )
    app.state.gemini = GeminiClient(
        api_key=settings.gemini_api_key, model=settings.gemini_model
    )


@app.get("/health")
async def health():
    if hasattr(app.state, "init_error"):
        return {"ok": False, "configured": False, "error": app.state.init_error}
    return {"ok": True, "configured": True}


@app.on_event("shutdown")
async def _shutdown() -> None:
    if hasattr(app.state, "graph"):
        await app.state.graph.aclose()
    if hasattr(app.state, "gemini"):
        await app.state.gemini.aclose()


def _meeting_email_html(
    *,
    request_id: str,
    subject: str,
    body: str,
    start_iso: str,
    end_iso: str,
    timezone: str,
) -> str:
    return (
        f"<p><b>{subject}</b></p>"
        f"<p>{body}</p>"
        f"<p><b>Proposed time:</b> {start_iso} to {end_iso} ({timezone})</p>"
        f"<p><b>RequestId:</b> {request_id}</p>"
        "<p>Please reply with 'Yes' to accept or 'No' to decline.</p>"
    )


async def _maybe_schedule_if_all_accepted(state, request_id: str) -> None:
    db: Db = state.db
    graph: GraphClient = state.graph

    req = db.get_meeting_request(request_id)
    if not req:
        return
    if req["status"] in ("SCHEDULED", "DECLINED"):
        return

    responses = db.list_attendee_responses(request_id)
    statuses = [r["status"] for r in responses]

    if any(s == "DECLINED" for s in statuses):
        db.set_meeting_declined(request_id)
        return

    if all(s == "ACCEPTED" for s in statuses):
        event = await graph.create_teams_meeting_event(
            organizer_upn=req["organizer_upn"],
            subject=req["subject"],
            body_html=req["body"],
            start_iso=req["start_iso"],
            end_iso=req["end_iso"],
            timezone=req["timezone"],
            attendees=req["attendees"],
        )
        join_url = (event.get("onlineMeeting") or {}).get("joinUrl")
        if not join_url:
            # Graph sometimes returns joinUrl differently; keep event id regardless.
            join_url = None
        db.set_meeting_scheduled(
            request_id=request_id,
            teams_join_url=join_url,
            graph_event_id=event.get("id", ""),
        )


@app.post("/requests", response_model=MeetingRequestStatus)
async def create_request(
    payload: CreateMeetingRequest, background: BackgroundTasks, request: Request
):
    state = _state(request)
    settings = state.settings
    db: Db = state.db
    graph: GraphClient = state.graph

    request_id = str(uuid4())

    attendees = sorted({str(e).lower() for e in payload.attendees})
    if not attendees:
        raise HTTPException(status_code=400, detail="No attendees")

    # Store the request.
    db.create_meeting_request(
        request_id=request_id,
        organizer_upn=settings.sender_user_principal_name,
        subject=payload.subject,
        body=payload.body,
        start_iso=payload.start_iso,
        end_iso=payload.end_iso,
        timezone=payload.timezone,
        attendees=attendees,
    )

    # Send email.
    html_body = _meeting_email_html(
        request_id=request_id,
        subject=payload.subject,
        body=payload.body,
        start_iso=payload.start_iso,
        end_iso=payload.end_iso,
        timezone=payload.timezone,
    )

    background.add_task(
        graph.send_mail,
        sender_upn=settings.sender_user_principal_name,
        to_emails=attendees,
        subject=f"Meeting Request: {payload.subject}",
        html_body=html_body,
    )

    req = db.get_meeting_request(request_id)
    return MeetingRequestStatus(
        id=req["id"],
        status=req["status"],
        subject=req["subject"],
        start_iso=req["start_iso"],
        end_iso=req["end_iso"],
        timezone=req["timezone"],
        attendees=req["attendees"],
        responses=db.list_attendee_responses(request_id),
        teams_join_url=req.get("teams_join_url"),
    )


@app.get("/requests/{request_id}", response_model=MeetingRequestStatus)
async def get_request(request_id: str, request: Request):
    state = _state(request)
    db: Db = state.db

    req = db.get_meeting_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    return MeetingRequestStatus(
        id=req["id"],
        status=req["status"],
        subject=req["subject"],
        start_iso=req["start_iso"],
        end_iso=req["end_iso"],
        timezone=req["timezone"],
        attendees=req["attendees"],
        responses=db.list_attendee_responses(request_id),
        teams_join_url=req.get("teams_join_url"),
    )


@app.post("/admin/subscriptions", response_model=CreateSubscriptionResponse)
async def create_inbox_subscription(
    request: Request,
    days_valid: int = Query(
        1,
        ge=1,
        le=3,
        description="Graph message subscriptions expire quickly; keep small.",
    ),
):
    state = _state(request)
    settings = state.settings
    graph: GraphClient = state.graph
    db: Db = state.db

    # Graph max expiration varies by resource; for messages, typically hours to days.
    expiration = datetime.now(timezone.utc) + timedelta(days=days_valid)
    expiration_iso = expiration.isoformat()

    # Watch inbox messages in the sender mailbox.
    resource = (
        f"/users/{settings.sender_user_principal_name}/mailFolders('Inbox')/messages"
    )
    notification_url = settings.public_base_url.rstrip("/") + "/graph/notifications"

    sub = await graph.create_subscription(
        resource=resource,
        notification_url=notification_url,
        expiration_iso=expiration_iso,
        client_state=settings.graph_client_state,
    )

    db.save_subscription(
        sub_id=sub["id"],
        resource=sub["resource"],
        expiration_iso=sub["expirationDateTime"],
    )

    return CreateSubscriptionResponse(
        id=sub["id"],
        resource=sub["resource"],
        expirationDateTime=sub["expirationDateTime"],
    )


@app.get("/admin/subscriptions")
async def list_subscriptions(request: Request):
    state = _state(request)
    db: Db = state.db
    return {"subscriptions": db.list_subscriptions()}


@app.api_route("/graph/notifications", methods=["GET", "POST"])
async def graph_notifications(request: Request, validationToken: str | None = None):
    # Validation handshake: Graph calls with ?validationToken=...
    if validationToken:
        return validationToken

    state = _state(request)
    settings = state.settings

    payload = await request.json()
    envelope = GraphNotificationEnvelope.model_validate(payload)

    for n in envelope.value:
        # Basic clientState validation if present.
        if n.clientState and n.clientState != settings.graph_client_state:
            continue

        message_id = None
        if n.resourceData and "id" in n.resourceData:
            message_id = n.resourceData["id"]
        else:
            # Fallback: resource ends with /messages/{id}
            parts = n.resource.split("/")
            if parts:
                message_id = parts[-1]

        if not message_id:
            continue

        # Fire-and-forget processing in background by awaiting inline (FastAPI will still handle quickly).
        await _process_incoming_message(state, message_id)

    return {"ok": True}


async def _process_incoming_message(state, message_id: str) -> None:
    settings = state.settings
    db: Db = state.db
    graph: GraphClient = state.graph
    gemini: GeminiClient = state.gemini

    msg = await graph.get_message(
        user_upn=settings.sender_user_principal_name, message_id=message_id
    )

    sender = ((msg.get("from") or {}).get("emailAddress") or {}).get("address")
    sender = (sender or "").lower()
    received = msg.get("receivedDateTime")

    body = (msg.get("body") or {}).get("content") or ""
    body_type = (msg.get("body") or {}).get("contentType") or ""
    subject = msg.get("subject") or ""

    text = strip_html(body) if body_type.lower() == "html" else body

    # Correlate to a request via RequestId token.
    request_id = extract_request_id(text) or extract_request_id(subject)
    if not request_id:
        return

    req = db.get_meeting_request(request_id)
    if not req:
        return

    if sender not in {a.lower() for a in req["attendees"]}:
        # Ignore mail not from expected attendees.
        return

    result = await gemini.classify_acceptance(text=text)
    status = "ACCEPTED" if result.get("accepted") else "DECLINED"

    db.update_attendee_response(
        request_id=request_id,
        attendee_email=sender,
        status=status,
        message_id=message_id,
        message_received_at_iso=received,
    )

    await _maybe_schedule_if_all_accepted(state, request_id)
