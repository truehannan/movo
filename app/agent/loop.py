"""The agent loop: observe -> decide -> act -> verify (PROMPT sections 6, 14, 21).

This module owns the workflow and all side effects. Jev supplies bounded typed
decisions via :class:`~app.jev.client.DecisionEngine`; everything else — action
execution, verification, retries, loop detection, safety gating, emergency
stop, and step/timeout limits — is deterministic application code.

The loop is UI-agnostic: it reports progress through an ``on_event`` callback
so the PySide6 window (or a test) can render it. It never imports Qt.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from app.agent.history import History
from app.agent.planner import Plan, resolve_text_argument
from app.agent.verifier import fingerprint, verify
from app.config.settings import Settings
from app.desktop.backend import DesktopBackend
from app.desktop.candidates import build_candidates
from app.jev.client import DecisionEngine
from app.jev.schemas import Decision, Operation
from app.safety import policy
from app.safety.confirmation import AutoDenyConfirmer, Confirmer
from app.safety.emergency_stop import EmergencyStop, EmergencyStopped


class Outcome(str, Enum):
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"  # emergency stop
    TIMEOUT = "TIMEOUT"
    MAX_STEPS = "MAX_STEPS"
    LOOP = "LOOP"
    ERROR = "ERROR"


class EventType(str, Enum):
    OBSERVED = "observed"
    DECIDED = "decided"
    ACTING = "acting"
    VERIFIED = "verified"
    RETRY = "retry"
    CONFIRM = "confirm"
    FINISHED = "finished"
    INFO = "info"


@dataclass
class AgentEvent:
    type: EventType
    step: int
    message: str
    decision: Decision | None = None
    app_name: str = ""
    target_label: str = ""
    verified: bool | None = None


@dataclass
class TaskResult:
    outcome: Outcome
    steps: int
    history: History
    detail: str = ""
    telemetry: dict = field(default_factory=dict)


EventCallback = Callable[[AgentEvent], None]


class AgentLoop:
    """Runs one goal to completion, retry, recovery, or a bounded stop."""

    def __init__(
        self,
        backend: DesktopBackend,
        engine: DecisionEngine,
        settings: Settings,
        stop: EmergencyStop | None = None,
        confirmer: Confirmer | None = None,
        on_event: EventCallback | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._engine = engine
        self._settings = settings
        self._stop = stop or EmergencyStop()
        self._confirmer = confirmer or AutoDenyConfirmer()
        self._on_event = on_event or (lambda e: None)
        self._sleep = sleep
        self._now = now

    def _emit(self, event: AgentEvent) -> None:
        self._on_event(event)

    def run(self, plan: Plan) -> TaskResult:
        history = History(loop_threshold=3)
        telemetry = {"jev_calls": 0, "input_tokens": 0, "actions_ok": 0, "actions_failed": 0}
        deadline = self._now() + self._settings.task_timeout_s
        last_verification: str | None = None
        step = 0

        try:
            while step < self._settings.max_steps:
                self._stop.raise_if_triggered()
                if self._now() > deadline:
                    return self._finish(Outcome.TIMEOUT, step, history, telemetry, "task timeout")

                # --- OBSERVE ---
                before = self._backend.get_ui_tree()
                history.observe_state(fingerprint(before))
                candidates = build_candidates(before)
                self._emit(
                    AgentEvent(
                        EventType.OBSERVED,
                        step,
                        before.summary(),
                        app_name=before.window.app_name,
                    )
                )

                if history.is_looping():
                    return self._finish(Outcome.LOOP, step, history, telemetry, "loop detected")

                # --- DECIDE ---
                decision = self._engine.decide(
                    goal=plan.goal,
                    app_name=before.window.app_name,
                    window_title=before.window.title,
                    candidates=candidates,
                    recent_history=history.recent_lines(),
                    last_verification=last_verification,
                )
                telemetry["jev_calls"] += 1
                telemetry["input_tokens"] += decision.input_tokens

                target = next(
                    (c for c in candidates if c.id == decision.target_id), None
                )
                target_label = target.name if target else ""
                # Derive text/key argument deterministically (not from Jev).
                if decision.operation.needs_text:
                    decision.text = resolve_text_argument(
                        decision.operation, plan, target_label
                    )

                self._emit(
                    AgentEvent(
                        EventType.DECIDED,
                        step,
                        decision.describe(),
                        decision=decision,
                        app_name=before.window.app_name,
                        target_label=target_label,
                    )
                )

                # --- terminal operations ---
                if decision.operation is Operation.DONE:
                    return self._finish(Outcome.DONE, step, history, telemetry, "goal complete")
                if decision.operation is Operation.BLOCKED:
                    return self._finish(Outcome.BLOCKED, step, history, telemetry, "blocked by Jev")

                # --- confidence gate (PROMPT section 34) ---
                if decision.confidence < self._settings.thresholds.low:
                    history.add(step, decision.describe(), verified=False, note="low-confidence, reobserve")
                    self._emit(AgentEvent(EventType.INFO, step, "low confidence, reobserving"))
                    self._sleep(0.3)
                    step += 1
                    continue

                # --- safety gate (PROMPT section 21) ---
                verdict = policy.classify(decision.operation, target_label, decision.text)
                if not decision.safe or not verdict.allowed:
                    reason = verdict.reason or "flagged unsafe by decision model"
                    if self._settings.confirmation_mode:
                        self._emit(AgentEvent(EventType.CONFIRM, step, reason, decision=decision))
                        if not self._confirmer.confirm(decision.describe(), reason):
                            return self._finish(
                                Outcome.BLOCKED, step, history, telemetry,
                                f"declined: {reason}",
                            )
                    elif verdict.destructive:
                        return self._finish(
                            Outcome.BLOCKED, step, history, telemetry,
                            f"destructive action blocked: {reason}",
                        )

                # --- ACT (with retries) ---
                self._stop.raise_if_triggered()
                if decision.operation.needs_target:
                    if target is not None:
                        self._backend.highlight(target.element)
                self._emit(
                    AgentEvent(
                        EventType.ACTING, step, decision.describe(),
                        decision=decision, target_label=target_label,
                    )
                )
                ok = self._execute(decision, target)

                # --- VERIFY ---
                after = self._backend.get_ui_tree()
                result = verify(decision.operation, before, after, decision.text)
                verified = ok and result.verified
                last_verification = result.summary
                if verified:
                    telemetry["actions_ok"] += 1
                else:
                    telemetry["actions_failed"] += 1

                history.add(step, decision.describe(), verified, note=result.summary)
                self._emit(
                    AgentEvent(
                        EventType.VERIFIED, step, result.summary,
                        decision=decision, verified=verified,
                    )
                )

                # --- RETRY on failure ---
                if not verified:
                    self._emit(AgentEvent(EventType.RETRY, step, "action not verified"))

                if not decision.should_continue and verified:
                    return self._finish(Outcome.DONE, step, history, telemetry, "continuation says complete")

                step += 1

            return self._finish(Outcome.MAX_STEPS, step, history, telemetry, "max steps reached")

        except EmergencyStopped:
            return self._finish(Outcome.STOPPED, step, history, telemetry, "emergency stop")
        except Exception as exc:  # defensive: never crash the UI thread
            return self._finish(Outcome.ERROR, step, history, telemetry, f"{type(exc).__name__}: {exc}")

    def _execute(self, decision: Decision, target) -> bool:
        op = decision.operation
        retries = self._settings.max_retries_per_action
        attempt = 0
        while attempt <= retries:
            self._stop.raise_if_triggered()
            try:
                if op is Operation.CLICK and target is not None:
                    if self._backend.click(target.element):
                        return True
                elif op is Operation.DOUBLE_CLICK and target is not None:
                    if self._backend.click(target.element, double=True):
                        return True
                elif op is Operation.RIGHT_CLICK and target is not None:
                    if self._backend.click(target.element, button="right"):
                        return True
                elif op is Operation.TYPE and decision.text is not None:
                    if self._backend.type_text(decision.text):
                        return True
                elif op is Operation.PRESS_KEY and decision.text is not None:
                    if self._backend.press_key(decision.text):
                        return True
                elif op is Operation.SCROLL:
                    if self._backend.scroll(0, 400):
                        return True
                elif op is Operation.WAIT:
                    self._sleep(0.6)
                    return True
                elif op is Operation.DRAG and target is not None:
                    # Single-target drag is a no-op without a source; treat as failed.
                    return False
                else:
                    return False
            except Exception:
                pass
            attempt += 1
            if attempt <= retries:
                self._sleep(0.3)
        return False

    def _finish(
        self, outcome: Outcome, step: int, history: History, telemetry: dict, detail: str
    ) -> TaskResult:
        self._emit(AgentEvent(EventType.FINISHED, step, f"{outcome.value}: {detail}"))
        return TaskResult(outcome=outcome, steps=step, history=history, detail=detail, telemetry=telemetry)
