"""The Jev client wrapper and the decision engine (PROMPT sections 5, 9, 12).

``JevClient`` is a thin adapter over the official ``typesafe-sdk`` that exposes
a single ``system_one(state, questions)`` method and normalises usage/telemetry.
It is injectable, so tests pass a mock client with canned responses and the
whole agent loop runs without the network.

``DecisionEngine`` turns candidates + context into one Jev call and parses the
typed answers into a :class:`~app.jev.schemas.Decision`. It performs *no* side
effects and makes *no* deterministic decisions Jev should not make.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from app.config.settings import ConfidenceThresholds
from app.desktop.candidates import Candidate, serialize_candidates
from app.jev.questions import TARGET_NONE, build_questions, build_state
from app.jev.schemas import Decision, Operation


class SystemOneResponse(Protocol):
    """Structural type for the response object the SDK / mock returns."""

    choices: dict[str, Any]
    nouls: dict[str, Any]
    model: str
    usage: Any


class SystemOneClient(Protocol):
    """Structural type for anything that can answer a system_one call."""

    def system_one(self, state: Any, questions: dict) -> SystemOneResponse: ...


@dataclass
class JevConnectionResult:
    ok: bool
    model: str = ""
    detail: str = ""


class JevClient:
    """Adapter over ``typesafe_sdk.TypeSafeClient``.

    The same SDK speaks to the hosted Jev API or to a local Laya server (which
    implements the identical ``/v1/systemone`` wire contract): only ``base_url``
    changes. The API key is passed to the SDK directly and never logged.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "jev-latest",
        base_url: str | None = None,
    ) -> None:
        from typesafe_sdk import TypeSafeClient  # type: ignore

        self._model = model
        self._base_url = base_url
        kwargs: dict[str, Any] = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = TypeSafeClient(**kwargs)

    @property
    def model(self) -> str:
        return self._model

    def system_one(self, state: Any, questions: dict) -> Any:
        return self._client.system_one(state, questions)

    def test_connection(self) -> JevConnectionResult:
        """Make one tiny call to verify the key/model work (PROMPT section 30)."""
        from typesafe_sdk import Noul  # type: ignore

        try:
            resp = self._client.system_one(
                "connection check", {"ok": Noul(instructions="This is a connection test")}
            )
            return JevConnectionResult(ok=True, model=getattr(resp, "model", self._model))
        except Exception as exc:  # pragma: no cover - network dependent
            return JevConnectionResult(ok=False, detail=type(exc).__name__)

    def close(self) -> None:  # pragma: no cover - network dependent
        try:
            self._client.close()
        except Exception:
            pass


class LayaClient(JevClient):
    """A :class:`JevClient` pointed at a locally-running Laya server.

    Laya's server implements TypeSafe's exact wire API, so this reuses the whole
    decision path — only the base URL and a dummy key differ. No key leaves the
    machine and no network call is made beyond localhost.
    """

    def __init__(self, base_url: str, checkpoint: str = "laya") -> None:
        super().__init__(api_key="local", model=checkpoint, base_url=base_url)


def _answer_value(container: dict, key: str, attr: str, default=None):
    ans = container.get(key)
    if ans is None:
        return default
    return getattr(ans, attr, default)


class DecisionEngine:
    """Produces one typed :class:`Decision` per observation."""

    def __init__(self, client: SystemOneClient, thresholds: ConfidenceThresholds) -> None:
        self._client = client
        self._t = thresholds

    def decide(
        self,
        goal: str,
        app_name: str,
        window_title: str,
        candidates: list[Candidate],
        recent_history: list[str] | None = None,
        last_verification: str | None = None,
    ) -> Decision:
        candidate_block = serialize_candidates(candidates)
        state = build_state(
            goal=goal,
            app_name=app_name,
            window_title=window_title,
            candidate_block=candidate_block,
            recent_history=recent_history,
            last_verification=last_verification,
        )
        questions = build_questions([c.id for c in candidates])

        t0 = time.perf_counter()
        resp = self._client.system_one(state, questions)
        latency_ms = (time.perf_counter() - t0) * 1e3

        return self._parse(resp, candidates, latency_ms)

    def _parse(
        self, resp: Any, candidates: list[Candidate], latency_ms: float
    ) -> Decision:
        choices = getattr(resp, "choices", {}) or {}
        nouls = getattr(resp, "nouls", {}) or {}

        op_answer = choices.get("operation")
        op_str = getattr(op_answer, "choice", Operation.BLOCKED.value)
        op_conf = float(getattr(op_answer, "confidence", 0.0) or 0.0)
        op_probs = dict(getattr(op_answer, "probabilities", {}) or {})
        try:
            operation = Operation(op_str)
        except ValueError:
            operation = Operation.BLOCKED

        target_id: int | None = None
        if operation.needs_target:
            tgt = _answer_value(choices, "target", "choice", TARGET_NONE)
            if tgt and tgt != TARGET_NONE:
                try:
                    tid = int(tgt)
                    if any(c.id == tid for c in candidates):
                        target_id = tid
                except (TypeError, ValueError):
                    target_id = None

        cont = float(_answer_value(nouls, "continue", "noul", 0.0) or 0.0)
        safe = float(_answer_value(nouls, "safe", "noul", 0.0) or 0.0)

        model = getattr(resp, "model", "")
        usage = getattr(resp, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0

        return Decision(
            operation=operation,
            target_id=target_id,
            text=None,  # filled in by the executor/planner, not by Jev
            confidence=op_conf,
            should_continue=cont >= self._t.noul_yes,
            safe=safe >= self._t.noul_yes,
            op_probabilities=op_probs,
            model=model,
            input_tokens=input_tokens,
            latency_ms=latency_ms,
        )
