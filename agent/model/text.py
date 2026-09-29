"""Text-generation helper for TYPE_TEXT values (PROMPT §12).

Interaction selection (Jev) is separate from text generation. When Jev chooses
TYPE_TEXT for a field, this small helper produces the actual string via an
OpenAI-compatible chat model, constrained to return ``{"text": ...}``. The
result is validated so raw model output can never become JavaScript, selectors,
coordinates, or browser commands — only a plain string is typed.

The client is injectable so tests provide canned values without a network call.
"""

from __future__ import annotations

import json
from typing import Protocol

from agent.model.questions import TEXT_VALUE


class TextClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the raw model text (expected to be a JSON object)."""


def _validate(raw: str) -> str | None:
    """Parse the helper output and return a safe plain string, or None."""
    if not raw:
        return None
    text = raw.strip()
    # Strip a ```json fence if present.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or "text" not in obj:
        return None
    val = obj["text"]
    if val is None:
        return None
    if not isinstance(val, str):
        return None
    # A plain string only — never allow multi-line code blocks or scripts.
    val = val.strip()
    return val or None


class TextHelper:
    """Generates and validates the string for a TYPE_TEXT action."""

    def __init__(self, client: TextClient) -> None:
        self._client = client

    def value_for(
        self,
        goal: str,
        field_label: str,
        url: str,
        recent_actions: list[str] | None = None,
    ) -> str | None:
        user = json.dumps(
            {
                "goal": goal,
                "field": field_label,
                "url": url,
                "recent_actions": (recent_actions or [])[-5:],
            }
        )
        try:
            raw = self._client.complete(TEXT_VALUE, user)
        except Exception:
            return None
        return _validate(raw)


class OpenAICompatibleTextClient:
    """Calls an OpenAI-compatible /chat/completions endpoint (server-side)."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - network
        import httpx

        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
