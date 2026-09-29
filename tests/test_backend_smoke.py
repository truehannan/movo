"""Smoke tests for the real backend wiring and the app entry point.

These do not require a live display or AT-SPI: they exercise the defensive
construction and graceful-degrade paths that the deterministic suite otherwise
skips, so import/wiring regressions in ``x11_backend`` and ``main`` are caught.
"""

from __future__ import annotations

from app.desktop.backend import Bounds, Role, UIElement


def _stub_element() -> UIElement:
    return UIElement(node_id="n", role=Role.BUTTON, name="Go", bounds=Bounds(0, 0, 40, 20))


def test_x11_backend_constructs_and_degrades(monkeypatch):
    """The backend must construct even when every optional dep is missing."""
    import app.desktop.x11_backend as x

    # Force all optional deps to appear unavailable.
    monkeypatch.setattr(x.X11DesktopBackend, "_init_atspi", staticmethod(lambda: None))
    monkeypatch.setattr(x.X11DesktopBackend, "_init_input", staticmethod(lambda: (None, None)))
    monkeypatch.setattr(x.X11DesktopBackend, "_init_mss", staticmethod(lambda: None))

    backend = x.X11DesktopBackend()

    # With no AT-SPI, an observation still returns a well-formed object.
    obs = backend.get_ui_tree()
    assert obs.accessibility_ok is False
    assert obs.elements == []

    # Actions fail cleanly (return False) rather than raising.
    assert backend.click(_stub_element()) is False
    assert backend.type_text("hi") is False
    assert backend.press_key("Return") is False
    assert backend.scroll(0, 100) is False
    backend.close()


def test_x11_role_mapping():
    from app.desktop.x11_backend import _map_role

    assert _map_role("push button") is Role.BUTTON
    assert _map_role("entry") is Role.TEXTBOX
    assert _map_role("page tab") is Role.TAB
    assert _map_role("totally unknown role") is Role.OTHER


def test_x11_press_key_parses_combo(monkeypatch):
    """press_key should split a combo and drive the xdotool fallback."""
    import app.desktop.x11_backend as x

    monkeypatch.setattr(x.X11DesktopBackend, "_init_atspi", staticmethod(lambda: None))
    monkeypatch.setattr(x.X11DesktopBackend, "_init_input", staticmethod(lambda: (None, None)))
    monkeypatch.setattr(x.X11DesktopBackend, "_init_mss", staticmethod(lambda: None))
    backend = x.X11DesktopBackend()

    calls = {}

    def fake_run(args, **kw):
        calls["args"] = args

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(x.subprocess, "run", fake_run)
    assert backend.press_key("ctrl+l") is True
    assert calls["args"] == ["xdotool", "key", "ctrl+l"]


def test_main_build_backend_returns_a_backend(monkeypatch):
    """_build_backend must always return a usable DesktopBackend."""
    # Force the X11 backend import to fail so the null fallback path runs.
    import app.desktop.x11_backend as x
    from app import main
    from app.desktop.backend import DesktopBackend

    def boom():
        raise RuntimeError("no display")

    monkeypatch.setattr(x, "X11DesktopBackend", boom)
    backend = main._build_backend()
    assert isinstance(backend, DesktopBackend)
    # The null backend degrades safely.
    obs = backend.get_ui_tree()
    assert obs.accessibility_ok is False
    assert backend.type_text("x") is False


def test_capabilities_check_runs():
    from app.diagnostics.capabilities import check_capabilities

    caps = check_capabilities()
    # Every field is populated with a bool/str and the summary helpers work.
    assert isinstance(caps.session_type, str)
    rows = caps.as_rows()
    assert len(rows) == 5
    assert all(isinstance(ok, bool) for _, ok in rows)


def test_logging_redacts_secrets(capsys):
    import logging

    from app.diagnostics.logging import configure_logging

    logger = configure_logging(debug=True)
    logger.info("using key sk-abcdef1234567890 now")
    logger.handlers[0].flush()
    err = capsys.readouterr().err
    assert "sk-abcdef1234567890" not in err
    assert "****" in err
    logging.getLogger("jev").handlers.clear()
