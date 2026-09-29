"""Isolated secret storage for the TypeSafe/Jev API key (PROMPT sections 20, 21).

The API key MUST never appear in logs. This module is the *only* place that
reads or writes the raw key. It prefers the OS keyring when available and falls
back to a restricted-permission local file (mode 0600) so keyring support can
be added/removed without touching the rest of the app.

The storage backend is chosen at construction time and hidden behind
:class:`SecretStore`, so callers never know or care where the key lives.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

_SERVICE = "jev-desktop-agent"
_ACCOUNT = "typesafe-api-key"
_ENV_VAR = "TYPESAFE_API_KEY"


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "jev-desktop-agent"


def mask_key(key: str | None) -> str:
    """Return a log-safe masked form of a key, e.g. ``sk-...a1b2``.

    Used anywhere a key might otherwise be printed. Never returns the raw key.
    """
    if not key:
        return "<none>"
    key = key.strip()
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}...{key[-4:]}"


class SecretStore:
    """Stores exactly one secret: the TypeSafe API key.

    Resolution order for reads: explicit stored value, then the
    ``TYPESAFE_API_KEY`` environment variable (so power users and CI can inject
    it without persisting). Writes go to the keyring if present, else the file.
    """

    def __init__(self, *, prefer_keyring: bool = True) -> None:
        self._keyring = None
        if prefer_keyring:
            try:  # keyring is an optional dependency
                import keyring  # type: ignore

                # Touch the backend so we fail over to file storage if the
                # keyring backend is a non-functional stub.
                keyring.get_keyring()
                self._keyring = keyring
            except Exception:
                self._keyring = None

        self._file = _config_dir() / "secrets.json"

    # --- backend name (for diagnostics; never exposes the value) --------
    @property
    def backend_name(self) -> str:
        return "keyring" if self._keyring is not None else "file"

    # --- read ------------------------------------------------------------
    def get_api_key(self) -> str | None:
        if self._keyring is not None:
            try:
                val = self._keyring.get_password(_SERVICE, _ACCOUNT)
                if val:
                    return val
            except Exception:
                pass
        val = self._read_file_key()
        if val:
            return val
        env = os.environ.get(_ENV_VAR)
        return env.strip() if env else None

    def has_api_key(self) -> bool:
        return bool(self.get_api_key())

    # --- write -----------------------------------------------------------
    def set_api_key(self, key: str) -> None:
        key = key.strip()
        if not key:
            raise ValueError("API key must not be empty")
        if self._keyring is not None:
            try:
                self._keyring.set_password(_SERVICE, _ACCOUNT, key)
                return
            except Exception:
                # Fall through to file storage.
                pass
        self._write_file_key(key)

    def clear_api_key(self) -> None:
        if self._keyring is not None:
            try:
                self._keyring.delete_password(_SERVICE, _ACCOUNT)
            except Exception:
                pass
        try:
            if self._file.exists():
                self._file.unlink()
        except OSError:
            pass

    # --- file backend ----------------------------------------------------
    def _read_file_key(self) -> str | None:
        try:
            with open(self._file, encoding="utf-8") as fh:
                data = json.load(fh)
            val = data.get("api_key")
            return val.strip() if isinstance(val, str) and val.strip() else None
        except (OSError, ValueError):
            return None

    def _write_file_key(self, key: str) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        # Write then tighten permissions to owner read/write only.
        with open(self._file, "w", encoding="utf-8") as fh:
            json.dump({"api_key": key}, fh)
        try:
            os.chmod(self._file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
