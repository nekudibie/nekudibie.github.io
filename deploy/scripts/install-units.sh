#!/usr/bin/env bash
# Install systemd units for one role, substituting the repo path and user. Idempotent; does not
# start anything unless --enable is given. Usage: deploy/scripts/install-units.sh brain|vault|desk [--enable]
set -euo pipefail
ROLE="${1:-}"; ENABLE="${2:-}"
cd "$(dirname "$0")/../.."
REPO=$(pwd); USER_NAME=$(id -un)
[ -n "$ROLE" ] || { echo "usage: $0 brain|vault|desk [--enable]" >&2; exit 2; }
[ -x "$REPO/.venv/bin/companion-api" ] || [ -x "$REPO/.venv/bin/companion-vault" ] || [ -x "$REPO/.venv/bin/companion-audio" ] || { echo "run uv sync first (no .venv found)" >&2; exit 2; }
render() { sed -e "s|__REPO__|$REPO|g" -e "s|__USER__|$USER_NAME|g" -e "s|__API_URL__|${COMPANION_API_URL:-http://127.0.0.1:8710}|g" -e "s|__MIC__|${COMPANION_MIC:-default}|g" -e "s|__SPEAKER__|${COMPANION_SPEAKER:-default}|g" "$1"; }
case "$ROLE" in
  brain) UNITS="companion-api.service companion-worker.service companion-backup.service companion-backup.timer"; SCOPE=system;;
  vault) UNITS="companion-vault.service companion-backup.service companion-backup.timer"; SCOPE=system;;
  desk)  UNITS="companion-audio.service"; SCOPE=user;;
  *) echo "unknown role $ROLE" >&2; exit 2;;
esac
if [ "$SCOPE" = system ]; then
  for u in $UNITS; do render "deploy/systemd/$u" | sudo tee "/etc/systemd/system/$u" >/dev/null; echo "installed /etc/systemd/system/$u"; done
  sudo systemctl daemon-reload
  if [ "$ENABLE" = "--enable" ]; then for u in $UNITS; do sudo systemctl enable --now "$u"; done; fi
else
  mkdir -p "$HOME/.config/systemd/user"
  for u in $UNITS; do render "deploy/systemd/$u" > "$HOME/.config/systemd/user/$u"; echo "installed ~/.config/systemd/user/$u"; done
  systemctl --user daemon-reload
  if [ "$ENABLE" = "--enable" ]; then systemctl --user enable --now $UNITS; loginctl enable-linger "$USER_NAME" || true; fi
fi
echo "done. Status: systemctl $([ "$SCOPE" = user ] && echo --user) status ${UNITS%% *}"
