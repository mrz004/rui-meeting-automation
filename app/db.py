from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Db:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connect(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meeting_requests (
                    id TEXT PRIMARY KEY,
                    organizer_upn TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    start_iso TEXT NOT NULL,
                    end_iso TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    attendees_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL,
                    teams_join_url TEXT,
                    graph_event_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attendee_responses (
                    request_id TEXT NOT NULL,
                    attendee_email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_message_id TEXT,
                    last_message_received_at_iso TEXT,
                    updated_at_iso TEXT NOT NULL,
                    PRIMARY KEY (request_id, attendee_email)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_subscriptions (
                    id TEXT PRIMARY KEY,
                    resource TEXT NOT NULL,
                    expiration_iso TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL
                )
                """
            )

    def create_meeting_request(
        self,
        *,
        request_id: str,
        organizer_upn: str,
        subject: str,
        body: str,
        start_iso: str,
        end_iso: str,
        timezone: str,
        attendees: list[str],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_requests (
                    id, organizer_upn, subject, body, start_iso, end_iso, timezone,
                    attendees_json, status, created_at_iso
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    organizer_upn,
                    subject,
                    body,
                    start_iso,
                    end_iso,
                    timezone,
                    json.dumps(attendees),
                    "PENDING",
                    utc_now_iso(),
                ),
            )
            for email in attendees:
                conn.execute(
                    """
                    INSERT INTO attendee_responses (request_id, attendee_email, status, updated_at_iso)
                    VALUES (?, ?, ?, ?)
                    """,
                    (request_id, email.lower(), "UNKNOWN", utc_now_iso()),
                )

    def get_meeting_request(self, request_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            d = dict(row)
            d["attendees"] = json.loads(d.pop("attendees_json"))
            return d

    def list_attendee_responses(self, request_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM attendee_responses WHERE request_id = ? ORDER BY attendee_email",
                (request_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_attendee_response(
        self,
        *,
        request_id: str,
        attendee_email: str,
        status: str,
        message_id: str | None,
        message_received_at_iso: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE attendee_responses
                SET status = ?, last_message_id = ?, last_message_received_at_iso = ?, updated_at_iso = ?
                WHERE request_id = ? AND attendee_email = ?
                """,
                (
                    status,
                    message_id,
                    message_received_at_iso,
                    utc_now_iso(),
                    request_id,
                    attendee_email.lower(),
                ),
            )

    def set_meeting_scheduled(
        self,
        *,
        request_id: str,
        teams_join_url: str | None,
        graph_event_id: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE meeting_requests
                SET status = ?, teams_join_url = ?, graph_event_id = ?
                WHERE id = ?
                """,
                ("SCHEDULED", teams_join_url, graph_event_id, request_id),
            )

    def set_meeting_declined(self, request_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE meeting_requests SET status = ? WHERE id = ?",
                ("DECLINED", request_id),
            )

    def save_subscription(
        self, *, sub_id: str, resource: str, expiration_iso: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO graph_subscriptions (id, resource, expiration_iso, created_at_iso)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    resource = excluded.resource,
                    expiration_iso = excluded.expiration_iso
                """,
                (sub_id, resource, expiration_iso, utc_now_iso()),
            )

    def list_subscriptions(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM graph_subscriptions ORDER BY created_at_iso DESC"
            ).fetchall()
            return [dict(r) for r in rows]
