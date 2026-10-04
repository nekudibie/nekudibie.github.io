# Hardware

The step-by-step identification and bench-test plan is in docs/NEXT_STEPS.md.

Status words used here: **confirmed** (Neku has it and it is identified), **unknown**
(exists but model/condition unidentified), **candidate** (reasonable option, not bought),
**excluded** (must not be used).

## Inventory (identified from Neku's photos, 2026-10-04)

| Item | Status | Model / markings | Notes |
|---|---|---|---|
| CPU | confirmed | AMD Ryzen 5 5600G (AM4, 6c/12t, integrated graphics) | Strongest part owned. Needs an AM4 motherboard, DDR4 **desktop** DIMMs, a PSU and a cooler. **No AM4 board seen yet.** |
| CPU | confirmed, excluded | Intel Core i3-380M (2010 mobile, socket G1) | Too old and slow; no use here. |
| RAM | confirmed | Samsung 8 GB DDR4 SO-DIMM PC4-2400T (M471A1K43CB1-CRC) | Laptop memory. Fits the incoming i5-7200U laptop; does **not** fit a desktop AM4 board. |
| RAM | confirmed, excluded | Samsung 4 GB DDR3 DIMM PC3-12800U (M378B5273CH0-CK0) | DDR3 desktop; incompatible with Ryzen. |
| RAM | confirmed, excluded | Samsung 4 GB DDR3 SO-DIMM PC3-10600S (M471B5273CH0-CH9) | DDR3 laptop; too old for either host. |
| Laptop (ordered, £10) | confirmed, not yet arrived | Intel i5-7200U, 4 GB RAM, 128 GB SSD, 14", working battery | Candidate always-on vault + Home Assistant host, and a small-model brain once the 8 GB DDR4 SO-DIMM is fitted (8 or 12 GB total depending on slots). Battery doubles as a UPS. |
| Laptop webcam module | confirmed, excluded | strip marked CUPAI13FF23000BC206759R2 | Internal ribbon-cable camera; not a usable camera for this project. |
| SD card reader board | confirmed, excluded | DAG34ATH6D0 "Intel G34A" | Laptop daughterboard; no use. |
| Smart lights | partly | Govee Smart LED Bulb **H6006**, B22, 1000 lm, 2700–6500 K (one photographed; three owned, assumed same model until confirmed) | Neku reports the Govee Home app shows **LAN Control** (switched on) and all three are the same model, so Home Assistant's local Govee integration should apply; to be confirmed when HA runs. Otherwise Govee cloud API via Home Assistant. |
| Motherboard | confirmed exists, model unknown | AM4 (Neku confirms) | Model decides whether the 5600G needs a BIOS update first (B450/X470/A320 do; B550/A520 usually do not). Needs **long** DDR4 DIMMs, none seen yet, plus a cooler and PSU. |
| HDDs/SSDs, PSU, spare screen | unknown | ? | Not yet photographed. |
| Camera | unknown | ? | Not yet identified. |
| Raspberry Pi (doorbell) | in use, excluded | model not recorded | Runs Neku's doorbell; leave it alone. |
| Found USB stick | **excluded** | — | Firmware cannot be verified. Keep out of every host on the network. |
| Laptop battery cells | **excluded** | — | Do not build a pack from unidentified cells. |

Take photos of labels and run `sudo dmidecode -t processor,memory` and `lsblk -o NAME,SIZE,MODEL`
on any board that boots; paste the output into this file.

## Roles and what they need

### Desk (frontend)
* **Candidate:** Raspberry Pi 5, 4–8 GB. It only runs a browser kiosk and the native audio
  client; the model does not run here. Not a mandatory purchase: any small Linux box with
  HDMI, USB audio and a browser does the same job.
* Screen: the spare panel is usable only if it has (or gets) an HDMI controller board. If it
  is a bare laptop panel, you need a controller board matched to the panel's exact model
  number (printed on the back); choose it after identification. Touch is optional; a USB
  touch controller shows up as a normal HID device on Linux.
* Audio: a USB microphone/speakerphone or a Pi HAT with a microphone array. USB is simplest
  and avoids kernel overlays. Hardware mute = a device with a physical mute switch; the
  client's software mute is shown as "software mute" because it is not a disconnect.
  `companion-audio` needs only `alsa-utils` (`arecord`/`aplay`), 16 kHz mono capture.
* Power: the official Pi 5 27 W USB-C supply if a Pi 5 is bought; the Pi 5 is picky about
  5 V/5 A for USB peripherals.
* OS: Raspberry Pi OS (64-bit, Debian 13 "Trixie", Python 3.13) with desktop for the kiosk.
  Raspberry Pi OS Lite + a minimal Wayland kiosk is an option later.

