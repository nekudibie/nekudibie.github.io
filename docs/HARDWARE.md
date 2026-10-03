# Hardware

Status words used here: **confirmed** (Neku has it and it is identified), **unknown**
(exists but model/condition unidentified), **candidate** (reasonable option, not bought),
**excluded** (must not be used).

## Inventory template (fill in as items are identified)

| Item | Status | Model / markings | Notes to capture |
|---|---|---|---|
| Spare screen | unknown | ? | Panel size, native resolution, connector on the panel (eDP/LVDS/HDMI), whether it already has a controller board, touch (USB? which chipset?) |
| Old laptop/desktop CPUs | unknown | ? | Exact model string from the heat spreader; socket; TDP |
| RAM | unknown | ? | DIMM vs SO-DIMM, DDR generation, capacity, speed |
| Motherboards | unknown | ? | Model, socket, POST status, which RAM generation, SATA/M.2 ports, onboard video |
| HDDs | unknown | ? | Capacity, interface, SMART health (`smartctl -a`), hours |
| Smart lights | partly | Hue, Govee, Smart Life/Tuya | Exact models, whether a Hue Bridge exists, Govee models with LAN control |
| Camera | unknown | ? | Brand/model, RTSP/ONVIF support, whether cloud-only |
| Found USB stick | **excluded** | — | Scanned and formatted, but firmware cannot be verified. Keep out of every host on the network. |
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
  and avoids kernel overlays. Hardware mute = a device with a physical mute switch.
* Power: the official Pi 5 27 W USB-C supply if a Pi 5 is bought; the Pi 5 is picky about
  5 V/5 A for USB peripherals.
* OS: Raspberry Pi OS (64-bit, Debian 13 "Trixie", Python 3.13) with desktop for the kiosk.
  Raspberry Pi OS Lite + a minimal Wayland kiosk is an option later.

### Brain (model host)
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
* **Govee:** local control exists only for specific models with "LAN Control" enabled in the
  Govee app; others need the cloud API. List model numbers first.
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
