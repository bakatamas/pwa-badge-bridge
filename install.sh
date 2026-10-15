#!/usr/bin/env bash
# Installs the PWA Badge Bridge native host for Chromium-based browsers (current user).
set -euo pipefail

HOST_NAME="hu.celest.pwa_badge_bridge"
EXT_ID="albabpmnaedopmjgfiaennhhfjcbcinm"
SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin/pwa-badge-bridge"
CFG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CFG_HOME/pwa-badge-bridge"

# Browser config folders; the host manifest goes into each one that exists.
BROWSERS=(
  "google-chrome"
  "google-chrome-beta"
  "google-chrome-unstable"
  "chromium"
  "BraveSoftware/Brave-Browser"
  "vivaldi"
  "microsoft-edge"
)

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "python3 not found." >&2
  exit 1
fi
if ! "$PY" -c "from gi.repository import Gio" 2>/dev/null; then
  echo "Missing PyGObject. Install python-gobject (Arch) or python3-gi (Debian/Ubuntu)." >&2
  exit 1
fi

install -Dm755 "$SRC/host/pwa_badge_bridge.py" "$BIN"
# Pin the interpreter we just checked; the browser may start the host with a different PATH.
sed -i "1s|.*|#!$PY|" "$BIN"

found=0
for b in "${BROWSERS[@]}"; do
  [ -d "$CFG_HOME/$b" ] || continue
  mkdir -p "$CFG_HOME/$b/NativeMessagingHosts"
  cat > "$CFG_HOME/$b/NativeMessagingHosts/$HOST_NAME.json" <<EOF
{
  "name": "$HOST_NAME",
  "description": "PWA Badge Bridge",
  "path": "$BIN",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$EXT_ID/"]
}
EOF
  echo "Registered host for: $b"
  found=1
done
if [ "$found" = 0 ]; then
  echo "No supported browser config folder found in $CFG_HOME." >&2
  echo "Start your browser once, then run this script again." >&2
  exit 1
fi

echo
if [ -t 0 ]; then
  # Interactive: let the user pick apps. A broken config shouldn't abort the install.
  "$BIN" --setup || true
else
  echo "Not running in a terminal; skipping app selection."
  echo "Run '$BIN --setup' later to choose apps (config: $CONFIG_DIR/config.json)."
fi

echo
echo "Next: load '$SRC/extension' in your browser's extensions page (Developer mode → Load unpacked)."
echo "To add more apps later, run: $BIN --setup"
