"""Startup capability check (PROMPT section 22).

Reports which desktop capabilities are available so the UI can show a
diagnostic status and the agent can pick a safe strategy. All probes are
best-effort and must never raise.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass
class Capabilities:
    session_type: str = "unknown"  # "x11", "wayland", or "unknown"
    accessibility: bool = False
    screenshot: bool = False
    mouse_input: bool = False
    keyboard_input: bool = False
    window_detection: bool = False

    def all_ok(self) -> bool:
        return all(
            [
                self.accessibility or self.screenshot,
                self.mouse_input,
                self.keyboard_input,
                self.window_detection,
            ]
        )

    def as_rows(self) -> list[tuple[str, bool]]:
        return [
            ("Accessibility (AT-SPI)", self.accessibility),
            ("Screenshot", self.screenshot),
            ("Mouse input", self.mouse_input),
            ("Keyboard input", self.keyboard_input),
            ("Active window detection", self.window_detection),
        ]


def _session_type() -> str:
    st = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if st in ("x11", "wayland"):
        return st
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def _probe_accessibility() -> bool:
    try:
        import gi  # type: ignore

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def _probe_screenshot() -> bool:
    try:
        import mss  # type: ignore  # noqa: F401

        return True
    except Exception:
        return bool(shutil.which("scrot") or shutil.which("gnome-screenshot"))


def _probe_input() -> bool:
    try:
        import pynput  # type: ignore  # noqa: F401

        return True
    except Exception:
        return bool(shutil.which("xdotool"))


def _probe_window_detection(session: str) -> bool:
    if _probe_accessibility():
        return True
    if session == "x11":
        return bool(shutil.which("xdotool") or shutil.which("wmctrl"))
    return False


def check_capabilities() -> Capabilities:
    session = _session_type()
    # Prefer the proven engine's own capability report when it imports cleanly,
    # since that is exactly what the agent will use to act.
    try:
        from app.desktop import lcu_engine as eng

        caps = eng.capabilities()
        return Capabilities(
            session_type=session,
            accessibility=bool(caps.get("atspi")),
            screenshot=bool(caps.get("scrot") or caps.get("mss")),
            mouse_input=bool(caps.get("input")),
            keyboard_input=bool(caps.get("input")),
            window_detection=bool(caps.get("wmctrl") or caps.get("atspi")),
        )
    except Exception:
        pass
    accessibility = _probe_accessibility()
    screenshot = _probe_screenshot()
    inp = _probe_input()
    return Capabilities(
        session_type=session,
        accessibility=accessibility,
        screenshot=screenshot,
        mouse_input=inp,
        keyboard_input=inp,
        window_detection=_probe_window_detection(session),
    )
