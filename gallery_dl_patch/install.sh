#!/usr/bin/env bash
# Install the modified gallery-dl Zerochan extractor.
# This adds page_html support for categorized tag parsing.
#
# Usage: bash install.sh
# Requires: gallery-dl installed via pip

set -e

PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find gallery-dl extractor directory
SITE_PACKAGES=$(python3 -c "import gallery_dl; import os; print(os.path.dirname(gallery_dl.__file__))" 2>/dev/null)
if [ -z "$SITE_PACKAGES" ]; then
    echo "Error: gallery-dl not found. Install it first:"
    echo "  pip install gallery-dl"
    exit 1
fi

TARGET="$SITE_PACKAGES/extractor/zerochan.py"
BACKUP="$TARGET.bak"

if [ -f "$TARGET" ]; then
    echo "Backing up original to $BACKUP"
    cp "$TARGET" "$BACKUP"
fi

cp "$PATCH_DIR/zerochan.py" "$TARGET"
echo "Installed patched zerochan.py to $TARGET"
echo "Done. gallery-dl will now support --page-html for zerochan."
