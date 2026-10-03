#!/usr/bin/env bash
# Poll the readiness endpoints of every configured host. Usage: healthcheck.sh [api_url] [vault_url]
set -u
API="${1:-${COMPANION_API_URL:-http://127.0.0.1:8710}}"; VAULT="${2:-${COMPANION_VAULT_URL:-}}"
check() { local name=$1 url=$2; out=$(curl -sS -m 5 "$url/readyz" 2>&1) && echo "$out" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("  %s: %s" % (sys.argv[1], "ready" if d.get("ready") else "NOT READY")); [print("    - %s: %s %s" % (x["name"], x["status"], x.get("detail",""))) for x in d.get("dependencies",[])]' "$name" || echo "  $name: unreachable ($url): $out"; }
check api "$API"; [ -n "$VAULT" ] && check vault "$VAULT"; exit 0
