#!/usr/bin/env bash
# Render the deck and the printed consent sign to PDF with headless Chrome.
# Usage: bash deck/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
render() {
  "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="$2" "file://$PWD/$1" 2>/dev/null
  test -s "$2"
  echo "wrote $2 ($(wc -c <"$2" | tr -d ' ') bytes)"
}
render deck/signer.html deck/signer.pdf
render demo/consent-sign.html demo/consent-sign.pdf
