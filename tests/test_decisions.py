"""Tests for Jev decision parsing (PROMPT sections 9, 25)."""

from __future__ import annotations

from app.config.settings import ConfidenceThresholds
from app.desktop.backend import Bounds, Role, UIElement
from app.desktop.candidates import Candidate
from app.jev.client import DecisionEngine
from app.jev.schemas import Operation
from tests.mock_jev import ScriptedJevClient, make_response


def _cands(n: int = 3) -> list[Candidate]:
    out = []
    for i in range(n):
        el = UIElement(node_id=str(i), role=Role.BUTTON, name=f"B{i}", bounds=Bounds(0, 0, 10, 10))
        out.append(Candidate(id=i, role=Role.BUTTON, name=f"B{i}", value=None, enabled=True, element=el))
    return out


def _engine(resp) -> DecisionEngine:
    return DecisionEngine(ScriptedJevClient([resp]), ConfidenceThresholds())


def _decide(engine, cands):
    return engine.decide("goal", "App", "Win", cands)


def test_click_with_target():
    d = _decide(_engine(make_response("CLICK", "1")), _cands())
    assert d.operation is Operation.CLICK
    assert d.target_id == 1


def test_type_has_no_target():
    d = _decide(_engine(make_response("TYPE", "NONE")), _cands())
    assert d.operation is Operation.TYPE
    assert d.target_id is None


def test_done_is_terminal():
    d = _decide(_engine(make_response("DONE")), _cands())
    assert d.operation is Operation.DONE
    assert d.operation.is_terminal


def test_invalid_operation_falls_back_to_blocked():
    d = _decide(_engine(make_response("FLY")), _cands())
    assert d.operation is Operation.BLOCKED


def test_target_out_of_range_is_dropped():
    d = _decide(_engine(make_response("CLICK", "99")), _cands())
    assert d.operation is Operation.CLICK
    assert d.target_id is None


def test_noul_threshold_controls_continue_and_safe():
    resp = make_response("CLICK", "0", cont=0.9, safe=0.2)
    d = _decide(_engine(resp), _cands())
    assert d.should_continue is True
    assert d.safe is False


def test_confidence_and_telemetry_populated():
    d = _decide(_engine(make_response("CLICK", "0", op_conf=0.83)), _cands())
    assert abs(d.confidence - 0.83) < 1e-6
    assert d.model == "jev-1.13.0"
    assert d.input_tokens == 120
