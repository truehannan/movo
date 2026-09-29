"""Structured page observation: the indexed, interactive element table (PROMPT §10).

A snapshot of the current page is translated into ``Element`` records — role,
accessible name, value, state, index, and which operations each supports. Only
useful, visible, interactive content is retained; the raw DOM/HTML never reaches
the model. The ``index`` is the bridge between Jev's target choice and the
executor, and it is resolved against a *fresh* snapshot before every mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Element:
    """One indexed, interactive element from a page snapshot."""

    index: int
    role: str  # normalised role, e.g. "button", "textbox", "link", "combobox"
    name: str = ""  # accessible name / visible text
    value: str | None = None
    # State flags used by the target criteria and freshness guards.
    editable: bool = False
    checked: bool | None = None
    selected: bool | None = None
    disabled: bool = False
    # Which bounded operations this element supports (drives the dynamic action space).
    can_click: bool = False
    can_type: bool = False
    can_select: bool = False
    # Native-select options (code-owned indices), when this is a select.
    options: list[str] = field(default_factory=list)

    def short(self) -> str:
        label = (self.name or self.value or "").strip().replace("\n", " ")
        return label[:80]

    def to_line(self) -> str:
        """Compact one-line rendering for the candidate block sent to the model."""
        parts = [f"[{self.index}]", self.role]
        if self.short():
            parts.append(self.short())
        if self.value is not None and self.value != "":
            parts.append(f'value="{self.value[:40]}"')
        if self.checked is not None:
            parts.append("checked" if self.checked else "unchecked")
        if self.disabled:
            parts.append("disabled")
        return " ".join(parts)


@dataclass
class Observation:
    """A fresh, structured view of the current page for one decision cycle."""

    url: str = ""
    title: str = ""
    elements: list[Element] = field(default_factory=list)
    # A compact semantic fingerprint used for freshness/stale-target guards.
    fingerprint: str = ""

    def by_index(self, index: int | None) -> Element | None:
        if index is None:
            return None
        return next((e for e in self.elements if e.index == index), None)

    def clickable(self) -> list[Element]:
        return [e for e in self.elements if e.can_click and not e.disabled]

    def typeable(self) -> list[Element]:
        return [e for e in self.elements if e.can_type and not e.disabled]

    def selectable(self) -> list[Element]:
        return [e for e in self.elements if e.can_select and not e.disabled]

    def summary(self) -> str:
        return f"{len(self.elements)} interactive elements on {self.title or self.url!r}"
