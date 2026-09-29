#!/usr/bin/env bash
# Validate a built .deb: structural checks plus a real dpkg install/remove on a
# CI runner. Kept separate from build so it can run against any artifact.
#
# Usage: packaging/validate_deb.sh path/to/package.deb
set -euo pipefail

DEB="${1:?usage: validate_deb.sh <package.deb>}"

echo ">> dpkg-deb --info"
dpkg-deb --info "$DEB"

echo ">> Verifying required control fields"
info="$(dpkg-deb --info "$DEB")"
for field in "Package:" "Version:" "Architecture:" "Depends:" "Description:"; do
    echo "$info" | grep -q "$field" || { echo "MISSING $field"; exit 1; }
done

echo ">> Verifying payload contains the app entry point and launcher"
contents="$(dpkg-deb --contents "$DEB")"
echo "$contents" | grep -q "usr/lib/jev-desktop-agent/app/main.py" || { echo "missing app/main.py"; exit 1; }
echo "$contents" | grep -q "usr/bin/jev-desktop-agent" || { echo "missing launcher"; exit 1; }
echo "$contents" | grep -q "usr/share/applications/jev-desktop-agent.desktop" || { echo "missing desktop entry"; exit 1; }
echo "$contents" | grep -q "jev-desktop-agent.svg" || { echo "missing icon"; exit 1; }

if command -v lintian >/dev/null 2>&1; then
    echo ">> lintian (informational; warnings do not fail the build)"
    lintian --no-tag-display-limit "$DEB" || true
fi

# On a Debian/Ubuntu runner, do a real install then removal.
if command -v dpkg >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
    echo ">> Installing (dependencies resolved via apt-get -f)"
    dpkg -i "$DEB" || apt-get install -f -y
    echo ">> Checking the launcher is on PATH"
    command -v jev-desktop-agent
    echo ">> Removing"
    dpkg -r jev-desktop-agent
else
    echo ">> Skipping real install (needs root); structural checks passed"
fi

echo ">> Validation OK"
