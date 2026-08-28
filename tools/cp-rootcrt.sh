#!/bin/sh
# Copies the Root CA certificate into the mewly app's resources.
#
# Usage: tools/cp-rootcrt.sh <mewly repository path>
#   e.g.  tools/cp-rootcrt.sh ~/projects/mewly
#
# Source: $ROOT_DIR/root.crt (default ~/.babycat-ca, created by provision-device.sh init)
# Destination: <mewly>/android/app/src/main/res/raw/babycat_ca.crt
# The mewly app must be rebuilt after copying for the change to take effect.
set -eu

MEWLY="${1:?mewly repository path is required (e.g. ~/projects/mewly)}"
ROOT_DIR="${ROOT_DIR:-$HOME/.babycat-ca}"
SRC="$ROOT_DIR/root.crt"
DEST_DIR="$MEWLY/android/app/src/main/res/raw"
DEST="$DEST_DIR/babycat_ca.crt"

[ -f "$SRC" ] || { echo "Root CA certificate not found: $SRC (run tools/provision-device.sh init first)" >&2; exit 1; }
[ -d "$DEST_DIR" ] || { echo "mewly resource directory not found: $DEST_DIR" >&2; exit 1; }

cp "$SRC" "$DEST"
echo "Copied: $DEST"
openssl x509 -in "$DEST" -noout -subject -enddate
