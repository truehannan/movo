"""The ``DesktopBackend`` interface and the shared data models it works with.

This module deliberately contains no X11/AT-SPI/PyAutoGUI imports so it can be
imported anywhere (including in tests and on CI) without a display server. The
concrete X11 implementation lives in :mod:`app.desktop.x11_backend`.

The interface keeps the rest of the application independent of any specific
computer-use backend (PROMPT section 23).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    """A small, normalised set of element roles the agent reasons about.

    AT-SPI exposes dozens of roles; we collapse them into this compact set so
    candidate serialization stays short and Jev's choices stay bounded.
    """

    BUTTON = "button"
    TEXTBOX = "textbox"
    LINK = "link"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    MENU = "menu"
    MENUITEM = "menuitem"
    TAB = "tab"
    LISTITEM = "listitem"
    COMBOBOX = "combobox"
    TREEITEM = "treeitem"
    ICON = "icon"
    LABEL = "label"
    HEADING = "heading"
    OTHER = "other"


@dataclass(frozen=True)
class Bounds:
    """Screen-space rectangle in pixels."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0


@dataclass
class UIElement:
    """A single element observed from the accessibility tree.

    ``node_id`` is a stable-ish identifier the backend can resolve back to a
    live accessible object (or to coordinates) when an action targets it.
    """

    node_id: str
    role: Role
    name: str = ""
    description: str = ""
    value: str | None = None
    bounds: Bounds | None = None
    enabled: bool = True
    visible: bool = True
    focusable: bool = False
    focused: bool = False
    editable: bool = False
    actionable: bool = False
    # Raw AT-SPI role name, kept for diagnostics only (never sent to Jev).
    raw_role: str = ""

    def short_label(self) -> str:
        label = self.name or self.description or self.value or ""
        label = label.strip().replace("\n", " ")
        return label[:80]


@dataclass
class WindowInfo:
    """The active window/application context."""

    app_name: str = ""
    title: str = ""
    bounds: Bounds | None = None
    pid: int | None = None


@dataclass
class Observation:
    """A single desktop observation: window context plus observed elements.

    ``screenshot_path`` is populated only when a screenshot fallback is taken;
    it is used for the visual overlay and debugging, never sent to Jev.
    """

    window: WindowInfo
    elements: list[UIElement] = field(default_factory=list)
    focused_element: UIElement | None = None
    screenshot_path: str | None = None
    accessibility_ok: bool = True

    def summary(self) -> str:
        """A one-line human/log summary of the observation."""
        return (
            f"app={self.window.app_name!r} title={self.window.title!r} "
            f"elements={len(self.elements)} "
            f"focused={self.focused_element.short_label() if self.focused_element else None!r}"
        )


class DesktopBackend(ABC):
    """Abstract low-level desktop control + observation.

    Concrete implementations (X11, or an external computer-use backend) provide
    these primitives. The agent loop and candidate builder depend only on this
    interface, so a :class:`~app.desktop.mock_backend.MockDesktopBackend` can
    drive the whole loop deterministically in tests.
    """

    # --- observation -----------------------------------------------------
    @abstractmethod
    def get_active_window(self) -> WindowInfo:
        """Return the currently active window/application."""

    @abstractmethod
    def get_ui_tree(self) -> Observation:
        """Observe the active window and return a filtered element set."""

    @abstractmethod
    def screenshot(self, path: str | None = None) -> str | None:
        """Capture a screenshot to ``path`` (or a temp file); return the path."""

    # --- actions ---------------------------------------------------------
    @abstractmethod
    def click(self, element: UIElement, button: str = "left", double: bool = False) -> bool:
        """Click a resolved element. Returns True on success."""

    @abstractmethod
    def type_text(self, text: str) -> bool:
        """Type text into the currently focused editable element."""

    @abstractmethod
    def press_key(self, key: str) -> bool:
        """Send a key or shortcut, e.g. ``'Return'`` or ``'ctrl+l'``."""

    @abstractmethod
    def scroll(self, dx: int, dy: int, element: UIElement | None = None) -> bool:
        """Scroll the view. ``dy`` positive scrolls down."""

    @abstractmethod
    def drag(self, source: UIElement, target: UIElement, duration: float = 0.4) -> bool:
        """Drag from a source element to a target element."""

    # --- window / visual -------------------------------------------------
    def focus_window(self, window: WindowInfo) -> bool:  # pragma: no cover - optional
        """Bring a window to the foreground. Optional; default no-op."""
        return False

    def highlight(self, element: UIElement, duration_ms: int = 600) -> None:  # pragma: no cover
        """Briefly highlight an element on the real desktop. Optional."""
        return None

    # --- lifecycle -------------------------------------------------------
    def close(self) -> None:  # pragma: no cover - optional
        """Release any resources held by the backend."""
        return None