### Brain (model host)
* 2026-10-04: a **Ryzen 5 5600G** was found in the salvage. With an AM4 board, 16 GB of DDR4
  desktop memory and a PSU it would be a strong brain for 7–8B models. No board has been seen,
  so the brain is still unconfirmed. The £10 i5-7200U laptop (with the 8 GB DDR4 SO-DIMM
  fitted) is the interim brain for 3B-class models and the always-on vault host.
* Earlier note: the old machines were already stripped for parts and may not boot, so there
  was **no confirmed brain host**. Options, in order of least spend: (a) try one
  board + CPU + matching RAM + a spare PSU on the bench first (needs a monitor, keyboard and
  a USB stick with Ubuntu Server 24.04); if it POSTs and `deploy/scripts/check-host.sh`
  passes, it is the brain; (b) run brain and desk on one Pi 5 8 GB with a small model only
  (expect slow replies; measure before judging); (c) a second-hand small-form-factor PC with
  16 GB RAM when budget allows. Nothing is bought until (a) has been tried.
* The strongest *working* rescued x86_64 machine: needs a motherboard that POSTs, a CPU that
  fits it, RAM of the right generation, a PSU, cooling, and an SSD for the OS. A loose CPU
  alone is nothing; DIMMs cannot be added to a Pi.
* Reality check before relying on it: an old dual-core laptop CPU can be *slower* than a
  Pi 5 for int8 inference. Run the measurement in docs/BUILD_GUIDE.md ("Benchmark the brain")
  before deciding. Expect usable 7–8 B models only with ≥16 GB RAM and a reasonably modern
  CPU; a discrete GPU with ≥8 GB VRAM changes the picture entirely.
* OS: Ubuntu Server 24.04 LTS (x86_64) or Debian 13. Ollama's install script supports both.
* RAM is **not** pooled across machines on a network. The brain's RAM is what it has.

### Vault/home server
* Any reliable host that is on 24/7 with low power draw. A separate machine from the brain is
  nice but not required at first (two-host layout: desk + brain/vault combined).
* Storage: a small SSD for the OS, `vault.db` and Home Assistant config; the rescued HDDs
  (after a SMART check) as an archive for recordings and backups. Use SATA/USB bridges that
  support UASP; identify bridge chips after the drives are known.
* Home Assistant Container runs here with `network_mode: host` (needed for discovery).

## Smart-home coverage (be exact before claiming it)
* **Hue:** with a Hue Bridge the HA integration is fully local. Bluetooth-only bulbs without
  a bridge are a different, weaker story.
* **Govee (3 lights, models unknown):** Home Assistant core has a local Govee light
  integration that uses Govee's LAN API, but only for the models Govee lists as LAN-capable,
  and only after "LAN Control" is switched on for each light in the Govee Home app
  (Settings of the device). Other models fall back to Govee's cloud API (needs an API key,
  rate-limited). First step: read the model number (H6xxx) from each light and check it
  against Govee's LAN API device list; record the three here.
* **Smart Life/Tuya:** the official HA Tuya integration is cloud-dependent and not
  feature-complete; local alternatives are community projects. Decide per device.
* **Camera:** needs RTSP/ONVIF or an HA-supported integration to appear as a camera entity;
  a cloud-only camera may offer nothing usable locally.

## Robot body (later)
Sequence: expressive stationary head → slow indoor wheeled rover (manual) → mapped waypoint
navigation → optional follow/docking → carried outdoor companion. A legged robot is a separate
advanced project. A rover needs onboard motion control (microcontroller with a watchdog),
rated motor drivers, encoders, bumper/cliff sensors, a fused and protected battery, and a
*physical* motor-power stop. Nothing in software substitutes for that switch.

## Conditional shopping list
Nothing has been priced; check current availability before buying anything.

| Need | Reuse if | Otherwise buy | Optional |
|---|---|---|---|
| Desk computer | an old mini-PC/laptop boots and has HDMI + USB | Raspberry Pi 5 (4–8 GB) + official PSU + case with fan + microSD or NVMe HAT | — |
| Desk screen | spare panel has HDMI (or an identified controller board is obtainable) | 7–10" HDMI touch display | touch |
| Microphone/speaker | a USB headset/speakerphone exists | USB conference speakerphone with physical mute | mic-array HAT |
| Brain | a rescued board + CPU + matching RAM + PSU all work | second-hand small-form-factor PC with ≥16 GB RAM | GPU ≥8 GB VRAM |
| Vault storage | rescued HDDs pass SMART | 1 TB SATA/NVMe SSD | USB-SATA UASP dock for HDD archive |
| Network | existing router has spare ports | small unmanaged switch | — |
