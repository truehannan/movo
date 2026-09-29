"""Tests for candidate filtering and serialization (PROMPT sections 8, 25)."""

from __future__ import annotations

from app.desktop.backend import Bounds, Observation, Role, UIElement, WindowInfo
from app.desktop.candidates import (
    DEFAULT_MAX_CANDIDATES,
    build_candidates,
    serialize_candidates,
)


def _obs(elements: list[UIElement]) -> Observation:
    return Observation(window=WindowInfo(app_name="Test", title="Win"), elements=elements)


def _el(**kw) -> UIElement:
    base = dict(
        node_id="n",
        role=Role.BUTTON,
        name="",
        bounds=Bounds(0, 0, 100, 30),
        enabled=True,
        visible=True,
        actionable=True,
    )
    base.update(kw)
    return UIElement(**base)


def test_invisible_and_disabled_are_filtered():
    els = [
        _el(node_id="a", name="Visible"),
        _el(node_id="b", name="Hidden", visible=False),
        _el(node_id="c", name="Disabled", enabled=False),
    ]
    cands = build_candidates(_obs(els))
    names = {c.name for c in cands}
    assert names == {"Visible"}


def test_zero_area_decorative_filtered():
    els = [
        _el(node_id="a", name="Real"),
        _el(node_id="b", name="", bounds=Bounds(0, 0, 1, 1), actionable=False),
    ]
    cands = build_candidates(_obs(els))
    assert len(cands) == 1
    assert cands[0].name == "Real"


def test_duplicates_removed():
    els = [
        _el(node_id="a", name="Save"),
        _el(node_id="b", name="Save"),
        _el(node_id="c", name="Cancel"),
    ]
    cands = build_candidates(_obs(els))
    assert len(cands) == 2


def test_candidate_ids_are_sequential():
    els = [_el(node_id=str(i), name=f"B{i}") for i in range(5)]
    cands = build_candidates(_obs(els))
    assert [c.id for c in cands] == [0, 1, 2, 3, 4]


def test_max_candidates_capped():
    els = [_el(node_id=str(i), name=f"B{i}", bounds=Bounds(0, i, 100, 30)) for i in range(40)]
    cands = build_candidates(_obs(els))
    assert len(cands) <= DEFAULT_MAX_CANDIDATES


def test_focused_element_ranked_first():
    els = [
        _el(node_id="a", name="Later", bounds=Bounds(0, 0, 500, 400)),
        _el(node_id="b", name="Focused", focused=True, bounds=Bounds(0, 0, 10, 10)),
    ]
    cands = build_candidates(_obs(els))
    assert cands[0].name == "Focused"


def test_serialization_format():
    els = [
        _el(node_id="a", role=Role.BUTTON, name="New issue"),
        _el(node_id="b", role=Role.TEXTBOX, name="Search", value="", editable=True),
    ]
    cands = build_candidates(_obs(els))
    text = serialize_candidates(cands)
    assert "role=button" in text
    assert 'name="New issue"' in text
    assert 'value=""' in text
    # One line per candidate.
    assert len(text.splitlines()) == len(cands)


def test_empty_candidates_serialization():
    assert "no actionable" in serialize_candidates([])
