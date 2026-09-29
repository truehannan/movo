"""``DesktopBackend`` backed by the proven linux-computer-use engine.

This wraps :mod:`app.desktop.lcu_engine` (adapted from tak-uukti/linux-computer-use,
verified on real apps) so the rest of Movo — candidate translation, the model
decision, verification — plugs in unchanged. Observation goes through the proven
AT-SPI walk that actually finds interactive elements (e.g. all calculator
buttons); actions go through xdotool/pynput.
"""

from __future__ import annotations

import tempfile

from app.desktop import lcu_engine as eng
from app.desktop.backend import (
    Bounds,
    DesktopBackend,
    Observation,
    Role,
    UIElement,
    WindowInfo,
)

_ROLE_MAP = {
    "push button": Role.BUTTON,
    "toggle button": Role.BUTTON,
    "link": Role.LINK,
    "text": Role.TEXTBOX,
    "entry": Role.TEXTBOX,
    "password text": Role.TEXTBOX,
    "list item": Role.LISTITEM,
    "menu item": Role.MENUITEM,
    "check box": Role.CHECKBOX,
    "radio button": Role.RADIO,
    "combo box": Role.COMBOBOX,
    "tab": Role.TAB,
    "page tab": Role.TAB,
    "spin button": Role.TEXTBOX,
    "tree item": Role.TREEITEM,
    "table cell": Role.LISTITEM,
    "slider": Role.OTHER,
    "label": Role.LABEL,
    "static": Role.LABEL,
}


def _to_uielement(idx: int, el: dict) -> UIElement:
    role = _ROLE_MAP.get(el["role"], Role.OTHER)
    bounds = Bounds(el["x"], el["y"], el["w"], el["h"])
    return UIElement(
        node_id=f"lcu:{idx}",
        role=role,
        name=el.get("name", ""),
        value=el.get("value"),
        bounds=bounds,
        enabled=bool(el.get("enabled", True)),
        visible=True,
        focusable=True,
        focused=bool(el.get("focused", False)),
        editable=bool(el.get("editable", False)),
        actionable=bool(el.get("canPress") or el.get("canSetValue")),
        raw_role=el.get("role", ""),
    )


class LcuBackend(DesktopBackend):
    """Movo desktop backend on the proven linux-computer-use engine."""

    def __init__(self) -> None:
        self._overlay_cb = None

    # --- observation ---
    def get_active_window(self) -> WindowInfo:
        data = eng.translate_active_window()
        w = data.get("window")
        if not w:
            return WindowInfo()
        return WindowInfo(
            app_name=self._app_name(w),
            title=w.get("title", ""),
            bounds=Bounds(w["x"], w["y"], w["w"], w["h"]),
            pid=w.get("pid"),
        )

    @staticmethod
    def _app_name(w: dict) -> str:
        # wmctrl gives the title; derive a short app name from it when possible.
        title = w.get("title", "")
        return title.split(" - ")[-1].strip() if " - " in title else title

    def get_ui_tree(self) -> Observation:
        data = eng.translate_active_window()
        w = data.get("window")
        window = (
            WindowInfo(
                app_name=self._app_name(w),
                title=w.get("title", ""),
                bounds=Bounds(w["x"], w["y"], w["w"], w["h"]),
                pid=w.get("pid"),
            )
            if w
            else WindowInfo()
        )
        elements = [_to_uielement(i, el) for i, el in enumerate(data.get("elements", []))]
        focused = next((e for e in elements if e.focused), None)
        return Observation(
            window=window,
            elements=elements,
            focused_element=focused,
            accessibility_ok=eng.have_atspi(),
        )

    def screenshot(self, path: str | None = None) -> str | None:
        if path is None:
            import os

            fd, path = tempfile.mkstemp(prefix="movo-shot-", suffix=".png")
            os.close(fd)
        return eng.screenshot(path)

    # --- actions ---
    def click(self, element: UIElement, button: str = "left", double: bool = False) -> bool:
        if element.bounds is None or element.bounds.is_empty():
            return False
        x, y = element.bounds.center
        return eng.click_xy(x, y, button=button, click_count=2 if double else 1)

    def type_text(self, text: str) -> bool:
        return eng.type_text(text)

    def press_key(self, key: str) -> bool:
        # Movo passes 'ctrl+l' or 'Return'; the engine handles chords per token.
        return eng.keypress([key])

    def scroll(self, dx: int, dy: int, element: UIElement | None = None) -> bool:
        x = y = None
        if element and element.bounds and not element.bounds.is_empty():
            x, y = element.bounds.center
        return eng.scroll_xy(x, y, dy)

    def drag(self, source: UIElement, target: UIElement, duration: float = 0.4) -> bool:
        # Not provided by the proven engine's minimal surface; compose from click
        # is unsafe, so report unsupported rather than faking it.
        return False

    # --- visual ---
    def set_overlay_callback(self, cb) -> None:
        self._overlay_cb = cb

    def highlight(self, element: UIElement, duration_ms: int = 600) -> None:
        if self._overlay_cb is not None and element.bounds is not None:
            try:
                self._overlay_cb(element.bounds, duration_ms)
            except Exception:
                pass

    def close(self) -> None:
        return None
