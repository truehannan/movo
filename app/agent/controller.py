"""Task controller (PROMPT section 3).

Wires configuration, secrets, the desktop backend, the Jev engine, and the
agent loop together, and runs a goal on a background thread so the UI stays
responsive. The controller is the single seam the UI talks to.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.agent.loop import AgentEvent, AgentLoop, TaskResult
from app.agent.planner import make_plan
from app.config.secrets import SecretStore
from app.config.settings import Settings
from app.desktop.backend import DesktopBackend
from app.diagnostics.logging import get_logger
from app.jev.client import DecisionEngine, JevClient
from app.safety.confirmation import Confirmer
from app.safety.emergency_stop import EmergencyStop

_log = get_logger()


class TaskController:
    """Owns long-lived agent resources and drives one task at a time."""

    def __init__(
        self,
        backend: DesktopBackend,
        settings: Settings,
        secrets: SecretStore,
        stop: EmergencyStop,
        confirmer: Confirmer | None = None,
    ) -> None:
        self._backend = backend
        self._settings = settings
        self._secrets = secrets
        self._stop = stop
        self._confirmer = confirmer
        self._thread: threading.Thread | None = None
        self._client: JevClient | None = None

    # --- connection ------------------------------------------------------
    def build_client(self) -> JevClient:
        key = self._secrets.get_api_key()
        if not key:
            raise RuntimeError("No API key configured")
        self._client = JevClient(key, model=self._settings.model)
        return self._client

    def test_connection(self):
        return self.build_client().test_connection()

    # --- running ---------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run_goal(
        self,
        goal: str,
        on_event: Callable[[AgentEvent], None],
        on_finished: Callable[[TaskResult], None],
    ) -> None:
        if self.running:
            raise RuntimeError("A task is already running")
        self._stop.reset()

        def worker() -> None:
            try:
                client = self._client or self.build_client()
                engine = DecisionEngine(client, self._settings.thresholds)
                loop = AgentLoop(
                    backend=self._backend,
                    engine=engine,
                    settings=self._settings,
                    stop=self._stop,
                    confirmer=self._confirmer,
                    on_event=on_event,
                )
                plan = make_plan(goal)
                _log.info("Running goal (%d chars)", len(goal))
                result = loop.run(plan)
            except Exception as exc:  # pragma: no cover - defensive
                from app.agent.history import History
                from app.agent.loop import Outcome

                result = TaskResult(Outcome.ERROR, 0, History(), f"{type(exc).__name__}: {exc}")
            on_finished(result)

        self._thread = threading.Thread(target=worker, name="jev-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.trigger()

    def shutdown(self) -> None:
        self.stop()
        if self._client is not None:
            self._client.close()
        self._backend.close()
