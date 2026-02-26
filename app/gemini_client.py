from __future__ import annotations

import json

import httpx


class GeminiClient:
    def __init__(self, *, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._http = httpx.AsyncClient(timeout=30)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def classify_acceptance(self, *, text: str) -> dict:
        """Return {'accepted': bool, 'confidence': float, 'reason': str}."""

        # Keep it robust: force JSON response with a very small schema.
        prompt = (
            "You are a strict classifier for meeting-invite replies. "
            "Given an email reply text, decide if the sender ACCEPTED the meeting request. "
            "Return JSON only with keys: accepted (boolean), confidence (number 0..1), reason (string). "
            "Rules: 'yes', 'okay', 'sounds good', 'confirmed', 'I will join' => accepted=true. "
            "'no', 'can't', 'decline', 'not available', 'reschedule', 'maybe', 'later' => accepted=false. "
            "If ambiguous, accepted=false."
            f"EMAIL_REPLY_TEXT:\n{text}\n"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 200,
                "responseMimeType": "application/json",
            },
        }

        resp = await self._http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Extract text from the first candidate.
        try:
            text_out = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return {"accepted": False, "confidence": 0.0, "reason": "No model output"}

        try:
            parsed = json.loads(text_out)
            accepted = bool(parsed.get("accepted", False))
            confidence = float(parsed.get("confidence", 0.0))
            reason = str(parsed.get("reason", ""))
            if confidence < 0.0:
                confidence = 0.0
            if confidence > 1.0:
                confidence = 1.0
            return {"accepted": accepted, "confidence": confidence, "reason": reason}
        except Exception:
            return {
                "accepted": False,
                "confidence": 0.0,
                "reason": "Non-JSON model output",
            }
