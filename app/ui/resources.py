"""Locate bundled UI assets (the Movo logo) in both dev and packaged layouts."""

from __future__ import annotations

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def logo_path() -> str | None:
    """Absolute path to the Movo logo PNG, or None if it is missing."""
    candidates = [
        _ASSETS_DIR / "movo.png",
        # Packaged icon location as a fallback.
        Path("/usr/share/icons/hicolor/256x256/apps/movo.png"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None
