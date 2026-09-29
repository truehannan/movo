"""Confirmation gate for destructive actions (PROMPT section 21).

The agent loop asks a :class:`Confirmer` before running any action the policy
flagged as destructive. The default policy in tests/headless mode denies; the
UI supplies an implementation that shows a dialog.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class Confirmer(Protocol):
    """Something that can ask the user to confirm a destructive action."""

    def confirm(self, action_description: str, reason: str) -> bool: ...


class AutoDenyConfirmer:
    """Denies every destructive action. Safe default for headless/tests."""

    def confirm(self, action_description: str, reason: str) -> bool:
        return False


class CallbackConfirmer:
    """Delegates to a callable (wired to a UI dialog on the main thread)."""

    def __init__(self, callback: Callable[[str, str], bool]) -> None:
        self._callback = callback

    def confirm(self, action_description: str, reason: str) -> bool:
        try:
            return bool(self._callback(action_description, reason))
        except Exception:
            return False
