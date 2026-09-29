"""Guarded execution (PROMPT §13).

Resolves a :class:`Decision` against a FRESH observation and, for mutations,
rejects stale targets rather than executing blindly. The freshness check runs
immediately before the mutation: if the page changed semantically since the
decision was made, the executor refuses and signals the loop to re-observe and
re-decide. Browser mutations are never retried by this layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.browser.browser import BrowserSession
from agent.core.actions import Decision, Operation
from agent.core.state import Observation
from agent.core.verification import is_stale


@dataclass
class ExecutionResult:
    ok: bool
    stale: bool = False
    detail: str = ""


class Executor:
    """Executes one resolved decision against the live page, guarding freshness."""

    def __init__(self, browser: BrowserSession) -> None:
        self._browser = browser

    def execute(self, decision: Decision, decided_on: Observation) -> ExecutionResult:
        op = decision.operation

        # Non-mutating operations don't need a stale check.
        if op is Operation.WAIT:
            return ExecutionResult(True, detail="waited")
        if op is Operation.SCROLL_DOWN:
            return ExecutionResult(self._browser.scroll(600), detail="scrolled down")
        if op is Operation.SCROLL_UP:
            return ExecutionResult(self._browser.scroll(-600), detail="scrolled up")
        if op.is_terminal:
            return ExecutionResult(True, detail=op.value.lower())

        # Mutations: re-observe and reject stale targets (never execute blindly).
        fresh = self._browser.observe()
        if is_stale(decided_on, fresh, decision.target_index):
            return ExecutionResult(False, stale=True, detail="stale target; re-observing")

        target = fresh.by_index(decision.target_index)
        if target is None:
            return ExecutionResult(False, stale=True, detail="target vanished")

        if op is Operation.CLICK:
            return ExecutionResult(self._browser.click(target), detail="clicked")
        if op is Operation.TYPE_TEXT:
            if not decision.text:
                return ExecutionResult(False, detail="no text to type")
            return ExecutionResult(self._browser.type_text(target, decision.text), detail="typed")
        if op is Operation.SELECT:
            opt = decision.option_index if decision.option_index is not None else 0
            return ExecutionResult(self._browser.select(target, opt), detail="selected")

        return ExecutionResult(False, detail=f"unsupported operation {op.value}")
