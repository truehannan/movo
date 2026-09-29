"""The bounded browser operation vocabulary and the typed decision (PROMPT §2, §11).

Faithful to browser-use/jev-ultrafast: one Jev request asks an ``operation``
Choice plus a per-operation ``target`` Choice; the executor consumes only the
target head matching the chosen operation. Jev never generates selectors,
coordinates, JavaScript, or the text to type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Operation(str, Enum):
    """The bounded operations Jev can choose (upstream vocabulary + room to grow)."""

    CLICK = "CLICK"
    TYPE_TEXT = "TYPE_TEXT"
    SELECT = "SELECT"
    SCROLL_UP = "SCROLL_UP"
    SCROLL_DOWN = "SCROLL_DOWN"
    WAIT = "WAIT"
    DONE = "DONE"
    BLOCKED = "BLOCKED"

    @property
    def needs_target(self) -> bool:
        return self in {Operation.CLICK, Operation.TYPE_TEXT, Operation.SELECT}

    @property
    def needs_text(self) -> bool:
        return self is Operation.TYPE_TEXT

    @property
    def is_terminal(self) -> bool:
        return self in {Operation.DONE, Operation.BLOCKED}

    @property
    def is_mutation(self) -> bool:
        """Actions that change page state (subject to freshness guards)."""
        return self in {Operation.CLICK, Operation.TYPE_TEXT, Operation.SELECT}


# Human-readable operation policy — the criteria Jev sees. The question
# descriptions ARE the policy (kept compact, upstream style).
OPERATION_CRITERIA: dict[str, str] = {
    Operation.CLICK.value: "Activate a visible interactive element (button, link, tab, checkbox, radio, menu item).",
    Operation.TYPE_TEXT.value: "Enter text into an editable text field or editable combobox.",
    Operation.SELECT.value: "Choose an option in a native select / dropdown.",
    Operation.SCROLL_UP.value: "Scroll the page up to reveal content above the viewport.",
    Operation.SCROLL_DOWN.value: "Scroll the page down to reveal content below the viewport.",
    Operation.WAIT.value: "Wait because a needed control is absent/disabled or submitted results are still loading.",
    Operation.DONE.value: "Every requirement of the goal is satisfied with visible evidence on the page.",
    Operation.BLOCKED.value: "No supported operation can make progress toward the goal.",
}


@dataclass
class Decision:
    """One resolved decision for the current observation.

    ``target_index`` refers to an element index from the current snapshot (or
    ``None``). ``text`` is filled by the separate text helper for TYPE_TEXT, not
    by Jev. ``option_index`` is the code-owned option index for SELECT.
    """

    operation: Operation
    target_index: int | None = None
    option_index: int | None = None
    text: str | None = None
    confidence: float = 0.0
    op_probabilities: dict[str, float] = field(default_factory=dict)
    model: str = ""
    input_tokens: int = 0
    latency_ms: float = 0.0

    def describe(self) -> str:
        bits = [self.operation.value]
        if self.target_index is not None:
            bits.append(f"→ [{self.target_index}]")
        if self.text:
            preview = self.text if len(self.text) <= 40 else self.text[:37] + "…"
            bits.append(f'"{preview}"')
        return " ".join(bits)
