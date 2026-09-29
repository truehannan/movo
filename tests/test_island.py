"""Tests for the Dynamic Island window behaviour (offscreen).

Skipped when PySide6 is not installed (headless CI logic job).
"""

from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config.secrets import SecretStore  # noqa: E402
from app.config.settings import Settings  # noqa: E402
from app.desktop.backend import Observation, WindowInfo  # noqa: E402
from app.desktop.mock_backend import MockDesktopBackend  # noqa: E402
from app.diagnostics.capabilities import Capabilities  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_window(qapp, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", tempfile.mkdtemp())
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    from app.ui.window import MainWindow

    backend = MockDesktopBackend(screens=[Observation(window=WindowInfo())])
    w = MainWindow(backend, Settings(), SecretStore(prefer_keyring=False), Capabilities())
    w.show()
    qapp.processEvents()
    return w


def test_island_starts_retracted_at_top(qapp, monkeypatch):
    w = _make_window(qapp, monkeypatch)
    # Retracted position sits above the revealed position (higher on screen).
    assert w._retracted_y < w._revealed_y
    assert w._trigger.isVisible()
    w.close()


def test_reveal_and_retract_toggle(qapp, monkeypatch):
    w = _make_window(qapp, monkeypatch)
    w._reveal()
    qapp.processEvents()
    assert w._revealed is True
    w._retract()
    qapp.processEvents()
    assert w._revealed is False
    w.close()


def test_text_input_keeps_island_open(qapp, monkeypatch):
    w = _make_window(qapp, monkeypatch)
    w._reveal()
    w.panel.input.setText("open firefox")
    assert w._text_input_active() is True
    # A retract attempt must not retract while typing.
    w._maybe_retract()
    qapp.processEvents()
    assert w._revealed is True
    w.close()


def test_empty_input_allows_retract(qapp, monkeypatch):
    w = _make_window(qapp, monkeypatch)
    w._reveal()
    w.panel.input.clear()
    # Not typing, not running, pointer not over it (offscreen) -> retract.
    w._maybe_retract()
    qapp.processEvents()
    assert w._revealed is False
    w.close()


def test_window_is_non_movable(qapp, monkeypatch):
    w = _make_window(qapp, monkeypatch)
    before = w.pos()
    # The former drag handlers are no-ops now.
    w._bar_press(None)
    w._bar_move(None)
    qapp.processEvents()
    assert w.pos() == before
    w.close()
