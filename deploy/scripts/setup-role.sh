#!/usr/bin/env bash
# Prepare this host for one role: validates the machine, installs the Python workspace for that
# role only, creates config/.env from the examples (never overwrites), and installs units.
# Usage: deploy/scripts/setup-role.sh brain|vault|desk
set -euo pipefail
ROLE="${1:-}"; [ -n "$ROLE" ] || { echo "usage: $0 brain|vault|desk" >&2; exit 2; }
cd "$(dirname "$0")/../.."
deploy/scripts/check-host.sh || { echo "host check failed" >&2; exit 1; }
command -v uv >/dev/null || { echo "install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1; }
case "$ROLE" in
  brain) PKGS="--package companion-api --package companion-worker"; EXTRAS="${COMPANION_EXTRAS:---extra stt --extra tts}";;
  vault) PKGS="--package companion-vault"; EXTRAS="";;
  desk)  PKGS="--package companion-audio"; EXTRAS="${COMPANION_EXTRAS:-}";;
  *) echo "unknown role $ROLE" >&2; exit 2;;
esac
echo "== uv sync for role $ROLE"
# shellcheck disable=SC2086
uv sync --frozen $PKGS $EXTRAS || uv sync $PKGS $EXTRAS
[ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "created .env (fill in tokens; make them with: uv run companion-api make-token)"; }
[ -f config/local.yaml ] || { cp config/example.yaml config/local.yaml; echo "created config/local.yaml (edit providers/hosts for role $ROLE)"; }
if [ "$ROLE" = brain ] && command -v npm >/dev/null; then (cd apps/desk && npm ci --no-audit --no-fund && npm run build); else [ "$ROLE" = brain ] && echo "npm not found: build apps/desk elsewhere and copy apps/desk/dist here"; fi
if [ "$ROLE" = desk ]; then
  command -v arecord >/dev/null || echo "install audio tools: sudo apt install alsa-utils"
  mkdir -p "$HOME/.config/autostart"
  API_URL="${COMPANION_API_URL:-http://127.0.0.1:8710}"
  BROWSER=$(command -v chromium-browser || command -v chromium || command -v firefox || true)
  if [ -n "$BROWSER" ]; then
    cat > "$HOME/.config/autostart/companion-kiosk.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Companion kiosk
Exec=$BROWSER --kiosk --noerrdialogs --disable-session-crashed-bubble --app=$API_URL
X-GNOME-Autostart-enabled=true
DESK
    echo "kiosk autostart written for $API_URL (remove ~/.config/autostart/companion-kiosk.desktop to disable)"
  else
    echo "no chromium/firefox found for the kiosk; install one (sudo apt install chromium) and re-run"
  fi
fi
deploy/scripts/install-units.sh "$ROLE"
echo
echo "Next: edit config/local.yaml and .env, then: uv run companion-api check-config  and  deploy/scripts/install-units.sh $ROLE --enable"
