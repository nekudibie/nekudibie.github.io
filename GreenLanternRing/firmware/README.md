# Firmware: intentionally omitted in v0.1

The v0.1 light is **steady green, on/off by slide switch**. That needs no microcontroller, so there is
no firmware. That's deliberate:

* Fewer parts in a very cramped head (a microcontroller adds about 3 × 3 mm plus decoupling, and a
  programming pad).
* No idle drain. Even a sleeping AVR adds about 0.1–20 µA, versus about 3 µA for the PCM alone.
* Nothing to brick, nothing to program, nothing to debug while the payment architecture is still being
  proven.

## Optional upgrade (Phase 7+): breathing or pulse animation

If you want a "charging the ring" pulse later:

| Option | Size | Notes |
|---|---|---|
| **ATtiny10** (SOT-23-6) | 2.9 × 2.8 mm | 1 KB flash, PWM on 2 pins, TPI programming (USBasp with TPI firmware, or an Arduino as programmer). Runs from 1.8–5.5 V, so it works directly from the cell |
| ATtiny202/402 (SOIC-8 / 8-pin) | 5 × 6 mm | UPDI programming (one wire, with a USB-serial adapter plus a resistor). Easier tooling, bigger |

The design change: S1 stays as the master power switch. The microcontroller's PWM pin drives the LEDs'
common low side through a small N-MOSFET (or directly, at these 4 mA). Firmware would be about 40 lines
of C. **This will be written only when the hardware stage needs it**, so we don't ship untested code.

An "LED flashes when paying" mode is **not** planned: see
[`../electronics/README.md`](../electronics/README.md) §7 for why we can detect a reader's field at
best, and never a payment approval.
