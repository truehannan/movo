"""Unit tests for the agent core (PROMPT §36)."""

from __future__ import annotations

from agent.browser.browser import FakeBrowserSession
from agent.browser.execution import Executor
from agent.core.actions import Operation
from agent.core.agent import AgentRuntime
from agent.core.safety import ActionPolicy, SafetyPolicy
from agent.core.state import Element, Observation
from agent.core.task import TaskContext, TaskStatus
from agent.core.verification import is_stale, verify_step
from agent.model.jev import DecisionEngine, build_questions
from agent.model.text import TextHelper, _validate
from tests.mock_jev import ScriptedJevClient, response


# --- decision parsing + dynamic action space -------------------------------
def _obs():
    return Observation(
        url="u", title="t", fingerprint="fp0",
        elements=[
            Element(index=0, role="textbox", name="Search", editable=True, can_type=True),
            Element(index=1, role="button", name="Go", can_click=True),
            Element(index=2, role="combobox", name="Sort", can_select=True, options=["A", "B"]),
        ],
    )


def test_dynamic_targets_only_relevant_operations():
    q = build_questions(_obs())
    assert set(q) == {"operation", "target_click", "target_type", "target_select"}
    # type targets contain only the textbox index
    assert "0" in q["target_type"].criteria
    assert "1" not in q["target_type"].criteria


def test_decision_click_resolves_target():
    eng = DecisionEngine(ScriptedJevClient([response("CLICK", {"target_click": 1})]))
    d = eng.decide("goal", _obs())
    assert d.operation is Operation.CLICK and d.target_index == 1


def test_decision_type_resolves_target():
    eng = DecisionEngine(ScriptedJevClient([response("TYPE_TEXT", {"target_type": 0})]))
    d = eng.decide("goal", _obs())
    assert d.operation is Operation.TYPE_TEXT and d.target_index == 0


def test_invalid_operation_falls_back_to_blocked():
    eng = DecisionEngine(ScriptedJevClient([response("FLY")]))
    assert eng.decide("g", _obs()).operation is Operation.BLOCKED


def test_out_of_range_target_dropped():
    eng = DecisionEngine(ScriptedJevClient([response("CLICK", {"target_click": 99})]))
    d = eng.decide("g", _obs())
    assert d.operation is Operation.CLICK and d.target_index is None


# --- stale / freshness ------------------------------------------------------
def test_stale_when_fingerprint_changes():
    before = Observation(fingerprint="a", elements=[Element(index=0, role="button", name="X", can_click=True)])
    after = Observation(fingerprint="b", elements=[Element(index=0, role="button", name="X", can_click=True)])
    assert is_stale(before, after, 0) is True


def test_not_stale_when_identical():
    els = [Element(index=0, role="button", name="X", can_click=True)]
    a = Observation(fingerprint="a", elements=els)
    b = Observation(fingerprint="a", elements=list(els))
    assert is_stale(a, b, 0) is False


def test_stale_when_target_changes_identity():
    a = Observation(fingerprint="a", elements=[Element(index=0, role="button", name="Save", can_click=True)])
    b = Observation(fingerprint="a", elements=[Element(index=0, role="button", name="Delete", can_click=True)])
    assert is_stale(a, b, 0) is True


# --- safety -----------------------------------------------------------------
def test_safety_plain_click_auto():
    assert SafetyPolicy().classify(Operation.CLICK, "Search").auto


def test_safety_purchase_confirms():
    v = SafetyPolicy().classify(Operation.CLICK, "Buy now")
    assert v.needs_confirmation


def test_safety_override_block():
    pol = SafetyPolicy(overrides={"delete": ActionPolicy.BLOCKED})
    assert pol.classify(Operation.CLICK, "Delete account").blocked


# --- verification -----------------------------------------------------------
def test_verify_click_no_change_fails():
    a = Observation(fingerprint="x", elements=[])
    assert not verify_step(Operation.CLICK, a, a)


def test_verify_type_present():
    before = Observation(fingerprint="x", elements=[Element(index=0, role="textbox", name="q", can_type=True)])
    after = Observation(fingerprint="y", elements=[Element(index=0, role="textbox", name="q", value="hello", can_type=True)])
    assert verify_step(Operation.TYPE_TEXT, before, after, typed_text="hello")


# --- text helper validation -------------------------------------------------
def test_text_validate_extracts_string():
    assert _validate('{"text": "hello"}') == "hello"


def test_text_validate_rejects_non_string_and_null():
    assert _validate('{"text": null}') is None
    assert _validate('{"text": 42}') is None
    assert _validate("not json") is None
    assert _validate('{"other": "x"}') is None


def test_text_validate_strips_fence():
    assert _validate('```json\n{"text": "abc"}\n```') == "abc"


def test_text_helper_uses_client():
    class C:
        def complete(self, s, u):
            return '{"text": "wireless headphones"}'

    assert TextHelper(C()).value_for("g", "Search", "u") == "wireless headphones"


# --- executor stale rejection ----------------------------------------------
def test_executor_rejects_stale_target():
    els = [Element(index=0, role="button", name="Go", can_click=True)]
    # Browser observes a DIFFERENT fingerprint than the decision was made on.
    browser = FakeBrowserSession([("u", "t", els)])
    ex = Executor(browser)
    from agent.core.actions import Decision

    decided_on = Observation(fingerprint="OLD", elements=list(els))
    res = ex.execute(Decision(operation=Operation.CLICK, target_index=0), decided_on)
    assert res.stale is True and res.ok is False


# --- task limits ------------------------------------------------------------
def test_task_over_budget_steps():
    t = TaskContext(goal="g", max_steps=2)
    t.step_count = 2
    assert t.over_budget() == "max steps reached"


def test_task_status_terminal():
    assert TaskStatus.SUCCESS.is_terminal
    assert not TaskStatus.RUNNING.is_terminal


# --- loop: stop prevents further mutation -----------------------------------
def test_stop_prevents_actions():
    els = [Element(index=0, role="button", name="Go", can_click=True)]
    browser = FakeBrowserSession([("u", "t", els)])
    eng = DecisionEngine(ScriptedJevClient([response("CLICK", {"target_click": 0})]))
    rt = AgentRuntime(browser, eng, sleep=lambda s: None)
    rt.stop()  # stop before running
    task = rt.run(TaskContext(goal="g"))
    assert task.status is TaskStatus.STOPPED
    assert browser.actions == []
