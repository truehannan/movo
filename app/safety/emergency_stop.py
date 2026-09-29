"""Emergency stop (PROMPT section 21).

A thread-safe flag the UI sets (ESC key or STOP button) and the agent loop
checks between every step and before every action. Kept dependency-free so it
can be shared between the UI thread and the agent worker thread.
"""

from __future__ import annotations

import threading


class EmergencyStop:
    """A cooperative, thread-safe stop signal."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def trigger(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def triggered(self) -> bool:
        return self._event.is_set()

    def raise_if_triggered(self) -> None:
        if self._event.is_set():
            raise EmergencyStopped()


class EmergencyStopped(Exception):
    """Raised inside the agent loop when the emergency stop is engaged."""
