"""Agent events — concise execution facts, never model reasoning (PROMPT §8, §20).

These are emitted to the UI over the WebSocket. They deliberately expose only
what the agent did (reading page, found N elements, clicked X, waiting), never
hidden chain-of-thought.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum


class EventType(str, Enum):
    STATUS = "agent.status"        # status changed
    OBSERVED = "agent.observed"    # page read, element count
    DECISION = "agent.action"      # chose an operation + target
    ACTED = "agent.acted"          # executed (with result)
    MESSAGE = "agent.message"      # human-readable progress line
    CONFIRM = "agent.confirm"      # consequential action needs confirmation
    VERIFIED = "agent.verified"    # verification result
    ERROR = "agent.error"
    COMPLETED = "agent.completed"  # terminal


@dataclass
class AgentEvent:
    type: EventType
    task_id: str = ""
    step: int = 0
    message: str = ""
    # Optional structured fields (only the safe, user-facing ones).
    status: str | None = None
    operation: str | None = None
    target: str | None = None
    verified: bool | None = None
    outcome: str | None = None
    ts: float = field(default_factory=lambda: time.time())

    def to_wire(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        # Drop None fields to keep the payload compact.
        return {k: v for k, v in d.items() if v is not None}
