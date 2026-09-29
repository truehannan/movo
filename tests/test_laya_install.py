"""Simulated tests for the Laya install/provision program.

No real pip install or model download happens: subprocess is stubbed to emulate
pip's real behaviour (including the "No matching distribution found" failure the
user originally hit), and the HF cache / venv live under temp dirs. These prove
the runtime surfaces the *real* error text (not a guessed "check your
connection") and that the success path detects install + checkpoint + server.
"""

from __future__ import annotations

import subprocess

import pytest

from app.jev.laya_runtime import LayaRuntime


class _FakePopen:
    """Minimal Popen stand-in that streams canned lines then exits."""

    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout = iter(line + "\n" for line in lines)
        self.returncode = returncode
        self._code = returncode

    def wait(self):
        self.returncode = self._code
        return self._code

    def poll(self):
        return self._code


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    return tmp_path


def test_install_surfaces_real_pip_error(clean_env, monkeypatch):
    """The genuine pip failure text must reach the progress callback."""
    rt = LayaRuntime(port=8799, checkpoint="laya")
    # Not installed in a clean env.
    monkeypatch.setattr(rt, "is_installed", lambda: False)

    real_pip_error = "ERROR: No matching distribution found for laya[serve]"

    def fake_popen(cmd, **kwargs):
        # Emulate `pip install` failing exactly as it did for the user.
        if "pip" in cmd and "install" in cmd and any("laya" in str(c) for c in cmd):
            return _FakePopen([real_pip_error], returncode=1)
        return _FakePopen(["ok"], returncode=0)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    captured: list[str] = []
    ok = rt.ensure_installed(progress=captured.append)

    assert ok is False
    # The REAL error is surfaced verbatim — not a hardcoded connection message.
    assert any(real_pip_error in line for line in captured)
    assert not any("check your connection" in line.lower() for line in captured)


def test_install_success_path(clean_env, monkeypatch):
    rt = LayaRuntime(port=8799, checkpoint="laya")
    # First call (guard) not installed; after "install", report installed.
    states = iter([False, True])

    def is_installed():
        try:
            return next(states)
        except StopIteration:
            return True

    monkeypatch.setattr(rt, "is_installed", is_installed)

    def fake_popen(cmd, **kwargs):
        return _FakePopen(["Successfully installed laya-0.3.21"], returncode=0)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    captured: list[str] = []
    ok = rt.ensure_installed(progress=captured.append)
    assert ok is True
    assert any("Successfully installed" in line for line in captured)


def test_checkpoint_warm_is_skipped_when_present(clean_env, monkeypatch):
    rt = LayaRuntime(port=8799, checkpoint="laya")
    monkeypatch.setattr(rt, "checkpoint_present", lambda: True)
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a) or _FakePopen([], 0))
    ok = rt.ensure_checkpoint(progress=lambda _m: None)
    assert ok is True
    assert calls == []  # no download attempted when already cached


def test_provision_stops_at_first_failure(clean_env, monkeypatch):
    """If install fails, download and start must not run."""
    rt = LayaRuntime(port=8799, checkpoint="laya")
    monkeypatch.setattr(rt, "ensure_installed", lambda progress=None: False)
    started = {"download": False, "start": False}
    monkeypatch.setattr(rt, "ensure_checkpoint", lambda progress=None: started.__setitem__("download", True) or True)
    monkeypatch.setattr(rt, "start", lambda progress=None: started.__setitem__("start", True) or True)
    ok = rt.provision_and_start(progress=lambda _m: None)
    assert ok is False
    assert started == {"download": False, "start": False}


def test_serve_env_uses_configured_port_and_model(clean_env):
    rt = LayaRuntime(port=8731, checkpoint="laya-multilingual")
    env = rt._serve_env()
    assert env["LAYA_PORT"] == "8731"
    assert env["LAYA_HOST"] == "127.0.0.1"
    assert env["LAYA_MODELS"] == "multilingual"
    assert env["LAYA_PRELOAD"] == "1"


def test_start_returns_true_when_already_running(clean_env, monkeypatch):
    rt = LayaRuntime(port=8799)
    monkeypatch.setattr(rt, "_ping", lambda: True)
    assert rt.start(progress=lambda _m: None) is True
