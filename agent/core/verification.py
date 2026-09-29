"""Independent verification + freshness guards (PROMPT §13, §14).

Two separate concerns live here:

* **Freshness / stale-target rejection** — before executing a mutation the
  chosen target must still exist in a *fresh* observation with matching
  identity; if the page changed semantically, the decision is stale and must be
  discarded so the agent re-observes and re-decides. Mutations are never blindly
  retried.
* **Verification** — ``DONE`` is never taken as proof. We check observable
  evidence (URL/title change, visible results, changed field/checkbox state)
  consistent with the operation before accepting a step, and the caller runs a
  goal-level check before accepting task completion.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.core.actions import Operation
from agent.core.state import Observation


def is_stale(before: Observation, fresh: Observation, target_index: int | None) -> bool:
    """True if a decision made on ``before`` is unsafe to apply to ``fresh``.

    The page is considered to have changed out from under the decision when the
    semantic fingerprint differs, or the target no longer resolves to an element
    with the same role+name.
    """
    if before.fingerprint and fresh.fingerprint and before.fingerprint != fresh.fingerprint:
        return True
    if target_index is None:
        return False
    b = before.by_index(target_index)
    f = fresh.by_index(target_index)
    if b is None or f is None:
        return True
    # Identity check: same index must still be the same control.
    if b.role != f.role or b.short() != f.short():
        return True
    if f.disabled:
        return True
    return False


@dataclass
class VerificationResult:
    verified: bool
    summary: str

    def __bool__(self) -> bool:
        return self.verified


def verify_step(
    operation: Operation,
    before: Observation,
    after: Observation,
    typed_text: str | None = None,
) -> VerificationResult:
    """Did ``operation`` plausibly take effect (step-level, not goal-level)?"""
    changed = before.fingerprint != after.fingerprint

    if operation in (Operation.WAIT,):
        return VerificationResult(True, "waited")
    if operation in (Operation.DONE, Operation.BLOCKED):
        return VerificationResult(True, operation.value.lower())
    if operation in (Operation.SCROLL_UP, Operation.SCROLL_DOWN):
        return VerificationResult(True, "scrolled")

    if operation is Operation.TYPE_TEXT and typed_text:
        # The value landed if some editable field now holds the typed text.
        for e in after.typeable():
            if e.value and typed_text[:20] in e.value:
                return VerificationResult(True, "text present in field")
        # else fall through to change check

    if changed:
        return VerificationResult(True, "page state changed")

    if operation in (Operation.CLICK, Operation.SELECT):
        return VerificationResult(False, "no observable change after action")
    return VerificationResult(True, "no verification needed")
