"""Browser session: the one authoritative execution layer (PROMPT §21).

``BrowserSession`` is the interface the agent uses to observe and act on a tab.
Two implementations:

* :class:`FakeBrowserSession` — an in-memory page model driven by a list of
  ``Element`` states with scripted transitions. It lets the whole
  observe→decide→act→verify loop run deterministically in tests and in the
  proof-of-work, with no real browser.
* :class:`CdpBrowserSession` — drives a real page over the Chrome DevTools
  Protocol: it injects ``snapshot.js`` to observe, and performs input via CDP.

The agent depends only on the interface, so the loop is identical either way.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Callable

from agent.core.state import Element, Observation

_SNAPSHOT_JS_PATH = os.path.join(os.path.dirname(__file__), "snapshot.js")


def load_snapshot_js() -> str:
    with open(_SNAPSHOT_JS_PATH, encoding="utf-8") as fh:
        return fh.read()


def parse_snapshot(payload: dict) -> Observation:
    """Translate the snapshot.js JSON payload into an :class:`Observation`."""
    elements = []
    for e in payload.get("elements", []):
        elements.append(
            Element(
                index=int(e["index"]),
                role=e.get("role", ""),
                name=e.get("name", ""),
                value=e.get("value"),
                editable=bool(e.get("editable")),
                checked=e.get("checked"),
                selected=e.get("selected"),
                disabled=bool(e.get("disabled")),
                can_click=bool(e.get("can_click")),
                can_type=bool(e.get("can_type")),
                can_select=bool(e.get("can_select")),
                options=list(e.get("options") or []),
            )
        )
    return Observation(
        url=payload.get("url", ""),
        title=payload.get("title", ""),
        elements=elements,
        fingerprint=payload.get("fingerprint", ""),
    )


class BrowserSession(ABC):
    @abstractmethod
    def observe(self) -> Observation:
        """Take a fresh snapshot of the current page."""

    @abstractmethod
    def click(self, element: Element) -> bool: ...

    @abstractmethod
    def type_text(self, element: Element, text: str) -> bool: ...

    @abstractmethod
    def select(self, element: Element, option_index: int) -> bool: ...

    @abstractmethod
    def scroll(self, dy: int) -> bool: ...

    def close(self) -> None:  # pragma: no cover - optional
        return None


class FakeBrowserSession(BrowserSession):
    """A scriptable in-memory page for tests and the proof-of-work.

    ``pages`` is a list of ``(url, title, [Element,...])`` states. A transition
    function maps ``(action, element, current_index) -> next_index`` so actions
    can advance the page exactly as a real site would.
    """

    def __init__(
        self,
        pages: list[tuple[str, str, list[Element]]],
        transition: Callable[[str, Element | None, int], int] | None = None,
    ) -> None:
        self._pages = pages
        self._i = 0
        self._transition = transition
        self.actions: list[tuple[str, object]] = []

    def _fingerprint(self) -> str:
        url, title, els = self._pages[self._i]
        parts = "|".join(f"{e.role}:{e.short()}:{e.value or ''}:{e.checked}" for e in els[:40])
        return f"{url}|{title}|{len(els)}|{parts}"

    def observe(self) -> Observation:
        url, title, els = self._pages[self._i]
        return Observation(url=url, title=title, elements=list(els), fingerprint=self._fingerprint())

    def _advance(self, action: str, element: Element | None) -> bool:
        self.actions.append((action, element.index if element else None))
        if self._transition is not None:
            self._i = self._transition(action, element, self._i)
        return True

    def click(self, element: Element) -> bool:
        return self._advance("click", element)

    def type_text(self, element: Element, text: str) -> bool:
        self.actions.append(("type", text))
        # Reflect the typed value into the live element for verification.
        element.value = text
        if self._transition is not None:
            self._i = self._transition("type", element, self._i)
        return True

    def select(self, element: Element, option_index: int) -> bool:
        return self._advance("select", element)

    def scroll(self, dy: int) -> bool:
        self.actions.append(("scroll", dy))
        return True


class CdpBrowserSession(BrowserSession):  # pragma: no cover - needs real Chrome
    """Drives a real page over the Chrome DevTools Protocol.

    ``send`` is a callable that issues a CDP command and returns its result,
    supplied by the browser harness / connection layer. This class owns only the
    observe/act semantics; the transport lives elsewhere so there is a single
    authoritative execution layer.
    """

    def __init__(self, send: Callable[[str, dict], dict]) -> None:
        self._send = send
        self._snapshot_js = load_snapshot_js()

    def observe(self) -> Observation:
        result = self._send(
            "Runtime.evaluate",
            {"expression": self._snapshot_js, "returnByValue": True, "awaitPromise": True},
        )
        raw = result.get("result", {}).get("value")
        payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return parse_snapshot(payload)

    def _node_expr(self, index: int) -> str:
        return f"window.__jevAgent && window.__jevAgent.nodes[{index}]"

    def click(self, element: Element) -> bool:
        expr = f"(() => {{ const n = {self._node_expr(element.index)}; if(!n) return false; n.click(); return true; }})()"
        r = self._send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return bool(r.get("result", {}).get("value"))

    def type_text(self, element: Element, text: str) -> bool:
        payload = json.dumps(text)
        expr = (
            f"(() => {{ const n = {self._node_expr(element.index)}; if(!n) return false; "
            f"n.focus(); n.select && n.select(); "
            f"n.value = {payload}; "
            f"n.dispatchEvent(new Event('input', {{bubbles:true}})); "
            f"n.dispatchEvent(new Event('change', {{bubbles:true}})); return true; }})()"
        )
        r = self._send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return bool(r.get("result", {}).get("value"))

    def select(self, element: Element, option_index: int) -> bool:
        expr = (
            f"(() => {{ const n = {self._node_expr(element.index)}; if(!n) return false; "
            f"n.selectedIndex = {int(option_index)}; "
            f"n.dispatchEvent(new Event('change', {{bubbles:true}})); return true; }})()"
        )
        r = self._send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return bool(r.get("result", {}).get("value"))

    def scroll(self, dy: int) -> bool:
        expr = f"window.scrollBy(0, {int(dy)}); true"
        self._send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return True
