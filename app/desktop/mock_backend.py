"""A scriptable in-memory :class:`DesktopBackend` for tests and demos.

The mock holds a list of "screens" (observations). Actions can advance the
current screen so the agent loop sees state change, exactly as a real desktop
would, without touching the display. This is what makes the whole
observe->decide->act->verify loop testable (PROMPT section 25).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.desktop.backend import (
    Bounds,
    DesktopBackend,
    Observation,
    Role,
    UIElement,
    WindowInfo,
)


def el(
    node_id: str,
    role: Role,
    name: str = "",
    *,
    value: str | None = None,
    editable: bool = False,
    focused: bool = False,
    actionable: bool = True,
    x: int = 0,
    y: int = 0,
    w: int = 100,
    h: int = 30,
) -> UIElement:
    """Convenience constructor for a visible, enabled element."""
    return UIElement(
        node_id=node_id,
        role=role,
        name=name,
        value=value,
        bounds=Bounds(x, y, w, h),
        enabled=True,
        visible=True,
        focusable=editable or actionable,
        focused=focused,
        editable=editable,
        actionable=actionable,
    )


@dataclass
class MockDesktopBackend(DesktopBackend):
    """Records actions and lets a transition function advance state.

    ``transition`` receives ``(action_name, argument, current_index)`` and
    returns the next screen index. If it returns the same index, the state is
    unchanged (which the verifier will treat as an unverified action).
    """

    screens: list[Observation]
    index: int = 0
    transition: Callable[[str, object, int], int] | None = None
    actions: list[tuple[str, object]] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)

    # --- observation ---
    def get_active_window(self) -> WindowInfo:
        return self.screens[self.index].window

    def get_ui_tree(self) -> Observation:
        return self.screens[self.index]

    def screenshot(self, path: str | None = None) -> str | None:
        return path or "/tmp/mock-screenshot.png"

    # --- actions ---
    def _record(self, name: str, arg: object) -> bool:
        self.actions.append((name, arg))
        if self.transition is not None:
            self.index = self.transition(name, arg, self.index)
        return True

    def click(self, element: UIElement, button: str = "left", double: bool = False) -> bool:
        name = "double_click" if double else ("right_click" if button == "right" else "click")
        return self._record(name, element.node_id)

    def type_text(self, text: str) -> bool:
        return self._record("type", text)

    def press_key(self, key: str) -> bool:
        return self._record("press_key", key)

    def scroll(self, dx: int, dy: int, element: UIElement | None = None) -> bool:
        return self._record("scroll", dy)

    def drag(self, source: UIElement, target: UIElement, duration: float = 0.4) -> bool:
        return self._record("drag", (source.node_id, target.node_id))

    def highlight(self, element: UIElement, duration_ms: int = 600) -> None:
        self.highlights.append(element.node_id)
