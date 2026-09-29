"""Non-secret application settings (PROMPT sections 20, 34).

Settings persist to a JSON file in the user config directory. Secrets never
live here; the API key is handled exclusively by :mod:`app.config.secrets`.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "jev-desktop-agent"


@dataclass
class ConfidenceThresholds:
    """Application decision thresholds (PROMPT section 34).

    These are ordinary values tuned in code, not asked of Jev. ``high`` and
    above executes automatically; between ``low`` and ``high`` the agent
    reobserves/reconsiders; below ``low`` it blocks or asks for confirmation.
    """

    high: float = 0.75
    low: float = 0.45
    # A Noul probability at/above this counts as a confident "yes".
    noul_yes: float = 0.70


@dataclass
class Settings:
    """User-configurable, non-secret settings."""

    model: str = "jev-latest"
    max_steps: int = 25
    max_retries_per_action: int = 2
    action_timeout_s: float = 8.0
    task_timeout_s: float = 180.0
    confirmation_mode: bool = True  # confirm destructive actions
    screenshot_fallback: bool = True
    debug_logging: bool = False
    prefer_keyring: bool = True
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)

    # --- persistence -----------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return _config_dir() / "settings.json"

    @classmethod
    def load(cls) -> Settings:
        p = cls.path()
        if not p.exists():
            return cls()
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cls()
        thresholds = ConfidenceThresholds(**(data.pop("thresholds", {}) or {}))
        known = {f for f in cls.__dataclass_fields__ if f != "thresholds"}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(thresholds=thresholds, **kwargs)

    def save(self) -> None:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
