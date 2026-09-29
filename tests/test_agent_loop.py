"""End-to-end agent loop tests with a mock backend and scripted Jev.

Proves the observe->decide->act->verify loop runs without a real desktop
(PROMPT section 25), including step limits, loop detection, emergency stop, and
the destructive-action confirmation gate.
"""

from __future__ import annotations

from app.agent.history import History
from app.agent.loop import AgentLoop, Outcome
from app.agent.planner import make_plan
from app.agent.verifier import fingerprint, verify
from app.config.settings import Settings
from app.desktop.backend import Observation, Role, WindowInfo
from app.desktop.mock_backend import MockDesktopBackend, el
from app.jev.client import DecisionEngine
from app.jev.schemas import Operation
from app.safety.confirmation import CallbackConfirmer
from app.safety.emergency_stop import EmergencyStop
from tests.mock_jev import ScriptedJevClient, make_response


def _screen(app: str, title: str, elements) -> Observation:
    return Observation(window=WindowInfo(app_name=app, title=title), elements=elements)


def _engine(responses) -> DecisionEngine:
    return DecisionEngine(ScriptedJevClient(responses), Settings().thresholds)


def _loop(backend, engine, **kw) -> AgentLoop:
    settings = kw.pop("settings", Settings())
    return AgentLoop(
        backend=backend,
        engine=engine,
        settings=settings,
        sleep=lambda s: None,  # no real waiting in tests
        **kw,
    )


def test_search_then_enter_then_done():
    """Demo-shaped task: TYPE into search, PRESS_KEY Return, then DONE."""
    home = _screen("firefox", "New Tab", [el("search", Role.TEXTBOX, "Search", editable=True, focused=True)])
    typed = _screen("firefox", "New Tab", [el("search", Role.TEXTBOX, "Search", value="python", editable=True, focused=True)])
    results = _screen("firefox", "python - Search", [el("r1", Role.LINK, "python.org")])

    def transition(action, arg, idx):
        if action == "type":
            return 1
        if action == "press_key":
            return 2
        return idx

    backend = MockDesktopBackend(screens=[home, typed, results], transition=transition)
    engine = _engine([
        make_response("TYPE", "NONE", cont=0.9),
        make_response("PRESS_KEY", "NONE", cont=0.9),
        make_response("DONE"),
    ])
    result = _loop(backend, engine).run(make_plan('Search for "python"'))

    assert result.outcome is Outcome.DONE
    assert ("type", "python") in backend.actions
    assert ("press_key", "Return") in backend.actions


def test_click_target_resolved_and_highlighted():
    home = _screen("gh", "GitHub", [el("issues", Role.LINK, "Issues", x=10, y=10)])
    issues = _screen("gh", "Issues · GitHub", [el("new", Role.BUTTON, "New issue")])

    backend = MockDesktopBackend(
        screens=[home, issues],
        transition=lambda a, arg, i: 1 if a == "click" else i,
    )
    engine = _engine([make_response("CLICK", "0", cont=0.2), make_response("DONE")])
    result = _loop(backend, engine).run(make_plan("Open GitHub Issues"))

    assert result.outcome is Outcome.DONE
    assert ("click", "issues") in backend.actions
    assert "issues" in backend.highlights


def test_max_steps_enforced():
    screen = _screen("app", "win", [el("b", Role.BUTTON, "Wiggle")])
    # Never changes state, always CLICK -> loop/step caps must stop it.
    backend = MockDesktopBackend(screens=[screen], transition=lambda a, arg, i: i)
    engine = _engine([make_response("CLICK", "0", cont=0.9)])
    settings = Settings(max_steps=4)
    result = _loop(backend, engine, settings=settings).run(make_plan("do stuff"))
    assert result.outcome in (Outcome.MAX_STEPS, Outcome.LOOP)
    assert result.steps <= 4


def test_loop_detection_stops_repeated_state():
    screen = _screen("app", "win", [el("b", Role.BUTTON, "Nop")])
    backend = MockDesktopBackend(screens=[screen], transition=lambda a, arg, i: i)
    engine = _engine([make_response("SCROLL", "NONE", cont=0.9)])
    result = _loop(backend, engine, settings=Settings(max_steps=20)).run(make_plan("scroll"))
    assert result.outcome is Outcome.LOOP


def test_emergency_stop():
    screen = _screen("app", "win", [el("b", Role.BUTTON, "Go")])
    backend = MockDesktopBackend(screens=[screen], transition=lambda a, arg, i: i)
    engine = _engine([make_response("CLICK", "0")])
    stop = EmergencyStop()
    stop.trigger()  # already engaged before the loop starts
    result = _loop(backend, engine, stop=stop).run(make_plan("go"))
    assert result.outcome is Outcome.STOPPED


def test_destructive_action_declined_blocks():
    home = _screen("files", "Files", [el("del", Role.BUTTON, "Delete")])
    backend = MockDesktopBackend(screens=[home], transition=lambda a, arg, i: i)
    # Jev even says unsafe; confirmer declines.
    engine = _engine([make_response("CLICK", "0", safe=0.1)])
    declined = CallbackConfirmer(lambda desc, reason: False)
    result = _loop(backend, engine, confirmer=declined).run(make_plan("clean up"))
    assert result.outcome is Outcome.BLOCKED
    assert ("click", "del") not in backend.actions


def test_destructive_action_confirmed_proceeds():
    home = _screen("files", "Files", [el("del", Role.BUTTON, "Delete")])
    done = _screen("files", "Files (empty)", [])

    backend = MockDesktopBackend(
        screens=[home, done], transition=lambda a, arg, i: 1 if a == "click" else i
    )
    engine = _engine([make_response("CLICK", "0", safe=0.1, cont=0.1), make_response("DONE")])
    approved = CallbackConfirmer(lambda desc, reason: True)
    _loop(backend, engine, confirmer=approved).run(make_plan("delete it"))
    assert ("click", "del") in backend.actions


# --- history / verifier unit tests ------------------------------------------

def test_history_repeated_action_detected():
    h = History(loop_threshold=3)
    for i in range(3):
        h.add(i, "CLICK → Nop", verified=False)
    assert h.repeated_action()
    assert h.is_looping()


def test_history_recent_lines_bounded():
    h = History()
    for i in range(10):
        h.add(i, f"CLICK → B{i}", verified=True)
    assert len(h.recent_lines(5)) == 5


def test_verifier_detects_no_change():
    a = _screen("app", "win", [el("b", Role.BUTTON, "Go")])
    res = verify(Operation.CLICK, a, a)
    assert not res.verified


def test_verifier_detects_change():
    a = _screen("app", "win1", [el("b", Role.BUTTON, "Go")])
    b = _screen("app", "win2", [el("c", Role.LINK, "Next")])
    assert verify(Operation.CLICK, a, b).verified


def test_verifier_type_checks_focused_value():
    before = _screen("app", "win", [el("t", Role.TEXTBOX, "Search", editable=True, focused=True)])
    after = _screen("app", "win", [el("t", Role.TEXTBOX, "Search", value="python", editable=True, focused=True)])
    assert verify(Operation.TYPE, before, after, typed_text="python").verified


def test_fingerprint_stable():
    a = _screen("app", "win", [el("b", Role.BUTTON, "Go")])
    b = _screen("app", "win", [el("b", Role.BUTTON, "Go")])
    assert fingerprint(a) == fingerprint(b)
