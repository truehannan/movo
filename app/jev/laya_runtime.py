"""Local Laya runtime manager.

Laya is an open-weight System One model that runs on the user's own machine. We
run it behind a small HTTP server that implements TypeSafe's exact ``/v1/systemone``
wire contract (``laya-server``), so Movo's existing decision engine talks to it
through the same ``typesafe-sdk`` with only the base URL changed.

This manager owns everything local and heavy, kept out of the agent loop:

* installing ``laya-server`` into Movo's per-user virtualenv on demand,
* downloading the model checkpoint (once, into the shared Hugging Face cache),
* starting / health-checking / stopping the local server subprocess.

All long operations report progress through a callback so the UI can show it,
and nothing here requires root — installs go into ``~/.local/share/movo``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.diagnostics.logging import get_logger

_log = get_logger()

ProgressCb = Callable[[str], None]

# The pip package that provides the Jev-wire-compatible local server + CLI.
_LAYA_PACKAGE = "laya-server"
_HEALTH_PATH = "/"


def _data_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "movo"


def _venv_dir() -> Path:
    return _data_home() / "venv"


def _venv_python() -> Path:
    return _venv_dir() / "bin" / "python3"


def _venv_bin(name: str) -> Path:
    return _venv_dir() / "bin" / name


@dataclass
class LayaStatus:
    installed: bool
    checkpoint_present: bool
    running: bool
    port: int
    detail: str = ""


class LayaRuntime:
    """Manages the local Laya server for one checkpoint/port."""

    def __init__(self, port: int, checkpoint: str = "laya") -> None:
        self._port = port
        self._checkpoint = checkpoint
        self._proc: subprocess.Popen | None = None

    # --- introspection ---------------------------------------------------
    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _python(self) -> str:
        """The interpreter to use: the per-user venv if present, else current."""
        vp = _venv_python()
        return str(vp) if vp.exists() else sys.executable

    def is_installed(self) -> bool:
        """True if laya-server is importable in the target interpreter."""
        try:
            out = subprocess.run(
                [self._python(), "-c", "import server.api"],  # laya-server package
                capture_output=True,
                timeout=15,
            )
            if out.returncode == 0:
                return True
        except Exception:
            pass
        # Fallback: the console script exists.
        return _venv_bin("laya-server").exists() or bool(shutil.which("laya-server"))

    def checkpoint_present(self) -> bool:
        """True if the checkpoint is already in the shared HF cache."""
        cache = os.environ.get("HF_HUB_CACHE") or os.path.expanduser(
            "~/.cache/huggingface/hub"
        )
        marker = Path(cache) / f"models--convaiinnovations--{self._checkpoint}"
        return marker.exists()

    def is_running(self) -> bool:
        return self._ping()

    def status(self) -> LayaStatus:
        return LayaStatus(
            installed=self.is_installed(),
            checkpoint_present=self.checkpoint_present(),
            running=self.is_running(),
            port=self._port,
        )

    # --- install ---------------------------------------------------------
    def ensure_installed(self, progress: ProgressCb | None = None) -> bool:
        """Install laya-server into the per-user venv if it is not present."""
        p = progress or (lambda _m: None)
        if self.is_installed():
            return True
        py = self._python()
        p("Installing Laya runtime… (one-time, a few hundred MB)")
        try:
            subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"], timeout=120)
            proc = subprocess.run(
                [py, "-m", "pip", "install", _LAYA_PACKAGE],
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if proc.returncode != 0:
                _log.warning("laya install failed: %s", proc.stderr[-300:])
                p("Laya install failed. Check your connection and retry.")
                return False
        except Exception as exc:  # pragma: no cover - network dependent
            _log.warning("laya install error: %s", exc)
            p(f"Laya install error: {type(exc).__name__}")
            return False
        p("Laya runtime installed.")
        return True

    def ensure_checkpoint(self, progress: ProgressCb | None = None) -> bool:
        """Download the checkpoint into the HF cache if it is not present."""
        p = progress or (lambda _m: None)
        if self.checkpoint_present():
            return True
        p(f"Downloading the {self._checkpoint} model (~850 MB, one-time)…")
        try:
            proc = subprocess.run(
                [self._laya_cli(), "pull", self._checkpoint],
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if proc.returncode != 0:
                _log.warning("checkpoint pull failed: %s", proc.stderr[-300:])
                p("Model download failed. Check your connection and retry.")
                return False
        except Exception as exc:  # pragma: no cover - network dependent
            _log.warning("checkpoint pull error: %s", exc)
            p(f"Model download error: {type(exc).__name__}")
            return False
        p("Model downloaded.")
        return True

    def _laya_cli(self) -> str:
        vb = _venv_bin("laya-server")
        if vb.exists():
            return str(vb)
        found = shutil.which("laya-server")
        return found or "laya-server"

    # --- server lifecycle ------------------------------------------------
    def start(self, progress: ProgressCb | None = None, timeout_s: float = 60.0) -> bool:
        """Start the local server and wait until it answers the health check."""
        p = progress or (lambda _m: None)
        if self._ping():
            return True
        p("Starting local Laya server…")
        env = dict(os.environ)
        try:
            self._proc = subprocess.Popen(
                [
                    self._laya_cli(),
                    "serve",
                    self._checkpoint,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self._port),
                    "--no-browser",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        except Exception as exc:  # pragma: no cover - env dependent
            _log.warning("could not launch laya server: %s", exc)
            p(f"Could not start Laya: {type(exc).__name__}")
            return False

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                p("Laya server exited unexpectedly.")
                return False
            if self._ping():
                p("Laya is ready.")
                return True
            time.sleep(0.5)
        p("Laya did not become ready in time.")
        return False

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None

    def _ping(self) -> bool:
        try:
            req = urllib.request.Request(self.base_url + _HEALTH_PATH, method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    # --- one-shot bring-up ----------------------------------------------
    def provision_and_start(self, progress: ProgressCb | None = None) -> bool:
        """Install, download, and start — the full first-time bring-up."""
        return (
            self.ensure_installed(progress)
            and self.ensure_checkpoint(progress)
            and self.start(progress)
        )
