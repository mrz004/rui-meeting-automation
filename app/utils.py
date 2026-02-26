from __future__ import annotations

import re
from html import unescape


REQUEST_ID_RE = re.compile(r"RequestId\s*:\s*([0-9a-fA-F-]{36})")


def strip_html(html: str) -> str:
    # Good-enough plain text extraction for email bodies.
    text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return unescape(text)


def extract_request_id(text: str) -> str | None:
    m = REQUEST_ID_RE.search(text)
    return m.group(1) if m else None
