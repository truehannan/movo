"""Short local action history + loop detection (PROMPT sections 14, 15, 21).

Keeps a bounded list of what happened, exposes a compact recent slice for Jev,
and detects two failure modes that must stop the agent:

* the same action repeated with no effect
* the same observed state seen repeatedly (no progress)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HistoryEntry:
    step: int
    action: str  # e.g. 'CLICK → New issue'
    verified: bool
    note: str = ""

    def to_line(self) -> str:
        mark = "VERIFIED" if self.verified else "unverified"
        base = f"{self.step}. {self.action} [{mark}]"
        return f"{base} {self.note}".strip()


@dataclass
class History:
    max_entries: int = 50
    loop_threshold: int = 3
    entries: list[HistoryEntry] = field(default_factory=list)
    _action_streak: tuple[str, int] = ("", 0)
    _state_counts: dict[str, int] = field(default_factory=dict)

    def add(self, step: int, action: str, verified: bool, note: str = "") -> None:
        self.entries.append(HistoryEntry(step, action, verified, note))
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]
        last_action, count = self._action_streak
        if action == last_action:
            self._action_streak = (action, count + 1)
        else:
            self._action_streak = (action, 1)

    def observe_state(self, state_fingerprint: str) -> None:
        self._state_counts[state_fingerprint] = (
            self._state_counts.get(state_fingerprint, 0) + 1
        )

    def recent_lines(self, n: int = 5) -> list[str]:
        return [e.to_line() for e in self.entries[-n:]]

    # --- loop detection --------------------------------------------------
    def repeated_action(self) -> bool:
        _, count = self._action_streak
        return count >= self.loop_threshold

    def repeated_state(self) -> bool:
        return any(c >= self.loop_threshold for c in self._state_counts.values())

    def is_looping(self) -> bool:
        return self.repeated_action() or self.repeated_state()
