"""Action policy for consequential browser actions (PROMPT §18, §47).

Deterministic, pure classification: given a resolved action (operation + the
target element's accessible name), decide whether it may run automatically,
needs user confirmation, or is blocked. Per-action policy is configurable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from agent.core.actions import Operation


class ActionPolicy(str, Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


# Labels on a target that signal a consequential/irreversible action.
_CONSEQUENTIAL = [
    r"\bbuy\b", r"\bpurchase\b", r"\bplace\s+order\b", r"\bcheckout\b", r"\bpay\b",
    r"\bconfirm\s+payment\b", r"\bsubscribe\b", r"\bdelete\b", r"\bremove\b",
    r"\bdeactivate\b", r"\bclose\s+account\b", r"\bsend\b", r"\bpublish\b",
    r"\bpost\b", r"\bsubmit\b", r"\btransfer\b", r"\bwithdraw\b", r"\bapprove\b",
]
_CONSEQUENTIAL_RE = re.compile("|".join(_CONSEQUENTIAL), re.IGNORECASE)


@dataclass
class SafetyVerdict:
    policy: ActionPolicy
    reason: str = ""

    @property
    def auto(self) -> bool:
        return self.policy is ActionPolicy.AUTO

    @property
    def needs_confirmation(self) -> bool:
        return self.policy is ActionPolicy.CONFIRM

    @property
    def blocked(self) -> bool:
        return self.policy is ActionPolicy.BLOCKED


class SafetyPolicy:
    """Classifies actions. ``overrides`` maps a matched keyword to a policy."""

    def __init__(
        self,
        default_consequential: ActionPolicy = ActionPolicy.CONFIRM,
        overrides: dict[str, ActionPolicy] | None = None,
    ) -> None:
        self._default = default_consequential
        self._overrides = overrides or {}

    def classify(self, operation: Operation, target_label: str | None) -> SafetyVerdict:
        label = (target_label or "").strip()
        if operation in (Operation.WAIT, Operation.DONE, Operation.BLOCKED):
            return SafetyVerdict(ActionPolicy.AUTO)
        if operation in (Operation.SCROLL_UP, Operation.SCROLL_DOWN):
            return SafetyVerdict(ActionPolicy.AUTO)
        if label:
            m = _CONSEQUENTIAL_RE.search(label)
            if m:
                matched = m.group(0).lower().strip()
                policy = self._overrides.get(matched, self._default)
                return SafetyVerdict(policy, reason=f"consequential control: {label[:40]!r}")
        return SafetyVerdict(ActionPolicy.AUTO)
