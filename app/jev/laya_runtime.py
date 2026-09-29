"""Local Laya runtime manager.

Laya is an open-weight System One model that runs on the user's own machine. The
``laya`` PyPI package's ``serve`` extra provides a ``laya-serve`` command that
exposes TypeSafe's exact ``POST /v1/systemone`` wire contract, so Movo's decision
engine talks to it through the same ``typesafe-sdk`` with only the base URL
changed.

This manager owns everything local and heavy, kept out of the agent loop:

* installing ``laya[serve]`` into Movo's per-user virtualenv on demand,
* starting / health-checking / stopping the local ``laya-serve`` subprocess
  (the model checkpoint downloads automatically on first inference / preload).

Install and download stream their **real** output through a progress callback —
no output is swallowed or relabelled — and an optional interactive-terminal path
shows the whole thing live. Nothing requires root; installs go into
``~/.local/share/movo``.
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

# The correct PyPI package + extra that ships the laya-serve HTTP server.
# (There is no 'laya-server' distribution — installing that fails with
# "No matching distribution found", which earlier looked like a network error.)
_LAYA_REQUIREMENT = "laya[serve]"
_HEALTH_PATH = "/"

# Map our checkpoint names to laya-serve's LAYA_MODELS identifiers.
_MODEL_ALIASES = {
    "laya": "english",
    "laya-multilingual": "multilingual",
    "laya-typed-decisions": "typed-decisions",
}


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
        vp = _venv_python()
        return str(vp) if vp.exists() else sys.executable

    def _serve_cli(self) -> str:
        vb = _venv_bin("laya-serve")
        if vb.exists():
            return str(vb)
        return shutil.which("laya-serve") or "laya-serve"

    def is_installed(self) -> bool:
        """True if the laya package (with serve extra) is importable."""
        try:
            out = subprocess.run(
                [self._python(), "-c", "import laya, laya.serve"],
                capture_output=True,
                timeout=20,
            )
            if out.returncode == 0:
                return True
        except Exception:
            pass
        return _venv_bin("laya-serve").exists() or bool(shutil.which("laya-serve"))

    def checkpoint_present(self) -> bool:
        """True if the checkpoint's weights are already in the HF cache."""
        cache = os.environ.get("HF_HUB_CACHE") or os.path.expanduser(
            "~/.cache/huggingface/hub"
        )
        # The English checkpoint lives at the repo root; variants under it.
        marker = Path(cache) / "models--convaiinnovations--laya"
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
    def _stream(self, cmd: list[str], progress: ProgressCb, env: dict | None = None) -> int:
        """Run a command, streaming each output line to the progress callback.

        Returns the exit code. The real stdout/stderr is surfaced verbatim so
        the user sees the actual failure, not a guessed cause.
        """
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env or os.environ.copy(),
            )
        except Exception as exc:
            progress(f"could not launch: {type(exc).__name__}: {exc}")
            return 127
        assert proc.stdout is not None
        tail: list[str] = []
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                tail.append(line)
                tail[:] = tail[-40:]
                progress(line)
        proc.wait()
        if proc.returncode != 0 and tail:
            _log.warning("command failed (%d): %s", proc.returncode, " | ".join(tail[-4:]))
        return proc.returncode

    def ensure_installed(self, progress: ProgressCb | None = None) -> bool:
        """Install laya[serve] into the per-user venv, surfacing real output."""
        p = progress or (lambda _m: None)
        if self.is_installed():
            p("Laya runtime already installed.")
            return True
        py = self._python()
        p(f"Installing {_LAYA_REQUIREMENT} with {py} …")
        self._stream([py, "-m", "pip", "install", "--upgrade", "pip"], p)
        rc = self._stream([py, "-m", "pip", "install", _LAYA_REQUIREMENT], p)
        if rc != 0:
            p(f"Install failed (pip exit {rc}). See the log above for the real error.")
            return False
        if not self.is_installed():
            p("Install finished but the laya package is still not importable.")
            return False
        p("Laya runtime installed.")
        return True

    def ensure_checkpoint(self, progress: ProgressCb | None = None) -> bool:
        """Trigger a one-time checkpoint download via a tiny routing/predict call.

        laya downloads weights on first inference, so we warm the cache with a
        minimal predict. Output streams through the callback.
        """
        p = progress or (lambda _m: None)
        if self.checkpoint_present():
            p("Model already downloaded.")
            return True
        p(f"Downloading the {self._checkpoint} model (~850 MB, one-time)…")
        model_alias = _MODEL_ALIASES.get(self._checkpoint, "english")
        code = (
            "import laya;"
            "a=laya.load('convaiinnovations/laya');"
            "a.predict('warm up',"
            "{'ok':{'type':'noul','instructions':'warm up'}});"
            "print('checkpoint ready')"
        )
        rc = self._stream([self._python(), "-c", code], p)
        if rc != 0 or not self.checkpoint_present():
            p("Model download did not complete. See the log above.")
            return False
        p(f"Model {model_alias} downloaded.")
        return True

    # --- server lifecycle ------------------------------------------------
    def _serve_env(self) -> dict:
        env = os.environ.copy()
        env["LAYA_HOST"] = "127.0.0.1"
        env["LAYA_PORT"] = str(self._port)
        env["LAYA_PRELOAD"] = "1"
        env["LAYA_MODELS"] = _MODEL_ALIASES.get(self._checkpoint, "english")
        return env

    def start(self, progress: ProgressCb | None = None, timeout_s: float = 90.0) -> bool:
        """Start laya-serve and wait until it answers the health check."""
        p = progress or (lambda _m: None)
        if self._ping():
            p("Laya server already running.")
            return True
        p("Starting local Laya server…")
        try:
            self._proc = subprocess.Popen(
                [self._serve_cli()],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._serve_env(),
            )
        except Exception as exc:
            _log.warning("could not launch laya-serve: %s", exc)
            p(f"Could not start Laya: {type(exc).__name__}: {exc}")
            return False

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                p(f"Laya server exited (code {self._proc.returncode}).")
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

    # --- interactive terminal -------------------------------------------
    def open_interactive_setup(self) -> bool:
        """Open a real terminal that runs the setup with live, scrolling logs.

        Preferred when the user wants to watch the full install/download output.
        Returns True if a terminal was launched.
        """
        py = self._python()
        # A self-contained shell snippet that installs, warms the checkpoint,
        # and pauses so the user can read the result.
        script = (
            f'echo "Movo — setting up Laya locally"; '
            f'"{py}" -m pip install --upgrade pip; '
            f'"{py}" -m pip install "{_LAYA_REQUIREMENT}" && '
            f'"{py}" -c "import laya; a=laya.load(\'convaiinnovations/laya\'); '
            f"a.predict('warm up', {{'ok':{{'type':'noul','instructions':'warm up'}}}}); "
            f'print(\'Laya is ready.\')"; '
            f'echo; echo "Done. You can close this window."; '
            f'read -p "Press Enter to close…" _'
        )
        for term in (
            ["x-terminal-emulator", "-e"],
            ["gnome-terminal", "--"],
            ["konsole", "-e"],
            ["xterm", "-e"],
        ):
            exe = shutil.which(term[0])
            if not exe:
                continue
            try:
                if term[0] == "gnome-terminal":
                    subprocess.Popen([exe, "--", "bash", "-lc", script])
                else:
                    subprocess.Popen([exe] + term[1:] + ["bash", "-lc", script])
                return True
            except Exception:
                continue
        return False
