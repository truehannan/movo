"""Goal planning and action-argument derivation (PROMPT sections 12, 16).

Planning is kept separate from Jev. Jev decides *which* operation and *which*
candidate; it does not generate the text to type or the key to press. This
module derives those arguments deterministically from the user's goal.

The MVP planner is rule-based (no large LLM), which keeps the app local and
fast per PROMPT section 4. The interface leaves room to plug an LLM in later
for ambiguous decomposition without touching the loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.jev.schemas import Operation

# Common key words that map to real key names understood by the backend.
_KEY_ALIASES = {
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "space": "space",
    "backspace": "BackSpace",
}


@dataclass
class Plan:
    """A lightweight plan: the goal plus any text the agent may need to type.

    ``typed_texts`` is an ordered queue of strings extracted from the goal
    (usually quoted phrases or search terms). The loop pops from it whenever
    Jev chooses TYPE.
    """

    goal: str
    subgoals: list[str] = field(default_factory=list)
    typed_texts: list[str] = field(default_factory=list)


def _extract_quoted(goal: str) -> list[str]:
    return re.findall(r'"([^"]+)"|\'([^\']+)\'', goal)


def _extract_search_terms(goal: str) -> list[str]:
    """Pull a likely search string out of a natural-language goal."""
    texts: list[str] = []
    for a, b in _extract_quoted(goal):
        texts.append(a or b)
    if texts:
        return texts
    # "search for X", "find X", "create a folder called X"
    patterns = [
        r"search(?:\s+for)?\s+(.+)$",
        r"look\s+up\s+(.+)$",
        r"(?:called|named)\s+(.+)$",
        r"find\s+(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, goal, re.IGNORECASE)
        if m:
            term = m.group(1).strip().rstrip(".")
            # Trim trailing clauses.
            term = re.split(r"\s+(?:and|then)\s+", term)[0].strip()
            if term:
                texts.append(term)
                break
    return texts


def make_plan(goal: str) -> Plan:
    """Interpret a user goal into a plan with derived text arguments."""
    goal = goal.strip()
    return Plan(goal=goal, typed_texts=_extract_search_terms(goal))


def resolve_text_argument(
    operation: Operation,
    plan: Plan,
    target_label: str | None,
) -> str | None:
    """Derive the concrete text/key argument for TYPE / PRESS_KEY.

    Jev chose the operation; this turns it into a grounded argument without
    asking Jev to generate free text.
    """
    if operation is Operation.TYPE:
        if plan.typed_texts:
            return plan.typed_texts.pop(0)
        # Fall back to the whole goal if nothing more specific was extracted.
        return plan.goal
    if operation is Operation.PRESS_KEY:
        # A key press usually follows typing; default to Return unless the
        # goal names a specific key.
        goal_l = plan.goal.lower()
        for alias, key in _KEY_ALIASES.items():
            if re.search(rf"\bpress\s+{alias}\b", goal_l) or re.search(
                rf"\bhit\s+{alias}\b", goal_l
            ):
                return key
        return "Return"
    return None
