"""Browser-layer tests: snapshot parsing + a full multi-step loop (PROMPT §36)."""

from __future__ import annotations

from agent.browser.browser import FakeBrowserSession, parse_snapshot
from agent.core.agent import AgentRuntime
from agent.core.state import Element
from agent.core.task import TaskContext, TaskStatus
from agent.model.jev import DecisionEngine
from agent.model.text import TextHelper
from tests.mock_jev import ScriptedJevClient, response


def test_parse_snapshot_translates_payload():
    payload = {
        "url": "https://x.com",
        "title": "X",
        "fingerprint": "fp",
        "elements": [
            {"index": 0, "role": "textbox", "name": "Search", "value": "", "editable": True,
             "can_type": True, "can_click": False, "can_select": False},
            {"index": 1, "role": "button", "name": "Go", "can_click": True},
            {"index": 2, "role": "combobox", "name": "Country", "can_select": True, "options": ["US", "UK"]},
        ],
    }
    obs = parse_snapshot(payload)
    assert obs.url == "https://x.com" and obs.title == "X"
    assert len(obs.typeable()) == 1 and obs.typeable()[0].index == 0
    assert len(obs.clickable()) == 1 and obs.clickable()[0].index == 1
    assert len(obs.selectable()) == 1 and obs.selectable()[0].options == ["US", "UK"]


class _FixedText:
    def __init__(self, value: str):
        self._v = value

    def complete(self, system, user):
        return f'{{"text": "{self._v}"}}'


def test_full_search_flow_type_click_done():
    home = ("https://ex.com", "Home", [
        Element(index=0, role="textbox", name="Search", value="", editable=True, can_type=True),
        Element(index=1, role="button", name="Search", can_click=True),
    ])
    results = ("https://ex.com/r?q=laptop", "Results", [
        Element(index=2, role="link", name="Best Laptop 2026", can_click=True),
    ])

    def transition(action, element, i):
        if action == "click" and element is not None and element.role == "button":
            return 1
        return i

    browser = FakeBrowserSession([home, results], transition=transition)
    engine = DecisionEngine(ScriptedJevClient([
        response("TYPE_TEXT", {"target_type": 0}),
        response("CLICK", {"target_click": 1}),
        response("DONE"),
    ]))
    text = TextHelper(_FixedText("laptop"))
    events = []
    rt = AgentRuntime(browser, engine, text_helper=text, on_event=events.append, sleep=lambda s: None)

    task = rt.run(
        TaskContext(goal='search "laptop" and open a result', max_steps=10),
        verify_goal=lambda obs, goal: any(e.role == "link" for e in obs.elements),
    )
    assert task.status is TaskStatus.SUCCESS
    assert ("type", "laptop") in browser.actions
    assert ("click", 1) in browser.actions


def test_done_unverified_continues():
    # Page has no result link; DONE should be rejected and the loop continue
    # until step limit (BLOCKED via over_budget), never falsely reporting success.
    page = ("u", "t", [Element(index=0, role="button", name="X", can_click=True)])
    browser = FakeBrowserSession([page])
    engine = DecisionEngine(ScriptedJevClient([response("DONE")]))
    rt = AgentRuntime(browser, engine, sleep=lambda s: None)
    task = rt.run(
        TaskContext(goal="open a result", max_steps=3),
        verify_goal=lambda obs, goal: any(e.role == "link" for e in obs.elements),
    )
    assert task.status is not TaskStatus.SUCCESS
