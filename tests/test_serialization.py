"""Tests for state serialization, config loading, and secret masking."""

from __future__ import annotations

import os

from app.config.secrets import SecretStore, mask_key
from app.config.settings import ConfidenceThresholds, Settings
from app.jev.questions import TARGET_NONE, build_state


def test_build_state_is_compact_and_named():
    state = build_state(
        goal="Open Firefox",
        app_name="firefox",
        window_title="New Tab",
        candidate_block="0: role=button name=\"Menu\"",
        recent_history=["1. CLICK → Menu [VERIFIED]"] * 10,
        last_verification="state changed",
    )
    assert state["goal"] == "Open Firefox"
    assert state["current_app"] == "firefox"
    # History is trimmed to the last few entries.
    assert len(state["recent_actions"]) == 5
    assert state["last_verification"] == "state changed"


def test_build_state_omits_optional_fields():
    state = build_state("g", "a", "w", "c")
    assert "recent_actions" not in state
    assert "last_verification" not in state


def test_mask_key_never_reveals_full_key():
    assert mask_key("sk-abcdef123456") == "sk-...3456"
    assert mask_key("") == "<none>"
    assert mask_key("short") == "****"


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    s = Settings(max_steps=7, thresholds=ConfidenceThresholds(high=0.8))
    s.save()
    loaded = Settings.load()
    assert loaded.max_steps == 7
    assert loaded.thresholds.high == 0.8


def test_settings_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    loaded = Settings.load()
    assert loaded.model == "jev-latest"


def test_secret_store_file_backend_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    store = SecretStore(prefer_keyring=False)
    assert not store.has_api_key()
    store.set_api_key("sk-secret-value-123456")
    assert store.get_api_key() == "sk-secret-value-123456"
    # File permissions are owner-only.
    mode = oct(os.stat(tmp_path / "jev-desktop-agent" / "secrets.json").st_mode)[-3:]
    assert mode == "600"
    store.clear_api_key()
    assert not store.has_api_key()


def test_secret_store_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-from-env-000000")
    store = SecretStore(prefer_keyring=False)
    assert store.get_api_key() == "sk-from-env-000000"


def test_target_none_constant():
    assert TARGET_NONE == "NONE"
