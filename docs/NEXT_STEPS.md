# Next steps for Neku (written overnight, 2026-10-04)

Everything below is in the order I would do it. Each block says what you need, what to do,
what "done" looks like, and what to paste back to me. Nothing here buys anything, exposes
anything to the internet, or touches motors. Where a step needs a decision from you it says so.

Status words: **software ready** means the code for it is written and tested with fixtures;
**needs hardware** means the item does not exist yet; **your call** means I will not assume.

---

## Block A: 20 minutes at the PC before anything physical

### A1. Reset the Google client secret (5 min)
The secret was pasted into our chat, so treat it as leaked.
1. Open https://console.cloud.google.com/apis/credentials and click your OAuth client.
2. Click **Reset secret** (or **Add secret**, then delete the old one). Copy the new value.
3. In the terminal, in the `companion` folder:
   ```bash
   nano .env
   ```
   Replace the text after `COMPANION_GMAIL_CLIENT_SECRET=` with the new secret.
   `Ctrl+O`, `Enter`, `Ctrl+X`.
4. ```bash
   uv run companion-api email-logout
   uv run companion-api email-login
   ```
   Sign in again. Done when the terminal says the token was saved.

### A2. Pull the overnight update and start the companion (3 min)
```bash
git pull
./deploy/scripts/dev.sh
```
Open http://127.0.0.1:8710/. In **Tools → Purchases** the "Desk lamp bulb" and "HDMI cable"
rows now carry a **demo mailbox** badge. Click **Remove demo purchases**, then **Sync from
email**. Done when only real shops are listed and none shows merchant "Co".

Paste back: a screenshot of the Purchases list. If an order shows the wrong status or a
missing shop name, tell me the shop; I will add a pattern for its emails.

