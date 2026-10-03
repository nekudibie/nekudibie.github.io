#!/usr/bin/env bash
# Report what this machine is and whether it can run a companion role. Read-only.
set -u
ok()   { printf '  [ok]   %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=1; }
FAIL=0
echo "Host report: $(hostname) ($(date -u +%Y-%m-%dT%H:%MZ))"
ARCH=$(uname -m); OS=$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || uname -s)
echo "  arch: $ARCH | os: $OS | kernel: $(uname -r)"
case "$ARCH" in x86_64|aarch64) ok "architecture supported";; armv7l) bad "32-bit ARM is not supported (use a 64-bit OS image)";; *) bad "unknown architecture $ARCH";; esac
PY=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3 || true)
if [ -n "$PY" ]; then V=$($PY -c 'import sys;print("%d.%d"%sys.version_info[:2])'); case "$V" in 3.11|3.12|3.13|3.14) ok "python $V at $PY";; *) warn "python $V found; 3.11+ required (uv can install one: uv python install 3.12)";; esac; else warn "no python3; uv can install one"; fi
command -v uv >/dev/null && ok "uv $(uv --version | cut -d' ' -f2)" || warn "uv missing: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v node >/dev/null && ok "node $(node --version) (UI build)" || warn "node missing (only needed where the UI is built)"
command -v docker >/dev/null && ok "docker $(docker --version | cut -d' ' -f3 | tr -d ,)" || warn "docker missing (needed for Home Assistant Container / Ollama container)"
command -v ollama >/dev/null && ok "ollama $(ollama --version 2>/dev/null | head -1)" || warn "ollama not installed natively (fine if it runs in a container or on another host)"
command -v arecord >/dev/null && ok "alsa-utils present (arecord/aplay)" || warn "alsa-utils missing (desk role: sudo apt install alsa-utils)"
MEM_GB=$(awk '/MemTotal/{printf "%.1f", $2/1048576}' /proc/meminfo); CPUS=$(nproc)
echo "  cpu: $CPUS cores | ram: ${MEM_GB} GB | model: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //' || echo '?')"
awk -v m="$MEM_GB" 'BEGIN{exit !(m+0 < 7.5)}' && warn "under 8 GB RAM: a brain role will only run small models" || ok "RAM is enough for 7-8B models (int4/int8)"
DISK_FREE=$(df -h . | awk 'NR==2{print $4}'); ok "free disk here: $DISK_FREE (models need 4-8 GB each)"
if command -v lspci >/dev/null; then GPU=$(lspci 2>/dev/null | grep -iE 'vga|3d' | cut -d: -f3- | head -1); [ -n "$GPU" ] && echo "  gpu: $GPU"; fi
command -v nvidia-smi >/dev/null && ok "nvidia-smi present: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)"
if [ -r /proc/device-tree/model ]; then echo "  board: $(tr -d '\0' < /proc/device-tree/model)"; fi
[ -f /sys/class/thermal/thermal_zone0/temp ] && echo "  temp: $(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 )) °C"
for d in /dev/sd? /dev/nvme?n?; do [ -b "$d" ] && command -v smartctl >/dev/null && echo "  drive $d: $(sudo -n smartctl -H "$d" 2>/dev/null | grep -i 'overall' || echo 'run sudo smartctl -H '"$d"' for health')"; done
[ "$FAIL" = 0 ] && echo "Result: this host can run a companion role." || { echo "Result: fix the FAIL items first."; exit 1; }
