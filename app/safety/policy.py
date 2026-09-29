"""Destructive-action policy (PROMPT section 21).

The agent controls the user's real computer, so certain actions must never run
autonomously without explicit confirmation. This module is pure and
deterministic (no Jev, no UI) so it is fully unit-testable.

The policy inspects the *grounded* action — the chosen operation, the target
element's label, and any text about to be typed/pressed — and decides whether
it is destructive. Detection is intentionally conservative: when in doubt,
require confirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.jev.schemas import Operation

# Phrases on a target element (button/menu label) that signal a destructive or
# high-consequence action.
_DESTRUCTIVE_LABELS = [
    r"\bdelete\b",
    r"\bremove\b",
    r"\btrash\b",
    r"\bshut\s*down\b",
    r"\breboot\b",
    r"\brestart\b",
    r"\bformat\b",
    r"\buninstall\b",
    r"\bwipe\b",
    r"\berase\b",
    r"\bpay\b",
    r"\bpurchase\b",
    r"\bbuy\b",
    r"\bconfirm\s+payment\b",
    r"\btransfer\b",
    r"\bclose\s+account\b",
    r"\bdeactivate\b",
    r"\bfactory\s+reset\b",
]

# Dangerous shell / command fragments that must never be typed autonomously.
_DESTRUCTIVE_TEXT = [
    r"\brm\s+-rf\b",
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r":\s*\(\s*\)\s*\{",  # fork bomb
    r"\bapt(-get)?\s+(install|remove|purge)\b",
    r"\bpasswd\b",
    r"\buserdel\b",
    r"\bchmod\s+-R\b",
    r">\s*/dev/sd",
]

# Keystrokes/shortcuts that can be destructive.
_DESTRUCTIVE_KEYS = {"delete", "shift+delete"}

_LABEL_RE = re.compile("|".join(_DESTRUCTIVE_LABELS), re.IGNORECASE)
_TEXT_RE = re.compile("|".join(_DESTRUCTIVE_TEXT), re.IGNORECASE)


@dataclass
class SafetyVerdict:
    allowed: bool  # allowed to run automatically without confirmation
    destructive: bool
    reason: str = ""

    @classmethod
    def safe(cls) -> SafetyVerdict:
        return cls(allowed=True, destructive=False)

    @classmethod
    def needs_confirmation(cls, reason: str) -> SafetyVerdict:
        return cls(allowed=False, destructive=True, reason=reason)


def classify(
    operation: Operation,
    target_label: str | None = None,
    text: str | None = None,
) -> SafetyVerdict:
    """Classify a grounded action as safe or requiring confirmation."""
    label = (target_label or "").strip()
    body = (text or "").strip()

    if operation in (Operation.TYPE, Operation.PRESS_KEY) and body:
        if _TEXT_RE.search(body):
            return SafetyVerdict.needs_confirmation(
                f"potentially destructive command: {body[:40]!r}"
            )
        if operation is Operation.PRESS_KEY and body.lower() in _DESTRUCTIVE_KEYS:
            return SafetyVerdict.needs_confirmation(f"destructive keystroke: {body}")

    if operation in (
        Operation.CLICK,
        Operation.DOUBLE_CLICK,
        Operation.RIGHT_CLICK,
    ) and label:
        if _LABEL_RE.search(label):
            return SafetyVerdict.needs_confirmation(
                f"destructive control: {label[:40]!r}"
            )

    return SafetyVerdict.safe()