### A3. Give it a real model (10 min, software ready, your PC's RAM decides the size)
The chat currently answers from a labelled demo model. Ollama runs inside WSL:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b
ollama show qwen2.5:3b | grep -i -A3 capabilities
```
Done when the capabilities list includes `tools`. If it does not, tell me the output.

Then:
```bash
nano config/local.yaml
```
Under `llm:` set `provider: ollama` and `model: qwen2.5:3b`. Save. Restart with
`./deploy/scripts/dev.sh`. In the browser the health line should say the model is live and
the fixture badge disappears from chat replies.

Measure, do not guess:
```bash
ollama run qwen2.5:3b --verbose "Say hello in one sentence."
```
Paste back the `eval rate` line. Under about 8 tokens/s the replies will feel slow; that is
the number that decides whether your PC can be the brain for now.

If `ollama pull` says the model is too big for your RAM, use `qwen2.5:1.5b` and tell me.

---

## Block B: identify what you already own (30 min, phone camera, no tools)

Photograph every label. Blurry is fine as long as the model number is readable. Paste the
model numbers into the chat or into `docs/HARDWARE.md`.

### B1. Govee lights (decides whether they can be controlled without the cloud)
1. On each light find the sticker on the controller box or plug. The model starts with **H**
   followed by four digits, for example H6159 or H6072.
2. In the Govee Home app open each light → settings (gear icon) and look for a switch called
   **LAN Control**. Note whether it exists. If it does, turn it on.
Done when I have three model numbers and three yes/no answers for LAN Control.

### B2. Camera
Brand and model from the label on its base or back. Also: does it need its own app (cloud
only) or does the app mention RTSP or ONVIF? If you do not know, the model number is enough.

### B3. Spare screen
1. If it is a complete monitor: note its connector (HDMI, VGA, DisplayPort) and size.
2. If it is a bare laptop panel: photograph the label on its back. The model number looks
   like `LP156WH4`, `B140XTN`, `N156BGE`. That number decides whether a controller board
   exists for it. Note whether there is a second small ribbon cable (touch).

### B4. Salvaged computer parts
For each item, a photo of the marking:
- **CPU**: the text on the metal lid, for example `i5-6500` or `Ryzen 5 3600`.
- **RAM**: the sticker on each stick. Note whether it is long (desktop DIMM) or short
  (laptop SO-DIMM) and whether it says DDR3 or DDR4.
- **Motherboard**: the model printed between the slots, for example `B450M-A` or `H110M`.
- **HDD/SSD**: capacity and model from the label.
- **PSU**: do you have one at all, and what wattage.

Done when I can see which CPU fits which board and which RAM fits. I will tell you which
combination is worth a bench test, or whether none is.

---

## Block C: bench-test one rescued board (45 min, only if B4 found a matching set)

Do this only if you have, as one matching set: a motherboard, a CPU that fits its socket,
at least one RAM stick of the right generation, a CPU cooler, and a PSU. Missing any one of
those means skip to Block D; there is nothing to test.

Safety, plainly: unplug the PSU from the wall before touching anything. Touch a radiator or
the metal PSU case first to discharge static. Never force a CPU into a socket; it drops in
with no pressure when aligned. Do not use the found USB stick for anything.

1. Lay the board on its cardboard box (not on a metal surface). Fit CPU, cooler and one RAM
   stick in the slot the manual marks first (usually A2, the second from the CPU).
2. Connect the 24-pin and the 4/8-pin CPU power cables, a monitor to the board's own video
   output, and a keyboard.
3. Short the two **PWR_SW** pins on the front-panel header with a screwdriver tip for a
   second to start it.
4. Done, step 1, when the monitor shows the BIOS screen. No picture after 30 seconds: power
   off, try the other RAM stick or slot, reseat the cooler, then try once more. Still nothing
   after that: it does not POST; stop, that board is out.
5. If it POSTs: make an **Ubuntu Server 24.04** USB stick on the Windows PC with Rufus
   (https://rufus.ie) on a stick you trust, boot it, and install with the defaults onto the
   SSD (choose "Install OpenSSH server"). Use a fresh password; do not reuse any.
6. On the new machine:
   ```bash
   sudo apt update && sudo apt install -y git curl
   git clone https://github.com/nekudibie/nekudibie.github.io companion && cd companion
   ./deploy/scripts/check-host.sh
   ```
   Paste back the whole output. It reports CPU, RAM, disk and network and warns when the
   machine is too small for a role.

---

## Block D: the brain decision (made 2026-10-04)

Neku has an AM4 board and a Ryzen 5 5600G but no desktop DDR4 and does not want to buy any,
so that pair is shelved. Decision:

| Role | Host | Notes |
|---|---|---|
| Brain while at the desk | Neku's Windows PC, Ollama inside WSL (Block A3) | Measure `eval rate` and record it. Record the PC's CPU/RAM/GPU from `dxdiag`. |
| Always-on vault + Home Assistant | the £10 i5-7200U laptop with the 8 GB DDR4 SO-DIMM fitted | Battery doubles as a UPS. Also a slow small-model fallback when the PC is off. |
| Shelved | AM4 board + 5600G | Becomes a fast brain only if desktop DDR4 and a PSU are ever added. Not assumed. |

Block C (bench test) therefore does not apply for now.

## Block E: first real host install (software ready, 30 min once a host exists)

On the host chosen as brain (or brain+vault):
```bash
./deploy/scripts/setup-role.sh brain
./deploy/scripts/install-units.sh brain --enable
./deploy/scripts/healthcheck.sh
```
Done when `healthcheck.sh` is green and http://<host-ip>:8710 opens from your PC. Then I
walk you through `setup-role.sh vault` and Home Assistant (docs/BUILD_GUIDE.md stage 2).

---

## Block F: desk hardware (needs hardware; do after B and D)

What the desk needs, in order of what matters:
1. A microphone and speaker with a **physical mute switch**. A USB speakerphone is the simplest.
   Reuse any USB headset first to test voice; buy nothing until it works with the headset.
2. A screen with HDMI. The spare panel only counts if B3 finds a controller board for it.
3. A small computer. Your PC does this today. A Pi 5 is the usual choice later, but a Pi is
   not needed to test anything in Block A to E.

Voice test with any USB headset (software ready, not yet hardware-tested). WSL usually cannot
see USB audio devices, so do this on a real Linux machine (the Pi or the rescued host), not in
WSL. Full steps are in docs/BUILD_GUIDE.md stage 4; the short version:
```bash
uv sync --all-packages --extra stt --extra tts     # downloads the local speech models once
sudo apt install -y alsa-utils && arecord -l && aplay -l
uv run companion-audio --input-device plughw:1,0 --output-device plughw:0,0
```
Press Enter to start and stop a recording, speak in between. Paste back what it prints if
anything fails, together with the `arecord -l` output.

## What I will do while you work through this
- Add email patterns for any shop you name.
- Turn your measurements into the brain decision and a precise, priced shopping list if you ask.
- Add the three Govee models to `docs/HARDWARE.md` and tell you exactly which ones Home
  Assistant can drive locally.

## Hard rules still in force
No purchases, no motors, no public exposure, no sending email, no battery packs from loose
cells, and the found USB stick stays out of every machine on your network.
