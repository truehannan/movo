"""Proven Linux/X11 computer-use engine.

Adapted from tak-uukti/linux-computer-use (MIT), whose bridge is verified
end-to-end on real apps (gnome-calculator, gedit). It translates the desktop via
the AT-SPI accessibility tree into elements with role / name / bounds /
capabilities, and performs actions.

Two changes from the upstream bridge, both fallbacks so it also works where the
CLI tools are absent:

* input uses ``xdotool`` when present, otherwise ``pynput`` (both proven);
* screenshots use ``scrot`` when present, otherwise ``mss``.

The AT-SPI translation itself is kept faithful to the upstream (which is what
makes it find, e.g., all 26 calculator buttons): target the app by PID, keep the
INTERESTING_ROLES, cap the walk at 200 elements / depth 12, and fall back from
SCREEN to WINDOW+offset coordinates for GTK4 / Xwayland.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any

from app.diagnostics.logging import get_logger

_log = get_logger()

# --- optional AT-SPI --------------------------------------------------------
_ATSPI = None
try:  # pragma: no cover - import guarded
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    Atspi.set_timeout(800, 1500)
    _ATSPI = Atspi
except Exception as _e:  # pragma: no cover
    _log.warning("AT-SPI not available: %s", type(_e).__name__)

# --- optional input backends ------------------------------------------------
_HAVE_XDOTOOL = shutil.which("xdotool") is not None
_HAVE_WMCTRL = shutil.which("wmctrl") is not None
_HAVE_SCROT = shutil.which("scrot") is not None

_mouse = _keyboard = None
if not _HAVE_XDOTOOL:
    try:  # pragma: no cover - env dependent
        from pynput.keyboard import Controller as _Kb
        from pynput.mouse import Controller as _Mouse

        _mouse = _Mouse()
        _keyboard = _Kb()
    except Exception as _e:  # pragma: no cover
        _log.warning("pynput not available: %s", type(_e).__name__)

_mss = None
if not _HAVE_SCROT:
    try:  # pragma: no cover
        import mss as _mss_mod

        _mss = _mss_mod.MSS() if hasattr(_mss_mod, "MSS") else _mss_mod.mss()
    except Exception:  # pragma: no cover
        _mss = None


INTERESTING_ROLES = {
    "push button",
    "toggle button",
    "link",
    "text",
    "entry",
    "password text",
    "list item",
    "menu item",
    "check box",
    "radio button",
    "combo box",
    "tab",
    "page tab",
    "slider",
    "spin button",
    "tree item",
    "table cell",
    # Read-only readouts (e.g. a calculator's result) — kept so the agent can
    # verify state changes. They are not actionable; the candidate builder ranks
    # them below real controls.
    "label",
    "static",
}

# Roles that are display-only text (not clickable); their name IS their value.
_DISPLAY_ROLES = {"label", "static"}

WALK_MAX_DEPTH = 16
WALK_MAX_ELEMENTS = 300


def have_input() -> bool:
    return _HAVE_XDOTOOL or _mouse is not None


def have_atspi() -> bool:
    return _ATSPI is not None


def _run(cmd: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------- windows ---------------------------------------------------------
def get_active_window_id() -> str | None:
    if not _HAVE_XDOTOOL:
        return None
    try:
        r = _run(["xdotool", "getactivewindow"])
        return r.stdout.strip() or None
    except Exception:
        return None


def list_windows() -> list[dict]:
    if not _HAVE_WMCTRL:
        return []
    out = _run(["wmctrl", "-lpG"]).stdout
    active = get_active_window_id()
    result = []
    for line in out.splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        wid_hex, _desk, pid, x, y, w, h, _host, title = parts
        try:
            wid_int = int(wid_hex, 16)
            pid_int = int(pid)
            x, y, w, h = int(x), int(y), int(w), int(h)
        except ValueError:
            continue
        result.append(
            {
                "wid": wid_int,
                "title": title,
                "pid": pid_int,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "isFocused": active is not None and int(active) == wid_int,
            }
        )
    return result


# ---------- AT-SPI translation ---------------------------------------------
def _active_app_and_frame():
    """Return (app_node, frame_node) for the active window, or (None, None)."""
    if _ATSPI is None:
        return None, None
    try:
        desktop = _ATSPI.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            for j in range(app.get_child_count()):
                fr = app.get_child_at_index(j)
                if fr is None:
                    continue
                try:
                    st = fr.get_state_set()
                    if st and st.contains(_ATSPI.StateType.ACTIVE):
                        return app, fr
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover
        _log.debug("active app/frame failed: %s", e)
    return None, None


def _app_by_pid(pid: int):
    if _ATSPI is None or not pid:
        return None
    try:
        desktop = _ATSPI.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            try:
                if app.get_process_id() == pid:
                    return app
            except Exception:
                continue
    except Exception:
        pass
    return None


def walk_atspi(node, win_x: int = 0, win_y: int = 0) -> list[dict]:
    """Faithful port of the proven walk: translate a subtree into elements."""
    out: list[dict] = []
    if node is None or _ATSPI is None:
        return out

    def visit(n, depth: int) -> None:
        if len(out) >= WALK_MAX_ELEMENTS or depth > WALK_MAX_DEPTH:
            return
        try:
            role = n.get_role_name()
        except Exception:
            role = ""
        try:
            name = n.get_name() or ""
        except Exception:
            name = ""
        if role in INTERESTING_ROLES:
            try:
                ext = n.get_extents(_ATSPI.CoordType.SCREEN)
                ex_x, ex_y, ex_w, ex_h = ext.x, ext.y, ext.width, ext.height
                if (ex_x == 0 and ex_y == 0) or ex_w == 0 or ex_h == 0:
                    try:
                        ew = n.get_extents(_ATSPI.CoordType.WINDOW)
                        if ew.width > 0 and ew.height > 0:
                            ex_x, ex_y = ew.x + win_x, ew.y + win_y
                            ex_w, ex_h = ew.width, ew.height
                    except Exception:
                        pass
                if ex_w > 0 and ex_h > 0:
                    states = set()
                    try:
                        states = {s.value_name for s in n.get_state_set().get_states()}
                    except Exception:
                        pass
                    actions: set[str] = set()
                    try:
                        ai = n.get_action_iface()
                        if ai is not None:
                            for k in range(ai.get_n_actions()):
                                try:
                                    nm_k = _ATSPI.Action.get_action_name(ai, k) or ""
                                except Exception:
                                    nm_k = ""
                                actions.add(nm_k.lower())
                    except Exception:
                        pass
                    editable = role in {
                        "text",
                        "entry",
                        "password text",
                        "spin button",
                        "combo box",
                    }
                    is_display = role in _DISPLAY_ROLES
                    enabled = (
                        "ATSPI_STATE_ENABLED" in states
                        or "ATSPI_STATE_SENSITIVE" in states
                        or not states
                    )
                    out.append(
                        {
                            "role": role,
                            "name": name[:120],
                            "x": ex_x,
                            "y": ex_y,
                            "w": ex_w,
                            "h": ex_h,
                            "canPress": (
                                "press" in actions
                                or "click" in actions
                                or "activate" in actions
                            )
                            and not is_display,
                            "canSetValue": editable,
                            "focused": "ATSPI_STATE_FOCUSED" in states,
                            "enabled": enabled,
                            "editable": editable,
                            "display": is_display,
                            # A read-only readout's text is its name.
                            "value": name[:120] if is_display else None,
                        }
                    )
            except Exception:
                pass
        try:
            nc = n.get_child_count()
        except Exception:
            nc = 0
        for j in range(nc):
            if len(out) >= WALK_MAX_ELEMENTS:
                return
            try:
                child = n.get_child_at_index(j)
            except Exception:
                continue
            if child is not None:
                visit(child, depth + 1)

    visit(node, 0)
    return out


def translate_active_window() -> dict:
    """Observe the active window: window info + translated elements.

    Returns ``{"window": {...}|None, "elements": [...]}``. Prefers PID-based app
    lookup (via wmctrl's active window) and falls back to the ACTIVE frame.
    """
    windows = list_windows()
    focused = next((w for w in windows if w.get("isFocused")), None)

    app = frame = None
    win_x = win_y = 0
    if focused is not None:
        app = _app_by_pid(focused["pid"])
        win_x, win_y = focused["x"], focused["y"]
    if app is None:
        app, frame = _active_app_and_frame()
    # Walk from the frame if we found one, else from the whole app.
    root = frame if frame is not None else app
    elements = walk_atspi(root, win_x, win_y)
    return {"window": focused, "elements": elements}


# ---------- input -----------------------------------------------------------
_BTN = {"left": "1", "middle": "2", "right": "3"}


def click_xy(x: int, y: int, button: str = "left", click_count: int = 1) -> bool:
    if _HAVE_XDOTOOL:
        btn = _BTN.get(button, "1")
        cmd = ["xdotool", "mousemove", str(x), str(y)]
        for _ in range(max(1, int(click_count))):
            cmd += ["click", btn]
        try:
            return _run(cmd, timeout=5).returncode == 0
        except Exception:
            return False
    if _mouse is not None:
        try:
            from pynput.mouse import Button

            b = {"left": Button.left, "right": Button.right, "middle": Button.middle}.get(
                button, Button.left
            )
            _mouse.position = (x, y)
            time.sleep(0.05)
            _mouse.click(b, max(1, int(click_count)))
            return True
        except Exception:
            return False
    return False


def type_text(text: str) -> bool:
    if _HAVE_XDOTOOL:
        try:
            return _run(["xdotool", "type", "--delay", "8", "--", text], timeout=15).returncode == 0
        except Exception:
            return False
    if _keyboard is not None:
        try:
            _keyboard.type(text)
            return True
        except Exception:
            return False
    return False


_KEY_MAP = {
    "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
    "tab": "Tab", "space": "space", "backspace": "BackSpace", "delete": "Delete",
    "del": "Delete", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next",
    "ctrl": "ctrl", "control": "ctrl", "shift": "shift", "alt": "alt",
    "meta": "super", "super": "super", "cmd": "super",
}


def keypress(keys: list[str]) -> bool:
    if not keys:
        return False
    if _HAVE_XDOTOOL:
        mods = {"ctrl", "control", "shift", "alt", "meta", "super", "cmd"}
        try:
            if len(keys) > 1 and all(k.lower() in mods for k in keys[:-1]):
                chord = "+".join(_KEY_MAP.get(k.lower(), k.lower()) for k in keys[:-1])
                last = keys[-1]
                chord += "+" + _KEY_MAP.get(last.lower(), last if len(last) > 1 else last.lower())
                return _run(["xdotool", "key", chord], timeout=5).returncode == 0
            ok = True
            for k in keys:
                parts = k.replace(" ", "").split("+")
                tok = "+".join(_KEY_MAP.get(p.lower(), p if len(p) > 1 else p.lower()) for p in parts)
                ok = ok and _run(["xdotool", "key", tok], timeout=5).returncode == 0
            return ok
        except Exception:
            return False
    if _keyboard is not None:
        try:
            from pynput.keyboard import Key

            named = {
                "return": Key.enter, "enter": Key.enter, "tab": Key.tab,
                "escape": Key.esc, "esc": Key.esc, "space": Key.space,
                "backspace": Key.backspace, "delete": Key.delete,
                "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
            }
            mods = {"ctrl": Key.ctrl, "control": Key.ctrl, "alt": Key.alt,
                    "shift": Key.shift, "super": Key.cmd, "meta": Key.cmd, "cmd": Key.cmd}
            for token in keys:
                parts = token.replace(" ", "").split("+")
                pressed = []
                try:
                    for p in parts:
                        lp = p.lower()
                        if lp in mods:
                            _keyboard.press(mods[lp])
                            pressed.append(mods[lp])
                        elif lp in named:
                            _keyboard.press(named[lp])
                            _keyboard.release(named[lp])
                        else:
                            _keyboard.press(p)
                            _keyboard.release(p)
                finally:
                    for m in reversed(pressed):
                        _keyboard.release(m)
            return True
        except Exception:
            return False
    return False


def scroll_xy(x: int | None, y: int | None, dy: int) -> bool:
    if x is not None and y is not None:
        if _HAVE_XDOTOOL:
            _run(["xdotool", "mousemove", str(x), str(y)])
        elif _mouse is not None:
            try:
                _mouse.position = (x, y)
            except Exception:
                pass
    if _HAVE_XDOTOOL:
        btn = "5" if dy > 0 else "4"
        ticks = max(1, abs(dy) // 120)
        try:
            for _ in range(ticks):
                _run(["xdotool", "click", btn])
            return True
        except Exception:
            return False
    if _mouse is not None:
        try:
            _mouse.scroll(0, -1 if dy > 0 else 1)
            return True
        except Exception:
            return False
    return False


# ---------- screenshot ------------------------------------------------------
def screenshot(path: str) -> str | None:
    if _HAVE_SCROT:
        try:
            if _run(["scrot", "-o", path], timeout=5).returncode == 0:
                return path
        except Exception:
            pass
    if _mss is not None:
        try:
            import mss.tools

            img = _mss.grab(_mss.monitors[0])
            mss.tools.to_png(img.rgb, img.size, output=path)
            return path
        except Exception:
            pass
    return None


def capabilities() -> dict[str, Any]:
    return {
        "atspi": _ATSPI is not None,
        "xdotool": _HAVE_XDOTOOL,
        "wmctrl": _HAVE_WMCTRL,
        "scrot": _HAVE_SCROT,
        "pynput": _mouse is not None,
        "mss": _mss is not None,
        "input": have_input(),
    }
