"""End-to-end API test: start a task over HTTP, watch events over the WebSocket.

Uses FastAPI's TestClient with a FakeBrowserSession and a scripted Jev client, so
the whole service path (auth, task start, worker thread, event hub, WS fan-out)
is exercised without a real browser or network.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from agent.api.config import Config
from agent.api.server import create_app
from agent.browser.browser import FakeBrowserSession
from agent.core.state import Element
from agent.model.jev import DecisionEngine
from tests.mock_jev import ScriptedJevClient, response

TOKEN = "test-token-123"
ORIGIN = "chrome-extension://abcdef"


def _factories():
    def browser_factory():
        home = ("https://ex.com", "Home", [
            Element(index=0, role="textbox", name="Search", editable=True, can_type=True),
            Element(index=1, role="button", name="Search", can_click=True),
        ])
        results = ("https://ex.com/r", "Results", [Element(index=2, role="link", name="Result", can_click=True)])
        return FakeBrowserSession([home, results], transition=lambda a, el, i: 1 if a == "click" else i)

    def engine_factory():
        return DecisionEngine(ScriptedJevClient([
            response("CLICK", {"target_click": 1}),
            response("DONE"),
        ]))

    return browser_factory, engine_factory


def _app():
    bf, ef = _factories()
    return create_app(Config(request_token=TOKEN), browser_factory=bf, engine_factory=ef)


def test_health_reports_capabilities():
    client = TestClient(_app())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "has_jev_key" in body and "has_text_model" in body


def test_start_requires_token():
    client = TestClient(_app())
    r = client.post("/tasks", json={"goal": "do it"}, headers={"origin": ORIGIN})
    assert r.status_code == 401


def test_start_rejects_bad_origin():
    client = TestClient(_app())
    r = client.post("/tasks", json={"goal": "do it"}, headers={"x-agent-token": TOKEN, "origin": "https://evil.com"})
    assert r.status_code == 403


def test_full_task_over_http_and_ws():
    client = TestClient(_app())
    r = client.post(
        "/tasks",
        json={"goal": "search and open", "context": {"url": "https://ex.com"}},
        headers={"x-agent-token": TOKEN, "origin": ORIGIN},
    )
    assert r.status_code == 200
    data = r.json()
    task_id = data["task"]["id"]
    assert data["ws"] == f"/events/{task_id}"

    # Wait for the task to reach a terminal state via HTTP polling.
    deadline = time.time() + 5
    status = "running"
    while time.time() < deadline:
        info = client.get(f"/tasks/{task_id}", headers={"x-agent-token": TOKEN}).json()
        status = info["status"]
        if status in ("success", "blocked", "error", "stopped"):
            break
        time.sleep(0.05)
    assert status == "success"

    # The event history recorded the full, verified completion. (Live WS delivery
    # is covered by test_ws_streams_first_event; here we assert the recorded
    # outcome without depending on half-duplex TestClient streaming timing.)
    app = client.app
    history = app.state.hub._history[task_id]
    types = [e["type"] for e in history]
    assert "agent.completed" in types
    completed = next(e for e in history if e["type"] == "agent.completed")
    assert completed.get("outcome") == "success"


def test_ws_streams_first_event():
    client = TestClient(_app())
    r = client.post("/tasks", json={"goal": "x"}, headers={"x-agent-token": TOKEN, "origin": ORIGIN})
    task_id = r.json()["task"]["id"]
    # Let the task finish so history is buffered for replay.
    time.sleep(0.6)
    with client.websocket_connect(f"/events/{task_id}?token={TOKEN}") as ws:
        first = ws.receive_json()
    assert first["type"].startswith("agent.")


def test_ws_rejects_bad_token():
    client = TestClient(_app())
    r = client.post("/tasks", json={"goal": "x"}, headers={"x-agent-token": TOKEN, "origin": ORIGIN})
    task_id = r.json()["task"]["id"]
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/events/{task_id}?token=wrong") as ws:
            ws.receive_json()


def test_stop_endpoint():
    client = TestClient(_app())
    r = client.post("/tasks", json={"goal": "x"}, headers={"x-agent-token": TOKEN, "origin": ORIGIN})
    task_id = r.json()["task"]["id"]
    s = client.post(f"/tasks/{task_id}/stop", headers={"x-agent-token": TOKEN})
    assert s.status_code == 200 and s.json()["ok"] is True
