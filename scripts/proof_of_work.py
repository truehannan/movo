#!/usr/bin/env python3
"""Proof of work: the real agent loop drives a scripted search page.

No UI, no network. It runs the actual AgentRuntime — observe → Jev decision
(operation + per-operation target) → text helper (for TYPE_TEXT) → guarded
execute (stale-checked) → verify — against a FakeBrowserSession modelling a
search page:

  page 0: a search textbox [0] + a Search button [1]
  page 1 (after search submitted): results incl. a result link

Jev is scripted (deterministic stand-in for the model): TYPE_TEXT→[0],
CLICK→[1] (search), then DONE. The text helper returns a fixed query. Success is
verified independently: the results page must actually show a result.

Run:  PYTHONPATH=. python scripts/proof_of_work.py
"""

from __future__ import annotations

import sys

from agent.browser.browser import FakeBrowserSession
from agent.core.agent import AgentRuntime
from agent.core.state import Element
from agent.core.task import TaskContext
from agent.model.jev import DecisionEngine
from agent.model.text import TextHelper

sys.path.insert(0, ".")
from tests.mock_jev import ScriptedJevClient, response  # noqa: E402


def build_pages():
    search_box = Element(index=0, role="textbox", name="Search", value="", editable=True, can_type=True)
    search_btn = Element(index=1, role="button", name="Search", can_click=True)
    home = ("https://example.com", "Example Search", [search_box, search_btn])

    result = Element(index=2, role="link", name="OpenAI - Wikipedia", can_click=True)
    results = ("https://example.com/results?q=OpenAI", "OpenAI - results", [result])
    return [home, results]


def transition(action, element, current_index):
    # Submitting the search (clicking the Search button) advances to results.
    if action == "click" and element is not None and element.role == "button":
        return 1
    return current_index


class FixedText:
    def complete(self, system, user):
        return '{"text": "OpenAI"}'


def verify_goal(observation, goal) -> bool:
    # Independent verification: results are visible (a result link present).
    return any(e.role == "link" for e in observation.elements)


def main() -> int:
    print("== Jev browser-agent proof of work — real observe→decide→act→verify ==\n")
    browser = FakeBrowserSession(build_pages(), transition=transition)
    jev = ScriptedJevClient([
        response("TYPE_TEXT", {"target_type": 0}),   # type the query into [0]
        response("CLICK", {"target_click": 1}),        # click Search [1]
        response("DONE"),                               # then done
    ])
    engine = DecisionEngine(jev)
    text = TextHelper(FixedText())

    events = []
    runtime = AgentRuntime(browser, engine, text_helper=text, on_event=events.append, sleep=lambda s: None)
    task = TaskContext(goal='Search for "OpenAI" and open the result', max_steps=15)

    result = runtime.run(task, verify_goal=verify_goal)

    print("goal:", task.goal)
    print("\nactivity:")
    for e in events:
        line = e.message or e.type.value
        print(f"  [{e.type.value}] {line}")
    print("\nbrowser actions issued:", browser.actions)
    print("final status:", result.status.value)

    ok = result.status.value == "success" and ("type", "OpenAI") in browser.actions
    print("\nPROOF OF WORK:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
