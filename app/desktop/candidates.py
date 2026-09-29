"""Candidate generation: turn an :class:`Observation` into a small set of
compact, typed candidates for Jev to choose between (PROMPT sections 6, 8, 11).

The single most important optimisation is keeping the Jev decision space small:
roughly 5-20 actionable candidates. This module owns all the deterministic
filtering the application should do *without* Jev (PROMPT section 12):

* drop invisible, disabled, decorative, and zero-area nodes
* drop redundant containers and duplicate elements
* rank the remainder and cap the count
* serialize to a compact text block keyed by candidate id
"""

from __future__ import annotations

from dataclasses import dataclass

from app.desktop.backend import Observation, Role, UIElement

# Roles that a user can meaningfully act on. Pure containers/labels are only
# kept when nothing better is available (they still carry text for context).
_ACTIONABLE_ROLES = {
    Role.BUTTON,
    Role.TEXTBOX,
    Role.LINK,
    Role.CHECKBOX,
    Role.RADIO,
    Role.MENUITEM,
    Role.TAB,
    Role.LISTITEM,
    Role.COMBOBOX,
    Role.TREEITEM,
    Role.MENU,
}

DEFAULT_MAX_CANDIDATES = 18
MIN_INTERESTING_AREA = 4  # px^2; smaller is almost certainly decorative


@dataclass(frozen=True)
class Candidate:
    """A compact, id-addressable actionable element handed to Jev.

    ``element`` is retained so the executor can resolve the chosen id back to a
    live element and its bounds. Only the compact fields reach Jev.
    """

    id: int
    role: Role
    name: str
    value: str | None
    enabled: bool
    element: UIElement

    def to_line(self) -> str:
        """Compact single-line serialization for the Jev state block."""
        parts = [f"{self.id}:", f"role={self.role.value}"]
        if self.name:
            parts.append(f'name="{self.name}"')
        if self.value is not None:
            parts.append(f'value="{self.value}"')
        if not self.enabled:
            parts.append("enabled=false")
        return " ".join(parts)


def _is_noise(el: UIElement) -> bool:
    """Deterministic filter for elements that should never be candidates."""
    if not el.visible or not el.enabled:
        return True
    if el.bounds is not None and el.bounds.area < MIN_INTERESTING_AREA:
        return True
    # A node with no label, no value and no actionable affordance is decorative.
    has_text = bool(el.name or el.description or el.value)
    if not el.actionable and not has_text:
        return True
    return False


def _dedup_key(el: UIElement) -> tuple:
    return (el.role, (el.name or el.description or "").strip().lower(), el.value)


def _rank(el: UIElement) -> tuple:
    """Sort key: focused first, then actionable, then labelled, then by area.

    Returns a tuple compared in *descending* usefulness after negation below.
    """
    labelled = bool(el.name or el.description)
    area = el.bounds.area if el.bounds else 0
    return (
        1 if el.focused else 0,
        1 if el.actionable else 0,
        1 if el.role in _ACTIONABLE_ROLES else 0,
        1 if labelled else 0,
        area,
    )


def build_candidates(
    observation: Observation,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> list[Candidate]:
    """Filter, de-duplicate, rank and cap observed elements into candidates.

    The returned candidates are numbered 0..N-1; that id is the bridge between
    Jev's target choice and the local executor.
    """
    seen: set[tuple] = set()
    kept: list[UIElement] = []
    for el in observation.elements:
        if _is_noise(el):
            continue
        key = _dedup_key(el)
        if key in seen:
            continue
        seen.add(key)
        kept.append(el)

    kept.sort(key=_rank, reverse=True)
    kept = kept[:max_candidates]

    candidates: list[Candidate] = []
    for idx, el in enumerate(kept):
        candidates.append(
            Candidate(
                id=idx,
                role=el.role,
                name=el.short_label(),
                value=el.value if el.editable or el.value else None,
                enabled=el.enabled,
                element=el,
            )
        )
    return candidates


def serialize_candidates(candidates: list[Candidate]) -> str:
    """Render candidates as the compact block sent to Jev.

    Example::

        0: role=button name="New issue"
        1: role=textbox name="Search" value=""
        2: role=link name="Issue #143 Add authentication"
    """
    if not candidates:
        return "(no actionable candidates)"
    return "\n".join(c.to_line() for c in candidates)
