"""Build the compact Jev state and the typed question set (PROMPT sections 9-11).

One request carries multiple related typed questions evaluated in parallel:

* ``operation``   Choice  — which operation to perform next
* ``target``      Choice  — which candidate id to target (or NONE)
* ``continue``    Noul    — should the agent continue after this action
* ``safe``        Noul    — is this action safe/grounded enough to execute

State is kept to hundreds of tokens: goal, current app/window, a short UI
summary, the candidate block, and minimal recent history (PROMPT section 11).
"""

from __future__ import annotations

from app.jev.schemas import OPERATION_CRITERIA

# The Jev SDK is an optional import here so this module (and its tests) load
# without the network SDK installed. The client wrapper imports the real types.
try:  # pragma: no cover - exercised indirectly
    from typesafe_sdk import Choice, Noul  # type: ignore
except Exception:  # pragma: no cover
    Choice = Noul = None  # type: ignore

TARGET_NONE = "NONE"


def build_state(
    goal: str,
    app_name: str,
    window_title: str,
    candidate_block: str,
    recent_history: list[str] | None = None,
    last_verification: str | None = None,
) -> dict:
    """Assemble the compact program state object sent to Jev.

    A structured object (not a giant string) lets question instructions refer
    to named fields and keeps the token count low.
    """
    state: dict = {
        "goal": goal,
        "current_app": app_name or "(unknown)",
        "current_window": window_title or "(unknown)",
        "candidates": candidate_block,
    }
    if recent_history:
        # Only the last few actions materially help the decision.
        state["recent_actions"] = recent_history[-5:]
    if last_verification:
        state["last_verification"] = last_verification
    return state


def build_questions(candidate_ids: list[int]):
    """Construct the typed question set for one decision.

    ``target`` is a Choice over the candidate ids (as strings) plus NONE, so
    Jev can only ever pick an id the local builder produced.
    """
    if Choice is None or Noul is None:  # pragma: no cover - guard for missing SDK
        raise RuntimeError("typesafe-sdk is not installed")

    target_criteria = {str(i): f"Target candidate #{i}" for i in candidate_ids}
    target_criteria[TARGET_NONE] = "No element should be targeted for this operation."

    return {
        "operation": Choice(
            instructions=(
                "Which single operation should happen next to make progress on `goal`, "
                "given `current_app`, `current_window`, the actionable `candidates`, and "
                "`recent_actions`. Choose DONE only if the goal is already satisfied."
            ),
            criteria=dict(OPERATION_CRITERIA),
        ),
        "target": Choice(
            instructions=(
                "Which candidate id from `candidates` should this operation act on. "
                "Pick NONE for operations that need no target (TYPE, PRESS_KEY, SCROLL, "
                "WAIT, DONE, BLOCKED)."
            ),
            criteria=target_criteria,
        ),
        "continue": Noul(
            instructions=(
                "After performing the chosen operation, more steps will still be required "
                "before `goal` is complete."
            ),
        ),
        "safe": Noul(
            instructions=(
                "The chosen operation is safe and well grounded to execute automatically, "
                "and is not a destructive or irreversible system action."
            ),
        ),
    }
