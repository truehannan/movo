"""Verification observer (PROMPT section 14).

Never assume an action worked. After acting, we reobserve and compare against
the state before the action. Verification here is deterministic and cheap: it
checks whether the desktop actually changed in a way consistent with the
operation. Jev is not consulted to verify — application code owns ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.desktop.backend import Observation
from app.jev.schemas import Operation


def fingerprint(obs: Observation) -> str:
    """A compact, comparable signature of an observation.

    Two observations with the same fingerprint are treated as "the same state"
    for loop detection and verification.
    """
    labels = "|".join(
        f"{e.role.value}:{e.short_label()}" for e in obs.elements[:20]
    )
    focused = obs.focused_element.short_label() if obs.focused_element else ""
    return f"{obs.window.app_name}::{obs.window.title}::{focused}::{labels}"


@dataclass
class VerificationResult:
    verified: bool
    summary: str

    def __bool__(self) -> bool:
        return self.verified


def verify(
    operation: Operation,
    before: Observation,
    after: Observation,
    typed_text: str | None = None,
) -> VerificationResult:
    """Decide whether ``operation`` plausibly took effect."""
    before_fp = fingerprint(before)
    after_fp = fingerprint(after)
    changed = before_fp != after_fp

    if operation in (Operation.WAIT,):
        # WAIT is about letting state settle; either outcome is acceptable.
        return VerificationResult(True, "waited")

    if operation in (Operation.DONE, Operation.BLOCKED):
        return VerificationResult(True, operation.value.lower())

    if operation is Operation.TYPE and typed_text:
        # Text landed if the focused element's value now contains it.
        fe = after.focused_element
        if fe and fe.value and typed_text[:20] in (fe.value or ""):
            return VerificationResult(True, "text present in focused field")
        # Otherwise fall back to "something changed".

    if changed:
        return VerificationResult(True, "desktop state changed")

    # Navigation/activation with no observable change is suspicious.
    if operation in (
        Operation.CLICK,
        Operation.DOUBLE_CLICK,
        Operation.RIGHT_CLICK,
        Operation.PRESS_KEY,
    ):
        return VerificationResult(False, "no observable change after action")

    return VerificationResult(True, "no verification needed")
