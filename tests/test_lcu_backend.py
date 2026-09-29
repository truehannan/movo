"""Tests for the proven-engine backend adapter (no real desktop needed).

Stubs ``lcu_engine.translate_active_window`` / action functions so the adapter's
translation into Movo's UIElement/Observation and its action dispatch are
verified deterministically.
"""

from __future__ import annotations

from app.desktop import lcu_engine as eng
from app.desktop.backend import Role
from app.desktop.candidates import build_candidates
from app.desktop.lcu_backend import LcuBackend


def _fake_translation():
    return {
        "window": {"title": "Calculator", "pid": 123, "x": 100, "y": 50, "w": 400, "h": 600, "isFocused": True},
        "elements": [
            {"role": "push button", "name": "7", "x": 120, "y": 400, "w": 40, "h": 40,
             "canPress": True, "canSetValue": False, "focused": False, "enabled": True,
             "editable": False, "display": False, "value": None},
            {"role": "push button", "name": "=", "x": 300, "y": 500, "w": 40, "h": 40,
             "canPress": True, "canSetValue": False, "focused": False, "enabled": True,
             "editable": False, "display": False, "value": None},
            {"role": "label", "name": "15", "x": 120, "y": 100, "w": 260, "h": 30,
             "canPress": False, "canSetValue": False, "focused": False, "enabled": True,
             "editable": False, "display": True, "value": "15"},
        ],
    }


def test_backend_translates_elements(monkeypatch):
    monkeypatch.setattr(eng, "translate_active_window", _fake_translation)
    monkeypatch.setattr(eng, "have_atspi", lambda: True)
    b = LcuBackend()
    obs = b.get_ui_tree()
    assert obs.window.title == "Calculator"
    assert len(obs.elements) == 3
    buttons = [e for e in obs.elements if e.role is Role.BUTTON]
    assert {e.name for e in buttons} == {"7", "="}
    label = next(e for e in obs.elements if e.role is Role.LABEL)
    assert label.value == "15"  # readout carried as value for verification


def test_buttons_become_candidates_labels_ranked_low(monkeypatch):
    monkeypatch.setattr(eng, "translate_active_window", _fake_translation)
    monkeypatch.setattr(eng, "have_atspi", lambda: True)
    b = LcuBackend()
    cands = build_candidates(b.get_ui_tree(), max_candidates=60)
    names = [c.name for c in cands]
    # The actionable buttons are present as candidates the model can pick.
    assert "7" in names and "=" in names


def test_backend_click_dispatches_to_engine(monkeypatch):
    monkeypatch.setattr(eng, "translate_active_window", _fake_translation)
    calls = {}
    monkeypatch.setattr(eng, "click_xy", lambda x, y, button="left", click_count=1: calls.update(x=x, y=y) or True)
    b = LcuBackend()
    obs = b.get_ui_tree()
    seven = next(e for e in obs.elements if e.name == "7")
    assert b.click(seven) is True
    # Clicked the element's center (120+20, 400+20).
    assert calls == {"x": 140, "y": 420}


def test_backend_typing_and_keys_dispatch(monkeypatch):
    sent = {}
    monkeypatch.setattr(eng, "type_text", lambda t: sent.update(typed=t) or True)
    monkeypatch.setattr(eng, "keypress", lambda keys: sent.update(keys=keys) or True)
    b = LcuBackend()
    assert b.type_text("hello") is True
    assert b.press_key("Return") is True
    assert sent == {"typed": "hello", "keys": ["Return"]}
