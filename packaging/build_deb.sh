#!/usr/bin/env bash
# Build the Movo .deb package.
#
# Assembles a staging tree from packaging/deb + the app/ source, sets the right
# permissions on the DEBIAN maintainer scripts, and runs dpkg-deb.
#
# Usage: packaging/build_deb.sh [output_dir]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEB_SRC="$REPO_ROOT/packaging/deb"
OUT_DIR="${1:-$REPO_ROOT/dist}"

VERSION="$(grep -m1 '^Version:' "$DEB_SRC/DEBIAN/control" | awk '{print $2}')"
PKG="movo_${VERSION}_all"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo ">> Staging package tree in $STAGE"
cp -r "$DEB_SRC/." "$STAGE/"

# Install the application source under /usr/lib/movo/app.
mkdir -p "$STAGE/usr/lib/movo"
( cd "$REPO_ROOT" && find app -name '__pycache__' -prune -o -type f -print ) | while read -r f; do
    dest="$STAGE/usr/lib/movo/$f"
    mkdir -p "$(dirname "$dest")"
    cp "$REPO_ROOT/$f" "$dest"
done

# Ship license and readme as package docs.
DOC_DEST="$STAGE/usr/share/doc/movo"
mkdir -p "$DOC_DEST"
cp "$REPO_ROOT/LICENSE" "$DOC_DEST/copyright"
cp "$REPO_ROOT/README.md" "$DOC_DEST/README.md"

# Permissions: dirs 755, files 644, maintainer scripts + launcher 755.
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"
chmod 755 "$STAGE/usr/bin/movo"

# Compute installed size (KiB) and inject into control.
INSTALLED_SIZE="$(du -sk "$STAGE" | awk '{print $1}')"
if ! grep -q '^Installed-Size:' "$STAGE/DEBIAN/control"; then
    printf 'Installed-Size: %s\n' "$INSTALLED_SIZE" >> "$STAGE/DEBIAN/control"
fi

mkdir -p "$OUT_DIR"
echo ">> Building $PKG.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT_DIR/$PKG.deb"

echo ">> Built $OUT_DIR/$PKG.deb"
dpkg-deb --info "$OUT_DIR/$PKG.deb"
echo ">> Contents:"
dpkg-deb --contents "$OUT_DIR/$PKG.deb"
