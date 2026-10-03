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

Where things run: `companion-audio` on the desk Pi (capture/playback via ALSA `arecord`/
`aplay`, in-memory buffers only); speech recognition (faster-whisper) and speech synthesis
(Piper) inside `companion-api` on the brain.

1. **Brain host, install the speech extras and models** (one-off, needs internet):
   ```bash
   uv sync --all-packages --extra stt --extra tts        # from packages/integrations extras
   mkdir -p data/voices && uv run python -m piper.download_voices en_GB-alan-medium --data-dir data/voices
   ```
   faster-whisper downloads its model on first use into `data/models/whisper`; pre-warm it
   with `uv run python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8', download_root='data/models/whisper')"`.
   Set `stt.provider: faster_whisper` and `tts.provider: piper` in `config/local.yaml`.
   Checkpoint: `GET /v1/audio/status` shows both providers with `is_fixture: false`;
   `POST /v1/audio/speak` returns a WAV you can play.
   Piper is GPL-3.0 and runs as a separate optional component.
2. **Desk Pi, audio devices**: `sudo apt install alsa-utils`, then `arecord -l` / `aplay -l` to
   find card/device numbers. Test the pair:
   `arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 3 /tmp/t.wav && aplay -D plughw:0,0 /tmp/t.wav`
   (then delete `/tmp/t.wav`). Prefer a USB speakerphone with a physical mute switch.
3. **Run the client**: `uv run companion-audio --api http://<brain>:8710 --input-device plughw:1,0 --output-device plughw:0,0`.
   Enter starts/stops a push-to-talk recording, `s` stops speech, `m` toggles the software
   mute. Pressing Enter while it is speaking interrupts it (barge-in). Without a microphone you
   can still exercise the whole path: `uv run companion-audio --simulate my_question.wav --output null`
   (16 kHz mono WAV).
4. **Echo and self-triggering**: the client is half-duplex (never records while speaking) and
   stops playback on any new push-to-talk. Measure on the real pair: speak while it answers
   and confirm it does not transcribe its own voice. Record the result in docs/STATUS.md.
5. **Wake word (after push-to-talk is stable)**: `uv sync --extra wakeword` on the desk,
   then `companion-audio --wake-word openwakeword --wake-model hey_jarvis`. Only the 80 ms
   ring buffer is held in memory; listening stops while muted. Default stays off.
6. **Physical button/LED** (optional): wire a momentary button to a GPIO pin and call
   `press_ptt()` / `release_ptt()` from a small gpiozero script; drive an LED from the
   `on_state` callback so "listening"/"speaking" is visible without the screen.

## Stage 4b: meetings

From the desk Pi: `uv run companion-audio --api http://<brain>:8710 --record-meeting "Weekly sync" --participants-informed`
(Enter stops). From the browser on localhost/HTTPS the Jobs page records with the consent
box. Transcription needs `stt.provider: faster_whisper` on the brain; progress shows on the
Jobs page, results under the meeting entry. Expect several minutes per hour of audio on a
CPU-only brain with the `base` model; measure and record the figure in docs/STATUS.md.

## Stage 5: real hosts with systemd (brain, then vault)

On each rescued host, as the user that will run the services:

```bash
git clone https://github.com/nekudibie/nekudibie.github.io companion && cd companion
deploy/scripts/check-host.sh            # architecture, Python, RAM, disk, GPU, audio tools
deploy/scripts/setup-role.sh brain      # or: vault / desk. Installs only that role's packages, creates .env and config/local.yaml
```

Edit `config/local.yaml` (`api.host` to the LAN address or keep 127.0.0.1 behind Caddy,
`llm`, `home`, `vault.mode`) and `.env` (tokens from `uv run companion-api make-token`), then:

```bash
uv run companion-api check-config
deploy/scripts/install-units.sh brain --enable      # api + worker + nightly backup timer
deploy/scripts/healthcheck.sh http://127.0.0.1:8710
```

Checkpoint: `systemctl status companion-api companion-worker` are active;
`systemctl list-timers companion-backup.timer` shows the next 02:00 run; the desk opens the
brain's address and connects.

Vault host: `setup-role.sh vault`, set `vault.mode: remote` **on the brain** with
`vault.url: http://<vault>:8720` and the same `COMPANION_VAULT_TOKEN` in both `.env` files,
then `install-units.sh vault --enable` on the vault host and restart the brain's API.
Checkpoint: brain `/readyz` shows `vault: ok mode=remote`. Home Assistant runs on the vault
host with `deploy/compose/homeassistant.yml`.

Containers instead of systemd: `deploy/compose/brain.yml` (Ollama, optionally the API and
worker with `--profile containers`) and `deploy/compose/vault.yml`; the image is built from
`deploy/docker/Dockerfile` with the locked dependencies.

## Stage 6: network and TLS

Keep every port off the internet. On the LAN either bind to the LAN address and firewall it
to the desk and vault hosts (`sudo ufw allow from <desk-ip> to any port 8710`), or keep
127.0.0.1 and put Caddy in front with its internal CA (`deploy/caddy/Caddyfile`) so the desk
browser has HTTPS, which is also what browser microphone capture needs. Install Caddy's root
certificate on the desk Pi. A WireGuard/Tailscale overlay is the simplest way to reach the
assistant away from home.

## Stage 7: updates and rollback

`deploy/scripts/update.sh` backs up, fetches, stops the units, installs the locked
dependencies, rebuilds the UI, runs migrations and restarts. It prints the rollback command;
`deploy/scripts/update.sh --rollback <ref>` restores the code, and the pre-update backup set
is there if a migration must be undone (`deploy/scripts/restore.sh`).

## Stage 8: the robot body (simulation first)

Nothing in this repository drives a motor. `robotics.mode: simulated` exposes the same
bounded command API a real body would get (`/v1/robot/*`), with a watchdog, link-loss,
bumper/cliff and latched emergency-stop behaviour you can exercise from the desk. Before any
hardware: a microcontroller that owns the motor drivers and stops on its own watchdog, rated
drivers, encoders, bumper and cliff sensors, a fused battery and a physical motor-power switch.
The Pi/brain only ever sends bounded high-level commands over an authenticated link.

## Recovery
* API won't start → `uv run companion-api check-config` prints the exact error.
* Model unreachable → the UI shows "model offline"; lights, scenes, time and stop still work.
* Database damaged → restore per docs/OPERATIONS.md "Backup and restore".
