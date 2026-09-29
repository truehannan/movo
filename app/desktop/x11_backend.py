"""Real Linux (X11) desktop backend (PROMPT sections 6, 7, 13, 22, 23, 32).

Observation is primarily via AT-SPI (the semantic accessibility tree); input is
via ``pynput`` (with an ``xdotool`` fallback for keys); screenshots via ``mss``.
This is genuine computer use — it controls real applications, never simulated
UI (PROMPT section 32).

Every external dependency is imported lazily and defensively, so importing this
module never fails on a machine missing a piece; the missing capability simply
degrades (reported by :mod:`app.diagnostics.capabilities`).
"""

from __future__ import annotations

import subprocess
import tempfile
import time

from app.desktop.backend import (
    Bounds,
    DesktopBackend,
    Observation,
    Role,
    UIElement,
    WindowInfo,
)
from app.diagnostics.logging import get_logger

_log = get_logger()

# Map AT-SPI role names to our compact Role set.
_ROLE_MAP = {
    "push button": Role.BUTTON,
    "toggle button": Role.BUTTON,
    "button": Role.BUTTON,
    "text": Role.TEXTBOX,
    "entry": Role.TEXTBOX,
    "password text": Role.TEXTBOX,
    "link": Role.LINK,
    "check box": Role.CHECKBOX,
    "radio button": Role.RADIO,
    "menu": Role.MENU,
    "menu item": Role.MENUITEM,
    "check menu item": Role.MENUITEM,
    "radio menu item": Role.MENUITEM,
    "page tab": Role.TAB,
    "list item": Role.LISTITEM,
    "combo box": Role.COMBOBOX,
    "tree item": Role.TREEITEM,
    "table cell": Role.LISTITEM,
    "icon": Role.ICON,
    "label": Role.LABEL,
    "heading": Role.HEADING,
}

_MAX_ELEMENTS = 120  # hard cap on how many nodes we walk per observation


def _map_role(raw: str) -> Role:
    return _ROLE_MAP.get(raw.lower(), Role.OTHER)


