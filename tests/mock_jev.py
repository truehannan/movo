"""A scripted Jev client for the proof-of-work and tests (no network).

Returns fake System-One responses shaped like typesafe_sdk's (``.choices`` with
``.choice/.confidence/.probabilities``, ``.usage.input_tokens``), so the real
:class:`DecisionEngine` parses them unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _ChoiceAnswer:
    choice: str
    confidence: float = 0.9
    probabilities: dict = field(default_factory=dict)


@dataclass
class _Usage:
    input_tokens: int = 80
    output_tokens: int = 0


@dataclass
class _Response:
    choices: dict
    model: str = "jev-1.13.0"
    usage: _Usage = field(default_factory=_Usage)


def response(operation: str, targets: dict | None = None, op_conf: float = 0.95) -> _Response:
    """Build a fake response. ``targets`` maps target-head name -> index string."""
    choices = {"operation": _ChoiceAnswer(operation, op_conf, {operation: op_conf})}
    for key, idx in (targets or {}).items():
        choices[key] = _ChoiceAnswer(str(idx), 0.9, {str(idx): 0.9})
    return _Response(choices=choices)


class ScriptedJevClient:
    """Yields queued responses per system_one call; repeats the last when drained."""

    def __init__(self, responses: list[_Response]) -> None:
        self._responses = list(responses)
        self._i = 0
        self.calls: list[tuple] = []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self._i < len(self._responses):
            r = self._responses[self._i]
            self._i += 1
            return r
        return self._responses[-1]
