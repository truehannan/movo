"""Manifest validation (PROMPT §27, §36).

Verifies both generated manifests are valid JSON, use MV3, declare the correct
persistent-sidebar mechanism per browser, and do NOT over-request permissions.
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_DIR = _ROOT / "extension" / "manifest"


def _load(name: str) -> dict:
    return json.loads((_MANIFEST_DIR / name).read_text())


def test_chromium_manifest_uses_side_panel():
    m = _load("chromium.json")
    assert m["manifest_version"] == 3
    assert "side_panel" in m
    assert "default_popup" not in json.dumps(m)  # popup is NOT the primary UI
    assert "sidePanel" in m["permissions"]
    # No broad host permissions.
    assert "<all_urls>" not in json.dumps(m)


def test_firefox_manifest_uses_sidebar_action():
    m = _load("firefox.json")
    assert m["manifest_version"] == 3
    assert "sidebar_action" in m
    assert "sidePanel" not in json.dumps(m)  # Chrome API must not appear in FF
    gecko = m["browser_specific_settings"]["gecko"]
    assert gecko["id"]
    # AMO (Nov 2025+) requires a data-collection declaration; we collect none.
    assert gecko["data_collection_permissions"]["required"] == ["none"]
    # data_collection_permissions requires Firefox 140+.
    assert float(gecko["strict_min_version"]) >= 140.0


def test_manifests_share_name_and_description():
    c = _load("chromium.json")
    f = _load("firefox.json")
    assert c["name"] == f["name"]
    assert c["description"] == f["description"]
