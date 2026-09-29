"""Tests for the auto-updater's pure logic (version compare, release parsing)."""

from __future__ import annotations

from app.diagnostics.updater import (
    UpdateCheck,
    _pick_deb_asset,
    _release_from_json,
    is_newer,
    parse_version,
)


def test_parse_version_handles_prefix_and_suffix():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("0.2.0") == (0, 2, 0)
    assert parse_version("v0.2.0-rc1") == (0, 2, 0, 1)
    assert parse_version("") == (0,)
    assert parse_version("garbage") == (0,)


def test_is_newer():
    assert is_newer("0.2.0", "0.1.1")
    assert is_newer("v1.0.0", "0.9.9")
    assert not is_newer("0.1.0", "0.1.0")
    assert not is_newer("0.1.0", "0.2.0")
    # v-prefix is irrelevant
    assert not is_newer("v0.1.0", "0.1.0")


def test_pick_deb_asset():
    assets = [
        {"name": "notes.txt", "browser_download_url": "u1"},
        {"name": "movo_0.2.0_all.deb", "browser_download_url": "u2"},
    ]
    assert _pick_deb_asset(assets) == "u2"
    assert _pick_deb_asset([]) is None
    assert _pick_deb_asset([{"name": "x.zip", "browser_download_url": "z"}]) is None


def test_release_from_json():
    data = {
        "tag_name": "v0.2.0",
        "body": "notes",
        "html_url": "http://example/releases/v0.2.0",
        "assets": [{"name": "movo_0.2.0_all.deb", "browser_download_url": "http://d/movo.deb"}],
    }
    rel = _release_from_json(data)
    assert rel is not None
    assert rel.version == "0.2.0"
    assert rel.tag == "v0.2.0"
    assert rel.has_asset
    assert rel.deb_url == "http://d/movo.deb"


def test_release_from_json_no_tag_returns_none():
    assert _release_from_json({}) is None


def test_update_check_available():
    from app.diagnostics.updater import ReleaseInfo

    newer = ReleaseInfo(version="0.3.0", tag="v0.3.0", deb_url="u")
    older = ReleaseInfo(version="0.1.0", tag="v0.1.0", deb_url="u")
    assert UpdateCheck(current="0.2.0", latest=newer).update_available
    assert not UpdateCheck(current="0.2.0", latest=older).update_available
    assert not UpdateCheck(current="0.2.0", latest=None).update_available
