from __future__ import annotations

import imaplib
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr
from typing import Iterable


@dataclass(frozen=True)
class GmailMessage:
    uid: int
    message_id: str | None
    from_email: str
    subject: str
    body_text: str
    received_at_iso: str | None


class GmailImapClient:
    def __init__(
        self,
        *,
        address: str,
        app_password: str,
        imap_host: str = "imap.gmail.com",
        imap_port: int = 993,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ):
        self.address = address
        self.app_password = app_password
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    def send_mail(
        self,
        *,
        to_emails: list[str],
        subject: str,
        html_body: str,
    ) -> None:
        msg = EmailMessage()
        msg["From"] = self.address
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject

        # Include a plain-text fallback.
        msg.set_content("This email requires an HTML-capable client.")
        msg.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(self.address, self.app_password)
            smtp.send_message(msg)

    def fetch_messages_since_uid(self, *, since_uid: int) -> list[GmailMessage]:
        """Fetch messages with UID > since_uid from INBOX.

        Notes:
        - Uses IMAP UIDs, which are monotonically increasing within a mailbox.
        - Returns minimal parsed fields needed by the app.
        """

        with imaplib.IMAP4_SSL(self.imap_host, self.imap_port) as imap:
            imap.login(self.address, self.app_password)
            imap.select("INBOX")

            # UID search range is inclusive; move past cursor.
            search_criteria = f"UID {since_uid + 1}:*" if since_uid >= 0 else "ALL"
            status, data = imap.uid("search", None, search_criteria)
            if status != "OK" or not data or not data[0]:
                return []

            uids = [int(x) for x in data[0].split() if x.strip().isdigit()]
            messages: list[GmailMessage] = []

            for uid in uids:
                status, msg_data = imap.uid("fetch", str(uid), "(RFC822)")
                if status != "OK" or not msg_data:
                    continue

                raw_bytes = None
                for part in msg_data:
                    if (
                        isinstance(part, tuple)
                        and part
                        and isinstance(part[1], (bytes, bytearray))
                    ):
                        raw_bytes = part[1]
                        break
                if not raw_bytes:
                    continue

                parsed = BytesParser(policy=default).parsebytes(raw_bytes)

                from_email = (parseaddr(parsed.get("From") or "")[1] or "").lower()
                subject = parsed.get("Subject") or ""
                message_id = parsed.get("Message-ID")
                date_hdr = parsed.get("Date")

                body_text = _extract_text(parsed)

                messages.append(
                    GmailMessage(
                        uid=uid,
                        message_id=message_id,
                        from_email=from_email,
                        subject=subject,
                        body_text=body_text,
                        received_at_iso=None if not date_hdr else str(date_hdr),
                    )
                )

            return messages


def _walk_parts(message) -> Iterable:
    if not message.is_multipart():
        return [message]
    return message.walk()


def _extract_text(message) -> str:
    # Prefer text/plain, then text/html.
    text_plain: list[str] = []
    text_html: list[str] = []

    for part in _walk_parts(message):
        content_type = (part.get_content_type() or "").lower()
        if content_type not in {"text/plain", "text/html"}:
            continue
        if part.get_content_disposition() == "attachment":
            continue

        try:
            payload = part.get_content()
        except Exception:
            continue

        if not isinstance(payload, str):
            continue

        if content_type == "text/plain":
            text_plain.append(payload)
        elif content_type == "text/html":
            text_html.append(payload)

    if text_plain:
        return "\n".join(text_plain).strip()
    if text_html:
        return "\n".join(text_html).strip()
    return ""
