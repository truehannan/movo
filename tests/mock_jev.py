"""Mock Jev response objects and a scriptable client for tests.

Mirrors the shape of ``typesafe_sdk`` responses (``.choices``, ``.nouls``,
``.model``, ``.usage``) closely enough that :class:`DecisionEngine` parses them
without knowing they are fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeChoiceAnswer:
    choice: str
    confidence: float = 0.9
    probabilities: dict = field(default_factory=dict)


@dataclass
class FakeNoulAnswer:
    noul: float = 0.9


@dataclass
class FakeUsage:
    input_tokens: int = 120
    output_tokens: int = 4


@dataclass
class FakeResponse:
    choices: dict
    nouls: dict
    model: str = "jev-1.13.0"
    usage: FakeUsage = field(default_factory=FakeUsage)

    @property
    def answers(self) -> dict:
        merged = {}
        merged.update(self.choices)
        merged.update(self.nouls)
        return merged


def make_response(
    operation: str,
    target: str = "NONE",
    *,
    op_conf: float = 0.9,
    cont: float = 0.9,
    safe: float = 0.95,
) -> FakeResponse:
    return FakeResponse(
        choices={
            "operation": FakeChoiceAnswer(operation, op_conf, {operation: op_conf}),
            "target": FakeChoiceAnswer(target, 0.9, {target: 0.9}),
        },
        nouls={"continue": FakeNoulAnswer(cont), "safe": FakeNoulAnswer(safe)},
    )


class ScriptedJevClient:
    """Returns a queued response per ``system_one`` call.

    When the script is exhausted it keeps returning the last response, so a loop
    that runs longer than expected does not crash (it will hit a step/loop cap).
    """

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self._i = 0
        self.calls: list[tuple] = []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self._i < len(self._responses):
            resp = self._responses[self._i]
            self._i += 1
            return resp
        return self._responses[-1]
