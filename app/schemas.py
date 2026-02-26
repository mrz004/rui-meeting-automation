from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


class CreateMeetingRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    attendees: list[EmailStr] = Field(min_length=1)

    # Provide explicit ISO timestamps; simplest first version.
    # Example: 2026-02-27T15:00:00
    start_iso: str
    end_iso: str

    # IANA tz name preferred; Graph accepts Windows tz in some places.
    timezone: str = "UTC"


class MeetingRequestStatus(BaseModel):
    id: str
    status: str
    subject: str
    start_iso: str
    end_iso: str
    timezone: str
    attendees: list[str]
    responses: list[dict]
    teams_join_url: str | None = None


class CreateSubscriptionResponse(BaseModel):
    id: str
    resource: str
    expirationDateTime: str


class GraphNotification(BaseModel):
    subscriptionId: str
    clientState: str | None = None
    resource: str
    changeType: str | None = None
    resourceData: dict | None = None


class GraphNotificationEnvelope(BaseModel):
    value: list[GraphNotification]
