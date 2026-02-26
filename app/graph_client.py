from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


@dataclass
class GraphToken:
    access_token: str
    expires_at: float


class GraphClient:
    def __init__(self, *, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: GraphToken | None = None
        self._http = httpx.AsyncClient(timeout=30)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get_token(self) -> str:
        now = time.time()
        if self._token and self._token.expires_at - 60 > now:
            return self._token.access_token

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        resp = await self._http.post(url, data=data)
        resp.raise_for_status()
        payload = resp.json()
        access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3599))
        self._token = GraphToken(access_token=access_token, expires_at=now + expires_in)
        return access_token

    async def request(
        self, method: str, url: str, *, json: dict | None = None
    ) -> httpx.Response:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = await self._http.request(method, url, headers=headers, json=json)
        resp.raise_for_status()
        return resp

    async def send_mail(
        self,
        *,
        sender_upn: str,
        to_emails: list[str],
        subject: str,
        html_body: str,
    ) -> None:
        url = f"https://graph.microsoft.com/v1.0/users/{sender_upn}/sendMail"
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": e}} for e in to_emails],
        }
        payload = {"message": message, "saveToSentItems": True}
        await self.request("POST", url, json=payload)

    async def create_subscription(
        self,
        *,
        resource: str,
        notification_url: str,
        expiration_iso: str,
        client_state: str,
    ) -> dict:
        url = "https://graph.microsoft.com/v1.0/subscriptions"
        payload = {
            "changeType": "created",
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration_iso,
            "clientState": client_state,
        }
        resp = await self.request("POST", url, json=payload)
        return resp.json()

    async def get_message(self, *, user_upn: str, message_id: str) -> dict:
        url = f"https://graph.microsoft.com/v1.0/users/{user_upn}/messages/{message_id}?$select=id,subject,from,receivedDateTime,body"
        resp = await self.request("GET", url)
        return resp.json()

    async def create_teams_meeting_event(
        self,
        *,
        organizer_upn: str,
        subject: str,
        body_html: str,
        start_iso: str,
        end_iso: str,
        timezone: str,
        attendees: list[str],
    ) -> dict:
        # Creates a calendar event with Teams meeting link.
        url = f"https://graph.microsoft.com/v1.0/users/{organizer_upn}/events"
        payload = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "start": {"dateTime": start_iso, "timeZone": timezone},
            "end": {"dateTime": end_iso, "timeZone": timezone},
            "attendees": [
                {"emailAddress": {"address": e}, "type": "required"} for e in attendees
            ],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        }
        resp = await self.request("POST", url, json=payload)
        return resp.json()