class X11DesktopBackend(DesktopBackend):
    """AT-SPI + pynput + mss implementation of :class:`DesktopBackend`."""

    def __init__(self) -> None:
        self._atspi = self._init_atspi()
        self._mouse, self._keyboard = self._init_input()
        self._mss = self._init_mss()
        self._overlay = None  # created lazily by highlight()

    # --- lazy dependency init -------------------------------------------
    @staticmethod
    def _init_atspi():
        try:
            import gi

            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi

            Atspi.set_timeout(800, 1500)
            return Atspi
        except Exception as exc:  # pragma: no cover - env dependent
            _log.warning("AT-SPI unavailable: %s", type(exc).__name__)
            return None

    @staticmethod
    def _init_input():
        try:
            from pynput.keyboard import Controller as KbController
            from pynput.mouse import Controller as MouseController

            return MouseController(), KbController()
        except Exception as exc:  # pragma: no cover - env dependent
            _log.warning("pynput unavailable: %s", type(exc).__name__)
            return None, None

    @staticmethod
    def _init_mss():
        try:
            import mss

            return mss.mss()
        except Exception:  # pragma: no cover - env dependent
            return None

    # --- window ----------------------------------------------------------
    def get_active_window(self) -> WindowInfo:
        # Prefer AT-SPI's active frame; fall back to wmctrl/xdotool.
        info = self._active_window_atspi()
        if info is not None:
            return info
        return self._active_window_wmctrl()

    def _active_window_atspi(self) -> WindowInfo | None:
        if self._atspi is None:
            return None
        try:
            desktop = self._atspi.get_desktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app is None:
                    continue
                for j in range(app.get_child_count()):
                    frame = app.get_child_at_index(j)
                    if frame is None:
                        continue
                    state = frame.get_state_set()
                    if state and state.contains(self._atspi.StateType.ACTIVE):
                        bounds = self._extent(frame)
                        return WindowInfo(
                            app_name=app.get_name() or "",
                            title=frame.get_name() or "",
                            bounds=bounds,
                        )
        except Exception as exc:  # pragma: no cover - env dependent
            _log.debug("active window via AT-SPI failed: %s", exc)
        return None

    @staticmethod
    def _active_window_wmctrl() -> WindowInfo:
        try:
            out = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if out.returncode == 0:
                return WindowInfo(title=out.stdout.strip())
        except Exception:
            pass
        return WindowInfo()

    # --- observation -----------------------------------------------------
    def get_ui_tree(self) -> Observation:
        window = self.get_active_window()
        elements: list[UIElement] = []
        focused: UIElement | None = None
        accessibility_ok = self._atspi is not None

        if self._atspi is not None:
            try:
                frame = self._active_frame()
                if frame is not None:
                    counter = [0]
                    self._walk(frame, elements, counter, depth=0)
                    focused = next((e for e in elements if e.focused), None)
            except Exception as exc:  # pragma: no cover - env dependent
                _log.debug("tree walk failed: %s", exc)
                accessibility_ok = False

        return Observation(
            window=window,
            elements=elements,
            focused_element=focused,
            accessibility_ok=accessibility_ok,
        )

    def _active_frame(self):
        desktop = self._atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            for j in range(app.get_child_count()):
                frame = app.get_child_at_index(j)
                if frame is None:
                    continue
                state = frame.get_state_set()
                if state and state.contains(self._atspi.StateType.ACTIVE):
                    return frame
        return None

    def _walk(self, node, out: list[UIElement], counter: list[int], depth: int) -> None:
        """Depth-bounded, count-bounded walk of the accessibility subtree."""
        if counter[0] >= _MAX_ELEMENTS or depth > 12:
            return
        try:
            child_count = node.get_child_count()
        except Exception:
            return

        el = self._to_element(node, counter[0])
        if el is not None:
            out.append(el)
            counter[0] += 1

        for i in range(min(child_count, 60)):
            if counter[0] >= _MAX_ELEMENTS:
                return
            try:
                child = node.get_child_at_index(i)
            except Exception:
                continue
            if child is not None:
                self._walk(child, out, counter, depth + 1)

    def _to_element(self, node, idx: int) -> UIElement | None:
        try:
            raw_role = node.get_role_name() or ""
            role = _map_role(raw_role)
            state = node.get_state_set()

            visible = bool(state.contains(self._atspi.StateType.SHOWING)) if state else True
            enabled = bool(state.contains(self._atspi.StateType.ENABLED)) if state else True
            focused = bool(state.contains(self._atspi.StateType.FOCUSED)) if state else False
            focusable = bool(state.contains(self._atspi.StateType.FOCUSABLE)) if state else False
            editable = bool(state.contains(self._atspi.StateType.EDITABLE)) if state else False

            name = node.get_name() or ""
            description = node.get_description() or ""
            value = self._value(node)
            actionable = self._actionable(node) or role in {
                Role.BUTTON, Role.LINK, Role.MENUITEM, Role.TAB, Role.CHECKBOX,
                Role.RADIO, Role.COMBOBOX, Role.LISTITEM, Role.TREEITEM,
            }
            bounds = self._extent(node)

            # Skip pure structural containers with no useful info.
            if role is Role.OTHER and not name and not description and not actionable:
                return None

            return UIElement(
                node_id=f"atspi:{idx}:{id(node)}",
                role=role,
                name=name,
                description=description,
                value=value,
                bounds=bounds,
                enabled=enabled,
                visible=visible,
                focusable=focusable,
                focused=focused,
                editable=editable,
                actionable=actionable,
                raw_role=raw_role,
            )
        except Exception:
            return None

    def _value(self, node) -> str | None:
        try:
            vi = node.get_value_iface()
            if vi is not None:
                return str(vi.get_current_value())
        except Exception:
            pass
        try:
            ti = node.get_text_iface()
            if ti is not None:
                n = ti.get_character_count()
                if n and n < 200:
                    return ti.get_text(0, n)
        except Exception:
            pass
        return None

    def _actionable(self, node) -> bool:
        try:
            ai = node.get_action_iface()
            return ai is not None and ai.get_n_actions() > 0
        except Exception:
            return False

    def _extent(self, node) -> Bounds | None:
        try:
            ci = node.get_component_iface()
            if ci is None:
                return None
            rect = ci.get_extents(self._atspi.CoordType.SCREEN)
            return Bounds(rect.x, rect.y, rect.width, rect.height)
        except Exception:
            return None

    # --- screenshot ------------------------------------------------------
    def screenshot(self, path: str | None = None) -> str | None:
        if path is None:
            fd, path = tempfile.mkstemp(prefix="jev-shot-", suffix=".png")
            import os

            os.close(fd)
        if self._mss is not None:
            try:
                import mss.tools

                monitor = self._mss.monitors[0]
                img = self._mss.grab(monitor)
                mss.tools.to_png(img.rgb, img.size, output=path)
                return path
            except Exception:  # pragma: no cover
                pass
        for tool in (["scrot", path], ["gnome-screenshot", "-f", path]):
            try:
                if subprocess.run(tool, timeout=3).returncode == 0:
                    return path
            except Exception:
                continue
        return None

    # --- actions ---------------------------------------------------------
    def _move_click(self, x: int, y: int, button: str, double: bool) -> bool:
        if self._mouse is None:
            return self._xdotool_click(x, y, button, double)
        from pynput.mouse import Button

        btn = {"left": Button.left, "right": Button.right, "middle": Button.middle}.get(
            button, Button.left
        )
        self._mouse.position = (x, y)
        time.sleep(0.05)
        self._mouse.click(btn, 2 if double else 1)
        return True

    @staticmethod
    def _xdotool_click(x: int, y: int, button: str, double: bool) -> bool:
        btn = {"left": "1", "middle": "2", "right": "3"}.get(button, "1")
        try:
            subprocess.run(["xdotool", "mousemove", str(x), str(y)], timeout=2, check=True)
            args = ["xdotool", "click"]
            if double:
                args += ["--repeat", "2"]
            args.append(btn)
            return subprocess.run(args, timeout=2).returncode == 0
        except Exception:
            return False

    def click(self, element: UIElement, button: str = "left", double: bool = False) -> bool:
        # Prefer the semantic accessibility action when it is a simple activation.
        if button == "left" and not double and self._do_atspi_action(element):
            return True
        if element.bounds is None or element.bounds.is_empty():
            return False
        x, y = element.bounds.center
        return self._move_click(x, y, button, double)

    def _do_atspi_action(self, element: UIElement) -> bool:
        # Resolving a UIElement back to a live node is not stored across calls;
        # for robustness we rely on coordinates. Semantic-action clicking can be
        # added by caching nodes, but coordinate clicks work broadly.
        return False

    def type_text(self, text: str) -> bool:
        if self._keyboard is None:
            try:
                return subprocess.run(
                    ["xdotool", "type", "--clearmodifiers", text], timeout=5
                ).returncode == 0
            except Exception:
                return False
        try:
            self._keyboard.type(text)
            return True
        except Exception:
            return False

    def press_key(self, key: str) -> bool:
        combo = [k.strip() for k in key.replace("-", "+").split("+") if k.strip()]
        if self._keyboard is None:
            try:
                xkey = "+".join(combo)
                return subprocess.run(["xdotool", "key", xkey], timeout=3).returncode == 0
            except Exception:
                return False
        try:
            from pynput.keyboard import Key

            mods = {
                "ctrl": Key.ctrl, "control": Key.ctrl, "alt": Key.alt,
                "shift": Key.shift, "cmd": Key.cmd, "super": Key.cmd,
            }
            named = {
                "return": Key.enter, "enter": Key.enter, "tab": Key.tab,
                "escape": Key.esc, "esc": Key.esc, "space": Key.space,
                "backspace": Key.backspace, "delete": Key.delete,
                "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
            }
            pressed = []
            try:
                for part in combo:
                    p = part.lower()
                    if p in mods:
                        self._keyboard.press(mods[p])
                        pressed.append(mods[p])
                    elif p in named:
                        self._keyboard.press(named[p])
                        self._keyboard.release(named[p])
                    else:
                        self._keyboard.press(part)
                        self._keyboard.release(part)
            finally:
                for m in reversed(pressed):
                    self._keyboard.release(m)
            return True
        except Exception:
            return False

    def scroll(self, dx: int, dy: int, element: UIElement | None = None) -> bool:
        if self._mouse is None:
            try:
                direction = "5" if dy > 0 else "4"
                return subprocess.run(["xdotool", "click", direction], timeout=2).returncode == 0
            except Exception:
                return False
        try:
            # pynput scroll: positive dy scrolls up, so negate.
            self._mouse.scroll(0, -1 if dy > 0 else 1)
            return True
        except Exception:
            return False

    def drag(self, source: UIElement, target: UIElement, duration: float = 0.4) -> bool:
        if (
            self._mouse is None
            or source.bounds is None
            or target.bounds is None
            or source.bounds.is_empty()
            or target.bounds.is_empty()
        ):
            return False
        from pynput.mouse import Button

        sx, sy = source.bounds.center
        tx, ty = target.bounds.center
        try:
            self._mouse.position = (sx, sy)
            time.sleep(0.05)
            self._mouse.press(Button.left)
            steps = 20
            for i in range(1, steps + 1):
                self._mouse.position = (
                    int(sx + (tx - sx) * i / steps),
                    int(sy + (ty - sy) * i / steps),
                )
                time.sleep(duration / steps)
            self._mouse.release(Button.left)
            return True
        except Exception:
            return False

    # --- window focus / highlight ---------------------------------------
    def focus_window(self, window: WindowInfo) -> bool:  # pragma: no cover - env dependent
        if not window.title:
            return False
        try:
            return subprocess.run(
                ["wmctrl", "-a", window.title], timeout=2
            ).returncode == 0
        except Exception:
            return False

    def highlight(self, element: UIElement, duration_ms: int = 600) -> None:  # pragma: no cover
        """Draw a transient rectangle over the element (PROMPT section 19).

        Implemented by the UI overlay when running under Qt; the backend keeps a
        no-op fallback so headless use is safe.
        """
        if self._overlay_cb is not None and element.bounds is not None:
            try:
                self._overlay_cb(element.bounds, duration_ms)
            except Exception:
                pass

    _overlay_cb = None

    def set_overlay_callback(self, cb) -> None:
        """Wire the UI overlay so :meth:`highlight` shows a real rectangle."""
        self._overlay_cb = cb

    def close(self) -> None:  # pragma: no cover
        if self._mss is not None:
            try:
                self._mss.close()
            except Exception:
                pass
