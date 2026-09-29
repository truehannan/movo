"""One-click auto-update via the GitHub Releases API (no extra infrastructure).

Movo checks the repository's latest release, compares its tag to the running
version, and — on the user's click — downloads that release's ``.deb`` asset to
a temp file and installs it with ``pkexec apt-get install`` (a graphical sudo
prompt). ``apt``/``dpkg`` replaces the package in place, so the old version is
removed automatically. The temp ``.deb`` is deleted afterward, leaving no files
behind.

Everything network-facing lives here and is pure/functional where possible so
the version comparison and release parsing are unit-testable without the net.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass

from app.diagnostics.logging import get_logger

_log = get_logger()

# Owner/repo for the release feed. Kept here so a fork can repoint it.
GITHUB_REPO = "truehannan/movo"
_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version(text: str) -> tuple[int, ...]:
    """Parse a version/tag like 'v1.2.3' or '0.2.0' into a comparable tuple.

    Non-numeric suffixes are ignored so 'v0.2.0' and '0.2.0' compare equal.
    Unparseable input yields (0,) so it always compares as oldest.
    """
    if not text:
        return (0,)
    m = re.findall(r"\d+", text)
    if not m:
        return (0,)
    return tuple(int(x) for x in m[:4])


def is_newer(candidate: str, current: str) -> bool:
    """True if ``candidate`` is a strictly newer version than ``current``."""
    return parse_version(candidate) > parse_version(current)


@dataclass
class ReleaseInfo:
    version: str
    tag: str
    deb_url: str | None
    notes: str = ""
    html_url: str = ""

    @property
    def has_asset(self) -> bool:
        return bool(self.deb_url)


def _pick_deb_asset(assets: list[dict]) -> str | None:
    for a in assets:
        name = a.get("name", "")
        if name.endswith(".deb"):
            url = a.get("browser_download_url")
            if url:
                return url
    return None


def fetch_latest_release(timeout: float = 6.0) -> ReleaseInfo | None:
    """Query the GitHub Releases API for the latest release. None on failure."""
    try:
        req = urllib.request.Request(
            _API_LATEST,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "movo-updater"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network dependent
        _log.debug("release check failed: %s", type(exc).__name__)
        return None
    return _release_from_json(data)


def _release_from_json(data: dict) -> ReleaseInfo | None:
    tag = data.get("tag_name") or data.get("name") or ""
    if not tag:
        return None
    return ReleaseInfo(
        version=tag.lstrip("v"),
        tag=tag,
        deb_url=_pick_deb_asset(data.get("assets", []) or []),
        notes=(data.get("body") or "")[:2000],
        html_url=data.get("html_url", ""),
    )


@dataclass
class UpdateCheck:
    current: str
    latest: ReleaseInfo | None

    @property
    def update_available(self) -> bool:
        return self.latest is not None and is_newer(self.latest.version, self.current)


def check_for_update(current_version: str) -> UpdateCheck:
    return UpdateCheck(current=current_version, latest=fetch_latest_release())


def download_deb(url: str, progress=None) -> str | None:
    """Download a .deb to a temp file; return its path, or None on failure."""
    p = progress or (lambda _m: None)
    try:
        fd, path = tempfile.mkstemp(prefix="movo-update-", suffix=".deb")
        os.close(fd)
        p("Downloading update…")
        req = urllib.request.Request(url, headers={"User-Agent": "movo-updater"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(path, "wb") as out:
            shutil.copyfileobj(resp, out)
        return path
    except Exception as exc:  # pragma: no cover - network dependent
        _log.warning("update download failed: %s", type(exc).__name__)
        p(f"Download failed: {type(exc).__name__}")
        return None


def install_deb(deb_path: str, progress=None) -> bool:
    """Install a .deb with a graphical sudo prompt; remove the temp file after.

    Uses ``pkexec apt-get install -y ./file.deb`` which upgrades the package in
    place (removing the previously installed version). Falls back to ``dpkg -i``
    when apt is unavailable.
    """
    p = progress or (lambda _m: None)
    if not os.path.exists(deb_path):
        return False
    installer = shutil.which("pkexec")
    ok = False
    try:
        p("Requesting permission to install…")
        if installer and shutil.which("apt-get"):
            proc = subprocess.run(
                [installer, "apt-get", "install", "-y", deb_path], timeout=600
            )
            ok = proc.returncode == 0
        elif installer:
            proc = subprocess.run([installer, "dpkg", "-i", deb_path], timeout=600)
            ok = proc.returncode == 0
        else:
            p("pkexec not available; install the .deb manually.")
            ok = False
    except Exception as exc:  # pragma: no cover - env dependent
        _log.warning("update install failed: %s", type(exc).__name__)
        p(f"Install failed: {type(exc).__name__}")
        ok = False
    finally:
        try:
            os.remove(deb_path)  # no bloat: temp file never lingers
        except OSError:
            pass
    if ok:
        p("Update installed. Restart Movo to use the new version.")
    return ok


def download_and_install(release: ReleaseInfo, progress=None) -> bool:
    """Full one-click flow: download the release .deb and install it."""
    p = progress or (lambda _m: None)
    if not release.deb_url:
        p("This release has no .deb asset yet.")
        return False
    path = download_deb(release.deb_url, p)
    if not path:
        return False
    return install_deb(path, p)
