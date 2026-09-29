"""Integration smoke test: drive the real MainWindow + TaskController + AgentLoop
with a mock backend and a scripted Jev client, offscreen.

This is skipped automatically if PySide6 is not installed (e.g. on the headless
CI logic job), so it never breaks the core test run.
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
from app.desktop.backend import Observation, Role, WindowInfo  # noqa: E402
from app.desktop.mock_backend import MockDesktopBackend, el  # noqa: E402
from app.diagnostics.capabilities import Capabilities  # noqa: E402
from app.jev.client import DecisionEngine  # noqa: E402
from tests.mock_jev import ScriptedJevClient, make_response  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _screen(app, title, elements):
    return Observation(window=WindowInfo(app_name=app, title=title), elements=elements)


def test_window_runs_a_task_end_to_end(qapp, monkeypatch):
    from app.ui.window import MainWindow

    monkeypatch.setenv("XDG_CONFIG_HOME", tempfile.mkdtemp())
    secrets = SecretStore(prefer_keyring=False)
    secrets.set_api_key("sk-test-000000")

    home = _screen("firefox", "New Tab", [el("s", Role.TEXTBOX, "Search", editable=True, focused=True)])
    done = _screen("firefox", "python - Search", [el("r", Role.LINK, "python.org")])
    backend = MockDesktopBackend(
        screens=[home, done], transition=lambda a, arg, i: 1 if a == "type" else i
    )

    window = MainWindow(backend, Settings(max_steps=5), secrets, Capabilities(accessibility=True))

    # Inject a scripted Jev client so no network is used.
    scripted = ScriptedJevClient([make_response("TYPE", "NONE", cont=0.1), make_response("DONE")])
    window._controller._client = _FakeJevClient(scripted, window._controller._settings.thresholds)

    finished = {}
    orig = window._handle_finished
    def capture(result):
        finished["result"] = result
        orig(result)
    window._finished_signal.disconnect()
    window._finished_signal.connect(capture)

    window._on_run('Search for "python"')

    # Pump the event loop until the worker thread finishes.
    import time
    deadline = time.time() + 5
    while "result" not in finished and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)

    assert "result" in finished, "task did not finish"
    assert ("type", "python") in backend.actions
    window.close()


class _FakeJevClient:
    """Wraps a scripted client so build_client() is bypassed but engine works."""

    def __init__(self, scripted, thresholds):
        self._engine = DecisionEngine(scripted, thresholds)
        self._scripted = scripted

    # TaskController uses DecisionEngine(client, ...); but here we pre-set
    # _client and the worker builds engine = DecisionEngine(client, ...).
    def system_one(self, state, questions):
        return self._scripted.system_one(state, questions)

    def close(self):
        pass
