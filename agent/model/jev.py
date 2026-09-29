"""The Jev decision engine (PROMPT §1, §2, §11).

Builds ONE Jev request per cycle containing an ``operation`` Choice over the
bounded vocabulary and a per-operation ``target`` Choice over the current
element indices. The executor later reads only the target head matching the
chosen operation. Text for TYPE_TEXT is produced by a separate helper (see
``text.py``), never by Jev.

The client is injectable, so tests drive the whole loop with a scripted decider
and no network.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from agent.core.actions import OPERATION_CRITERIA, Decision, Operation
from agent.core.state import Observation
from agent.model.questions import NEXT_ACTION, TARGET

# The SDK question types are imported lazily so this module loads without the
# network SDK present (e.g. in pure-logic tests). A minimal fallback keeps the
# engine usable with a mock client, which ignores the question objects anyway.
try:  # pragma: no cover
    from typesafe_sdk import Choice  # type: ignore
except Exception:  # pragma: no cover
    class Choice:  # type: ignore
        """Fallback stand-in used only when typesafe-sdk is absent."""

        def __init__(self, instructions: str = "", criteria: dict | None = None) -> None:
            self.instructions = instructions
            self.criteria = criteria or {}

TARGET_NONE = "NONE"


class SystemOneClient(Protocol):
    def system_one(self, state: Any, questions: dict) -> Any: ...


def build_state(
    goal: str,
    url: str,
    title: str,
    element_lines: list[str],
    recent_actions: list[str] | None = None,
) -> dict:
    """Compact program state for Jev — goal + current page + indexed elements."""
    state: dict = {
        "goal": goal,
        "current_url": url,
        "current_title": title,
        "elements": element_lines,
    }
    if recent_actions:
        state["recent_actions"] = recent_actions[-5:]
    return state


def build_questions(observation: Observation):
    """Operation Choice + one target Choice per operation that needs a target.

    Target criteria are dynamic: only indices that support the operation are
    offered (the dynamic action space, PROMPT §11).
    """
    questions: dict[str, Any] = {
        "operation": Choice(instructions=NEXT_ACTION, criteria=dict(OPERATION_CRITERIA)),
    }

    def target_choice(elements) -> Any:
        criteria = {str(e.index): e.to_line() for e in elements}
        criteria[TARGET_NONE] = "No suitable target for this operation."
        return Choice(instructions=TARGET, criteria=criteria)

    click_targets = observation.clickable()
    type_targets = observation.typeable()
    select_targets = observation.selectable()
    if click_targets:
        questions["target_click"] = target_choice(click_targets)
    if type_targets:
        questions["target_type"] = target_choice(type_targets)
    if select_targets:
        questions["target_select"] = target_choice(select_targets)
    return questions


_OP_TO_TARGET_KEY = {
    Operation.CLICK: "target_click",
    Operation.TYPE_TEXT: "target_type",
    Operation.SELECT: "target_select",
}


class DecisionEngine:
    """Produces one typed :class:`Decision` per observation."""

    def __init__(self, client: SystemOneClient) -> None:
        self._client = client

    def decide(
        self,
        goal: str,
        observation: Observation,
        recent_actions: list[str] | None = None,
    ) -> Decision:
        state = build_state(
            goal,
            observation.url,
            observation.title,
            [e.to_line() for e in observation.elements],
            recent_actions,
        )
        questions = build_questions(observation)
        t0 = time.perf_counter()
        resp = self._client.system_one(state, questions)
        latency_ms = (time.perf_counter() - t0) * 1e3
        return self._parse(resp, observation, latency_ms)

    def _parse(self, resp: Any, observation: Observation, latency_ms: float) -> Decision:
        choices = getattr(resp, "choices", {}) or {}
        op_ans = choices.get("operation")
        op_str = getattr(op_ans, "choice", Operation.BLOCKED.value)
        try:
            operation = Operation(op_str)
        except ValueError:
            operation = Operation.BLOCKED
        op_conf = float(getattr(op_ans, "confidence", 0.0) or 0.0)
        op_probs = dict(getattr(op_ans, "probabilities", {}) or {})

        target_index: int | None = None
        if operation.needs_target:
            key = _OP_TO_TARGET_KEY.get(operation)
            tgt_ans = choices.get(key) if key else None
            raw = getattr(tgt_ans, "choice", TARGET_NONE) if tgt_ans else TARGET_NONE
            if raw and raw != TARGET_NONE:
                try:
                    idx = int(raw)
                    if observation.by_index(idx) is not None:
                        target_index = idx
                except (TypeError, ValueError):
                    target_index = None

        usage = getattr(resp, "usage", None)
        return Decision(
            operation=operation,
            target_index=target_index,
            confidence=op_conf,
            op_probabilities=op_probs,
            model=getattr(resp, "model", ""),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0) if usage else 0,
            latency_ms=latency_ms,
        )


class JevClient:
    """Thin adapter over ``typesafe_sdk.TypeSafeClient`` (server-side only)."""

    def __init__(self, api_key: str, model: str = "jev-latest", base_url: str | None = None) -> None:
        from typesafe_sdk import TypeSafeClient  # type: ignore

        kwargs: dict[str, Any] = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = TypeSafeClient(**kwargs)
        self._model = model

    def system_one(self, state: Any, questions: dict) -> Any:
        return self._client.system_one(state, questions)

    def close(self) -> None:  # pragma: no cover
        try:
            self._client.close()
        except Exception:
            pass
