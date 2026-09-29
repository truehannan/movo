"""CDP connection to a real Chrome tab (PROMPT §21).

Connects to a Chrome/Chromium instance launched with
``--remote-debugging-port`` and exposes a ``browser_factory`` that returns a
:class:`CdpBrowserSession` bound to the active tab. This is the authoritative
execution transport; the session class (browser.py) owns the observe/act
semantics.

Kept dependency-light: uses the CDP HTTP endpoint to list targets and a
WebSocket to issue ``Runtime.evaluate``. If no debuggable Chrome is reachable,
the factory raises a clear error the service surfaces to the extension.
"""

from __future__ import annotations

import itertools
import json
import os
from collections.abc import Callable

from agent.browser.browser import CdpBrowserSession


class CdpConnection:  # pragma: no cover - requires a live Chrome
    """A minimal synchronous CDP client over a target's WebSocket."""

    def __init__(self, ws_url: str) -> None:
        from websockets.sync.client import connect

        self._ws = connect(ws_url, max_size=32 * 1024 * 1024)
        self._ids = itertools.count(1)

    def send(self, method: str, params: dict) -> dict:
        mid = next(self._ids)
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message", "CDP error"))
                return msg.get("result", {})

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass


def _debug_host() -> tuple[str, int]:
    host = os.environ.get("CDP_HOST", "127.0.0.1")
    port = int(os.environ.get("CDP_PORT", "9222"))
    return host, port


def _active_page_ws() -> str:  # pragma: no cover - requires a live Chrome
    import httpx

    host, port = _debug_host()
    resp = httpx.get(f"http://{host}:{port}/json", timeout=3.0)
    resp.raise_for_status()
    targets = resp.json()
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        raise RuntimeError("no debuggable Chrome page found")
    return pages[0]["webSocketDebuggerUrl"]


def connect_active_tab_factory(config) -> Callable[[], CdpBrowserSession]:
    """Return a factory that connects to the active tab on demand.

    Connection is lazy: it only attempts CDP when a task actually starts, so the
    service boots even if Chrome is not yet running with remote debugging.
    """

    def factory() -> CdpBrowserSession:  # pragma: no cover - requires a live Chrome
        ws_url = _active_page_ws()
        conn = CdpConnection(ws_url)
        conn.send("Runtime.enable", {})
        return CdpBrowserSession(send=conn.send)

    return factory
