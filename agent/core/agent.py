"""The agent runtime loop (PROMPT §1, §13-§18).

observe → decide (Jev: one operation + target) → text (helper, only for
TYPE_TEXT) → safety gate → guarded execute (stale-checked) → verify → repeat.

The goal is held in :class:`TaskContext`, never re-sent wholesale to Jev — each
cycle gives Jev only the current page's indexed elements and a short recent
action list. Stop/pause are honoured between and before every action; step,
runtime and failure limits bound the run; ``DONE`` is verified independently.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from agent.browser.browser import BrowserSession
from agent.browser.execution import Executor
from agent.core.actions import Operation
from agent.core.events import AgentEvent, EventType
from agent.core.safety import SafetyPolicy
from agent.core.state import Observation
from agent.core.task import TaskContext, TaskStatus
from agent.core.verification import verify_step
from agent.model.jev import DecisionEngine
from agent.model.text import TextHelper

EventSink = Callable[[AgentEvent], None]
Confirmer = Callable[[str, str], bool]  # (description, reason) -> approved


class AgentRuntime:
    """Runs one task to a terminal state. UI-agnostic (emits events)."""

    def __init__(
        self,
        browser: BrowserSession,
        engine: DecisionEngine,
        text_helper: TextHelper | None = None,
        safety: SafetyPolicy | None = None,
        on_event: EventSink | None = None,
        confirmer: Confirmer | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._browser = browser
        self._engine = engine
        self._text = text_helper
        self._safety = safety or SafetyPolicy()
        self._executor = Executor(browser)
        self._on_event = on_event or (lambda e: None)
        self._confirmer = confirmer or (lambda d, r: False)
        self._sleep = sleep
        self._stop = threading.Event()
        self._pause = threading.Event()

    # --- controls --------------------------------------------------------
    def stop(self) -> None:
        self._stop.set()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    # --- helpers ---------------------------------------------------------
    def _emit(self, task: TaskContext, etype: EventType, **kw) -> None:
        self._on_event(AgentEvent(type=etype, task_id=task.id, step=task.step_count, **kw))

    def _set_status(self, task: TaskContext, status: TaskStatus, message: str = "") -> None:
        task.status = status
        self._emit(task, EventType.STATUS, status=status.value, message=message)

    def _wait_while_paused(self) -> None:
        while self._pause.is_set() and not self._stop.is_set():
            self._sleep(0.1)

    # --- main loop -------------------------------------------------------
    def run(self, task: TaskContext, verify_goal: Callable[[Observation, str], bool] | None = None) -> TaskContext:
        self._set_status(task, TaskStatus.RUNNING, "Starting")
        recent: list[str] = []
        try:
            while True:
                if self._stop.is_set():
                    self._set_status(task, TaskStatus.STOPPED, "Stopped by user")
                    break
                self._wait_while_paused()
                if self._stop.is_set():
                    self._set_status(task, TaskStatus.STOPPED, "Stopped by user")
                    break

                reason = task.over_budget()
                if reason:
                    self._set_status(task, TaskStatus.BLOCKED, reason)
                    break

                # OBSERVE
                self._set_status(task, TaskStatus.THINKING, "Reading page")
                observation = self._browser.observe()
                task.browser.url = observation.url
                task.browser.title = observation.title
                self._emit(task, EventType.OBSERVED, message=observation.summary())

                # DECIDE (one Jev call: operation + target)
                decision = self._engine.decide(task.goal, observation, recent)

                # TYPE_TEXT: fill the value via the separate helper (not Jev).
                if decision.operation is Operation.TYPE_TEXT and decision.target_index is not None:
                    target = observation.by_index(decision.target_index)
                    decision.text = self._resolve_text(task, target.short() if target else "", observation.url, recent)
                    if not decision.text:
                        self._emit(task, EventType.MESSAGE, message="No value available for field; re-observing")
                        task.consecutive_failures += 1
                        task.step_count += 1
                        continue

                target_el = observation.by_index(decision.target_index)
                target_label = target_el.short() if target_el else ""
                self._emit(
                    task, EventType.DECISION,
                    operation=decision.operation.value,
                    target=target_label or None,
                    message=decision.describe(),
                )

                # Terminal operations
                if decision.operation is Operation.DONE:
                    if verify_goal is not None and not verify_goal(self._browser.observe(), task.goal):
                        self._emit(task, EventType.VERIFIED, verified=False, message="DONE not verified; continuing")
                        recent.append("DONE (unverified)")
                        task.step_count += 1
                        continue
                    self._set_status(task, TaskStatus.SUCCESS, "Task completed")
                    self._emit(task, EventType.COMPLETED, outcome="success", verified=True)
                    break
                if decision.operation is Operation.BLOCKED:
                    self._set_status(task, TaskStatus.BLOCKED, "No supported action can make progress")
                    self._emit(task, EventType.COMPLETED, outcome="blocked")
                    break

                # SAFETY gate for consequential actions
                verdict = self._safety.classify(decision.operation, target_label)
                if verdict.blocked:
                    self._set_status(task, TaskStatus.BLOCKED, verdict.reason)
                    self._emit(task, EventType.COMPLETED, outcome="blocked")
                    break
                if verdict.needs_confirmation:
                    self._set_status(task, TaskStatus.CONFIRMING, verdict.reason)
                    self._emit(task, EventType.CONFIRM, operation=decision.operation.value, target=target_label, message=verdict.reason)
                    if not self._confirmer(decision.describe(), verdict.reason):
                        self._set_status(task, TaskStatus.BLOCKED, f"Declined: {verdict.reason}")
                        self._emit(task, EventType.COMPLETED, outcome="blocked")
                        break

                if self._stop.is_set():
                    self._set_status(task, TaskStatus.STOPPED, "Stopped by user")
                    break

                # EXECUTE (guarded, stale-checked)
                self._set_status(task, TaskStatus.ACTING, decision.describe())
                result = self._executor.execute(decision, observation)
                if result.stale:
                    self._emit(task, EventType.MESSAGE, message="Page changed; re-observing")
                    task.step_count += 1
                    continue
                if not result.ok:
                    task.consecutive_failures += 1
                    self._emit(task, EventType.MESSAGE, message=f"Action failed: {result.detail}")
                    task.step_count += 1
                    continue

                if decision.operation is Operation.WAIT:
                    self._set_status(task, TaskStatus.WAITING, "Waiting")
                    self._sleep(0.1)

                # VERIFY (step level)
                after = self._browser.observe()
                vr = verify_step(decision.operation, observation, after, decision.text)
                verified = bool(vr)
                self._emit(task, EventType.VERIFIED, verified=verified, message=vr.summary)
                task.consecutive_failures = 0 if verified else task.consecutive_failures + 1

                recent.append(decision.describe())
                recent[:] = recent[-8:]
                task.step_count += 1

            return task
        except Exception as exc:  # defensive: never crash the service
            self._set_status(task, TaskStatus.ERROR, f"{type(exc).__name__}: {exc}")
            self._emit(task, EventType.ERROR, message=f"{type(exc).__name__}: {exc}")
            return task

    def _resolve_text(self, task: TaskContext, field_label: str, url: str, recent: list[str]) -> str | None:
        if self._text is None:
            return None
        return self._text.value_for(task.goal, field_label, url, recent)
