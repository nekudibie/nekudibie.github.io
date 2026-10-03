# Build guide

This guide goes from an empty laptop to a three-host deployment. Each stage has a checkpoint
and an expected result. Stages marked **hardware pending** cannot be completed until the
item exists; the software for them is ready and tested with fixtures.

## Stage 0: one machine, everything in fixtures (do this first)

Requirements: Linux or macOS, Python 3.11+, `uv`, Node 20+ (for the UI build).

```bash
git clone https://github.com/nekudibie/nekudibie.github.io companion && cd companion
./deploy/scripts/dev.sh
```

Checkpoint: the script prints a desk token and starts the API on http://127.0.0.1:8710.
Open it, go to Settings, paste the token, press *Save & test*. Expected: "Connected as desk".
In Chat try "turn on the desk lamp" (fixture badge appears), "remember that …", then ask about
it and open the sources drawer.

Tests: `uv run pytest -q` → all pass; `uv run ruff check .` → clean.

## Stage 1: attach a real model (brain on the same machine or a LAN host)

1. Install Ollama on the brain host (https://ollama.com/download, Linux script). Confirm with
   `curl http://<brain>:11434/api/version`.
2. Pull a model that reports the `tools` capability (`ollama show <model>` lists capabilities).
3. In `config/local.yaml` set `llm.provider: ollama`, `llm.base_url`, `llm.model`.
4. Restart the API. Checkpoint: `curl http://127.0.0.1:8710/readyz` shows `llm: ok`; if it
   says `degraded ... does not report the 'tools' capability`, pick another model.

Benchmark the brain (write the numbers into docs/STATUS.md, never guess them):

```bash
ollama run <model> --verbose "Say hello in one sentence."   # note eval rate tokens/s
```

## Stage 2: Home Assistant Container on the vault/home host

```bash
mkdir -p ~/homeassistant && cd deploy/compose && docker compose -f homeassistant.yml up -d
```

Open http://<host>:8123, create the owner account, add Hue (bridge), Govee and Tuya
integrations as applicable. Create a long-lived access token (Profile → Security).
Put it in `.env` as `COMPANION_HA_TOKEN`, set `home.provider: home_assistant`,
`home.base_url`, and list `home.allowed_entities` explicitly. Use the admin token with
`GET /v1/home/discover` to see entity ids.

Checkpoint: `/readyz` shows `home: ok`; the Home tab shows real entities without a fixture
badge; "turn on the desk lamp" moves a real light.

## Stage 3: desk Pi kiosk (hardware pending: Pi, screen, microphone)

1. Flash Raspberry Pi OS (64-bit, with desktop) with Raspberry Pi Imager; set hostname,
   user, Wi-Fi and SSH in the imager's settings.
2. First boot: `sudo apt update && sudo apt full-upgrade`, then
   `deploy/scripts/setup-desk.sh` (installs the kiosk autostart and the audio client).
3. Point the kiosk at `http://<brain>:8710/` (or the TLS address; see docs/OPERATIONS.md).

Checkpoint: screen shows the clock and connection banner; after pasting the desk token it
shows "Connected as desk".

## Stage 4: voice (hardware pending: microphone + speaker)

`companion-audio` runs on the desk Pi with ALSA `arecord`/`aplay`; STT (faster-whisper) and TTS
(Piper) run on the brain. Validate echo and interruption on the real speaker/microphone pair
before enabling the wake word.

## Stage 5: split the vault onto its own host

Set `vault.mode: remote`, `vault.url`, generate `COMPANION_VAULT_TOKEN` on both hosts, run
`companion-vault serve` on the vault host (systemd unit in deploy/systemd). Checkpoint:
`/readyz` on the API shows `vault: ok mode=remote`.

## Recovery
* API won't start → `uv run companion-api check-config` prints the exact error.
* Model unreachable → the UI shows "model offline"; lights, scenes, time and stop still work.
* Database damaged → restore per docs/OPERATIONS.md "Backup and restore".
