#!/usr/bin/env bash
# Validate a built Movo .deb: structural checks plus a real dpkg install/remove
# on a CI runner.
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

echo ">> Verifying maintainer scripts do no network work (must not hang the installer)"
if dpkg-deb --info "$DEB" | grep -q "postinst"; then
    # Extract control scripts and assert postinst contains no pip/curl/wget.
    tmp="$(mktemp -d)"
    dpkg-deb --control "$DEB" "$tmp"
    if grep -Eq '\b(pip|curl|wget|apt-get)\b' "$tmp/postinst"; then
        echo "postinst performs network work — this can hang the package manager"; exit 1
    fi
    rm -rf "$tmp"
fi

echo ">> Verifying payload contains the app entry point, launcher, icon, desktop entry"
contents="$(dpkg-deb --contents "$DEB")"
echo "$contents" | grep -q "usr/lib/movo/app/main.py" || { echo "missing app/main.py"; exit 1; }
echo "$contents" | grep -q "usr/bin/movo" || { echo "missing launcher"; exit 1; }
echo "$contents" | grep -q "usr/share/applications/movo.desktop" || { echo "missing desktop entry"; exit 1; }
echo "$contents" | grep -q "movo.png" || { echo "missing icon"; exit 1; }

if command -v lintian >/dev/null 2>&1; then
    echo ">> lintian (informational; warnings do not fail the build)"
    lintian --no-tag-display-limit "$DEB" || true
fi

# On a Debian/Ubuntu runner, do a real install then removal.
if command -v dpkg >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
    echo ">> Installing (dependencies resolved via apt-get -f)"
    dpkg -i "$DEB" || apt-get install -f -y
    echo ">> Checking the launcher is on PATH"
    command -v movo
    echo ">> Removing"
    dpkg -r movo
else
    echo ">> Skipping real install (needs root); structural checks passed"
fi

echo ">> Validation OK"
