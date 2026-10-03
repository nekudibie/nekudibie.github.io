#!/usr/bin/env bash
# One-command local start for development (single host, every provider a fixture
# unless you edit config/local.yaml). Idempotent: safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/../.."

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { echo "error: $*" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || die "uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/"
case "$(uname -m)" in x86_64|aarch64|arm64) ;; *) die "unsupported CPU architecture $(uname -m) (need x86_64 or aarch64)";; esac
[ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ] || die "dev.sh supports Linux and macOS"

bold "1/4 Python workspace (uv sync)"
uv sync --all-packages --frozen 2>/dev/null || uv sync --all-packages

bold "2/4 Secrets (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  DESK=$(uv run --no-sync python -c 'from companion_core.auth import generate_token; print(generate_token())')
  ADMIN=$(uv run --no-sync python -c 'from companion_core.auth import generate_token; print(generate_token())')
  sed -i.bak "s|^COMPANION_DESK_TOKEN=.*|COMPANION_DESK_TOKEN=${DESK}|; s|^COMPANION_ADMIN_TOKEN=.*|COMPANION_ADMIN_TOKEN=${ADMIN}|" .env && rm -f .env.bak
  chmod 600 .env
  echo "created .env with fresh desk/admin tokens"
else
  echo ".env already exists (left unchanged)"
fi
[ -f config/local.yaml ] || { cp config/example.yaml config/local.yaml; echo "created config/local.yaml from example"; }

bold "3/4 Desk UI"
if command -v npm >/dev/null 2>&1; then
  if [ ! -d apps/desk/node_modules ]; then (cd apps/desk && npm ci --no-audit --no-fund); fi
  if [ ! -f apps/desk/dist/index.html ] || [ "${REBUILD_UI:-0}" = "1" ]; then (cd apps/desk && npm run build); fi
else
  echo "npm not found: the API will run without the desk UI (install Node 20+ to build it)"
fi

bold "4/4 Start API (embedded vault + fixtures)"
uv run --no-sync companion-api check-config >/dev/null || die "configuration invalid (run: uv run companion-api check-config)"
PORT=$(uv run --no-sync python -c 'from companion_core.config import load_config; c=load_config(); print(c.api.port)')
DESK_TOKEN=$(grep -E '^COMPANION_DESK_TOKEN=' .env | cut -d= -f2-)
echo
echo "Open  http://127.0.0.1:${PORT}/   and paste this desk token in Settings:"
echo "  ${DESK_TOKEN}"
echo
exec uv run --no-sync companion-api serve
