#!/usr/bin/env bash
# Expose the local core (SIGNER_PORT, default 8000) over HTTPS/WSS with a cloudflared quick tunnel,
# so the hud-web Web App on GitHub Pages can reach it from the glasses (CONTRACTS §7).
# Prints the Web App URL with ?core=wss://…/ws/events and the fb-viewapp:// link to open it on the glasses.
# Usage: core/tools/tunnel.sh [port] [web_app_url]
set -euo pipefail

port="${1:-${SIGNER_PORT:-8000}}"
app_url="${2:-${SIGNER_WEBAPP_URL:-}}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Install: brew install cloudflared (macOS) or see https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
  exit 1
fi

log="$(mktemp -t signer-tunnel.XXXXXX)"
cleanup() { [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true; rm -f "$log"; }
trap cleanup EXIT INT TERM

echo "Starting quick tunnel to http://127.0.0.1:${port} ..."
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${port}" >"$log" 2>&1 &
pid=$!

url=""
for _ in $(seq 1 60); do
  url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$log" | head -n 1 || true)"
  [ -n "$url" ] && break
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "cloudflared exited:" >&2
    cat "$log" >&2
    exit 1
  fi
  sleep 1
done
[ -n "$url" ] || { echo "No tunnel URL after 60 s:" >&2; cat "$log" >&2; exit 1; }

wss="wss://${url#https://}/ws/events"
echo "Core (HTTPS): ${url}"
echo "Events (WSS): ${wss}"
if [ -n "$app_url" ]; then
  sep="?"; case "$app_url" in *\?*) sep="&" ;; esac
  full="${app_url}${sep}core=${wss}"
  echo "Web App:      ${full}"
  enc="$(python -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$full")"
  echo "Glasses link: fb-viewapp://web_app_deep_link?appName=Signer&appUrl=${enc}"
else
  echo "Pass the GitHub Pages URL of hud-web as the 2nd argument (or SIGNER_WEBAPP_URL) to print the Web App link."
fi
echo "Ctrl-C to stop."
wait "$pid"
