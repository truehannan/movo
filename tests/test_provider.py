"""Tests for the provider abstraction and Laya wiring (no heavy downloads).

Verifies that the controller picks the right client per provider, that the Laya
runtime reports status and starts an already-running server without touching the
network, and that LayaClient targets the local base URL.
"""

from __future__ import annotations

import pytest

from app.config.secrets import SecretStore
from app.config.settings import Settings


def test_settings_provider_helpers():
    s = Settings(provider="laya", laya_port=8731)
    assert s.is_local
    assert s.laya_base_url == "http://127.0.0.1:8731"
    j = Settings(provider="jev")
    assert not j.is_local


def test_laya_runtime_status_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    from app.jev.laya_runtime import LayaRuntime

    rt = LayaRuntime(port=8799, checkpoint="laya")
    st = rt.status()
    # Nothing installed/downloaded/running in a clean temp env.
    assert st.port == 8799
    assert st.running is False
    assert st.checkpoint_present is False


def test_laya_client_targets_local(monkeypatch):
    """LayaClient must build a TypeSafeClient pointed at the local base URL."""
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def system_one(self, *a, **k):
            raise AssertionError("should not call")

        def close(self):
            pass

    import app.jev.client as clientmod

    monkeypatch.setattr(clientmod, "TypeSafeClient", FakeClient, raising=False)
    # Patch the lazy import inside __init__ by injecting into typesafe_sdk.
    import typesafe_sdk

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", FakeClient, raising=False)

    from app.jev.client import LayaClient

    LayaClient(base_url="http://127.0.0.1:8731", checkpoint="laya")
    assert captured["base_url"] == "http://127.0.0.1:8731"
    assert captured["api_key"] == "local"
    assert captured["model"] == "laya"


def test_controller_builds_laya_client_without_key(monkeypatch, tmp_path):
    """With provider=laya the controller builds a client without an API key."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    from app.agent.controller import TaskController
    from app.desktop.backend import Observation, WindowInfo
    from app.desktop.mock_backend import MockDesktopBackend
    from app.safety.emergency_stop import EmergencyStop

    backend = MockDesktopBackend(screens=[Observation(window=WindowInfo())])
    settings = Settings(provider="laya", laya_port=8731)
    secrets = SecretStore(prefer_keyring=False)  # deliberately no key
    ctrl = TaskController(backend, settings, secrets, EmergencyStop())

    # Avoid actually launching a server: stub the runtime start + client build.
    import typesafe_sdk

    from app.jev import client as clientmod

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            pass

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", FakeClient, raising=False)

    # Stub the runtime so is_running() is True and start() is a no-op.
    rt = ctrl._laya_runtime()
    monkeypatch.setattr(rt, "is_running", lambda: True)

    built = ctrl.build_client()
    assert isinstance(built, clientmod.LayaClient)


def test_controller_jev_requires_key(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    from app.agent.controller import TaskController
    from app.desktop.backend import Observation, WindowInfo
    from app.desktop.mock_backend import MockDesktopBackend
    from app.safety.emergency_stop import EmergencyStop

    backend = MockDesktopBackend(screens=[Observation(window=WindowInfo())])
    ctrl = TaskController(
        backend, Settings(provider="jev"), SecretStore(prefer_keyring=False), EmergencyStop()
    )
    with pytest.raises(RuntimeError):
        ctrl.build_client()
