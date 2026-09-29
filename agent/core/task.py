"""Task context — the goal held externally, separate from Jev requests (PROMPT §9, §22)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"
    PAUSED = "paused"
    CONFIRMING = "confirming"
    SUCCESS = "success"
    BLOCKED = "blocked"
    ERROR = "error"
    STOPPED = "stopped"

    @property
    def is_terminal(self) -> bool:
        return self in {
            TaskStatus.SUCCESS,
            TaskStatus.BLOCKED,
            TaskStatus.ERROR,
            TaskStatus.STOPPED,
        }


@dataclass
class BrowserContext:
    """Which tab a task is bound to (PROMPT §22)."""

    tab_id: int | None = None
    url: str = ""
    title: str = ""


@dataclass
class TaskContext:
    """The externally-held task state. Never sent wholesale to Jev."""

    goal: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.IDLE
    started_at: float = field(default_factory=time.monotonic)
    browser: BrowserContext = field(default_factory=BrowserContext)
    step_count: int = 0
    max_steps: int = 50
    max_runtime_ms: int = 5 * 60 * 1000
    max_failures: int = 3
    consecutive_failures: int = 0

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000.0

    def over_budget(self) -> str | None:
        """Return a reason string if a limit is exceeded, else None (PROMPT §16)."""
        if self.step_count >= self.max_steps:
            return "max steps reached"
        if self.elapsed_ms() > self.max_runtime_ms:
            return "max runtime exceeded"
        if self.consecutive_failures >= self.max_failures:
            return "too many consecutive failures"
        return None
