# Electronics — rechargeable green LED system (Task 6)

Status: **design v0.1, calculated, NOT yet built or measured.**

## 1. Architecture

```
          ┌──────────────── RING ────────────────┐            ┌──────── CRADLE ────────┐
          │                                      │            │                        │
 payment  │  [Payment ring core / tag]  ← no electrical connection to anything        │
          │                                      │            │                        │
 lighting │  J1 ─▶|─ D1 ─┬─ B1 LiPo+PCM ─┐       │  pogo pins │ USB-C ─ MCP73831 ─ POGO+│
          │              └── S1 ── 3×(R+LED) ─┴─ J2 ◀──────────▶ (15 mA CC/CV) ─ POGO−  │
          └──────────────────────────────────────┘            └────────────────────────┘
```

Design decisions:

* **The charger IC lives in the cradle, not the ring.** The ring then holds only a protected cell, a
  diode, a switch, 3 resistors and 3 LEDs. That saves about 3 × 3 mm of PCB, and the charge current is
  set in one place.
* **D1 (BAT54 Schottky) in series with the contact.** The two brass contacts are exposed. With D1, a
  key, coin or sweat bridging them **cannot discharge the cell**. The cost is that the cell charges to
  about 3.95 V (80–85% of capacity) instead of 4.20 V. That is a deliberate safety and longevity choice.
* **No microcontroller.** Steady light doesn't need one. A microcontroller would add idle current,
  firmware, programming hardware and about 4 mm² of board, with no safety benefit (see
  [`../firmware/README.md`](../firmware/README.md) for the optional upgrade).
* **Payment and lighting are electrically independent.** Nothing connects to the payment hardware. The
  only interaction is magnetic (the cell's metal near the antenna), which is handled with a ferrite sheet
  and tested in ANT-04 and PAY-04/05.

## 2. Components (ring)

| Ref | Part | Why | Key values |
|---|---|---|---|
| B1 | **LiPo pouch cell with built-in PCM**, 301012 or 301015 class, **≥30 mAh** | Protected cell: the PCM cuts out on over-charge (~4.25–4.3 V), over-discharge (~2.5–3.0 V) and short circuit | 3.7 V nominal, 4.2 V max. Envelope in CAD (Design B): 12 × 10 × 3.0 mm, PCM bulge included. **Exact part and datasheet still to source (P5-01).** |
| D1 | BAT54 (SOT-23) or BAT54WS (SOD-323) Schottky | Reverse blocking on the exposed contacts | Vf ≈ 0.25 V at 1 mA, 0.32 V at 10 mA; 30 V, 200 mA |
| S1 | Sub-miniature SMD side-actuated slide switch, SPDT (e.g. **MSK-12C02** class) | Positive off: zero LED current when off | ≥100 mA rating. *Check the body size against the 3.2 mm slot* |
| R1–R3 | 680 Ω 0402 or 0603, 1% | One resistor per LED, so brightness is shared evenly | ≈1.3 mA per LED at 3.7 V; power < 2 mW |
| LED1–3 | **Kingbright APTD1608LZGCK** (0603, InGaN pure green, ~525 nm), or similar | Efficient green, bright even at 1 mA | Vf ≈ 3.3 V at 20 mA (datasheet); ~2.7–2.8 V at 1–2 mA (**estimate, measure in LED-01**) |
| J1, J2 | Ø1.0 mm brass rod, 3 mm long, press-fit in the cartridge | Charging contacts | 3.5 mm pitch, recessed 0.2–0.3 mm |
| — | NFC ferrite sheet, 0.1–0.3 mm, cut to 12 × 10 mm | Shields the payment antenna from the cell | Under the cell (between cell and band) |
| PCB | 0.8 mm FR-4, ~17 × 13 mm, **no copper pour** | Carries D1, S1, R, LEDs | Hand-solderable 0603. A breadboard-free option is §6 |

## 3. Resistor calculation (worked example)

Ohm's law for an LED with a series resistor:

  **R = (V_supply − V_f) / I_LED**

With V_supply = 3.7 V (nominal cell), V_f ≈ 2.75 V (green InGaN at about 1.5 mA) and a target of
I = 1.4 mA: R = (3.7 − 2.75) / 0.0014 ≈ 680 Ω (an E12 value). Power in R = I²R = 0.0014² × 680 ≈ 1.3 mW,
which is trivial.

Because V_f is close to the cell voltage, **brightness falls as the cell drains**. That is acceptable,
and it acts as a natural low-battery indicator. Full table: [`calculations/led_power_results.md`](calculations/led_power_results.md).

| R per LED | I per LED @3.95 / 3.7 / 3.4 V | 3-LED total @3.7 V | Runtime (30 mAh × 0.8) |
|---|---|---|---|
| 330 Ω | 3.1 / 2.4 / 1.7 mA | 7.3 mA | ~3.3 h |
| 470 Ω | 2.3 / 1.8 / 1.2 mA | 5.4 mA | ~4.5 h |
| **680 Ω (default)** | 1.6 / 1.3 / 0.9 mA | 3.9 mA | **~6 h** |
| 1 kΩ | 1.1 / 0.9 / 0.6 mA | 2.7 mA | ~9 h |

Heat: total power is under 30 mW even at 330 Ω, so there is no measurable temperature rise (verified
later in LED-04).

## 4. Battery specification (requirement for purchasing)

| Parameter | Requirement |
|---|---|
| Chemistry | Lithium-ion polymer (LiPo), single cell |
| Nominal / max voltage | 3.7 V / 4.20 V |
| Capacity | ≥30 mAh (so the 15 mA charge current is ≤0.5 C) |
| Size | ≤ 12 × 10 × 3.0 mm (Design B), ≤ 10 × 10 × 3.0 (A), ≤ 15 × 12 × 4.0 (C), **including PCM and tabs** |
| Protection | **Integrated PCM is mandatory** (over-charge, over-discharge, over-current or short circuit) |
| Max charge current | ≥0.5 C in the datasheet |
| Datasheet | Required. Don't buy a cell without one |
| Leads | Nickel tabs or pre-soldered leads. **Never solder directly to the cell body** |

Charging: CC/CV to 4.20 V at the charger (3.95 V at the cell after D1), 15 mA, terminating at about 7.5% of
I_REG. Estimated time from empty is ~2.4 h. **Termination at R_PROG = 66.5 kΩ is outside the datasheet's
characterised table (2–10 kΩ), so it must be measured on a dummy load first (CHG-02).**

Safety: charge on a non-flammable surface, never on the finger (the cradle enforces this), stop if the
ring is warm (>40 °C, CHG-04), and replace any swollen cell. The cartridge is removable, so the cell is
never permanently sealed in.

## 5. Charging method comparison (decision: cradle with pogo pins)

| Option | Safety | Size cost in ring | Practicality | Verdict |
|---|---|---|---|---|
| USB-C socket in the ring | Socket is ~9 × 3.5 × 7 mm and needs its own charger IC and moisture path | Very high | Poor | ✗ |
| Magnetic pogo connector | Good, but magnets near NFC detune it and saturate ferrite | Medium | Good | ✗ (magnets) |
| Removable cartridge charged outside the ring | Very good | Low | Fiddly every day | Partial: the cartridge *is* removable for service |
| **Printed charging cradle + 2 pogo pins, charger IC in cradle, diode in ring** | Very good: no magnets, keyed orientation, short-proof contacts | Lowest (2 pins plus a diode) | Good | **✓ selected** |

## 6. Wiring and assembly plan (point-to-point)

See [`wiring/point_to_point.md`](wiring/point_to_point.md).

## 7. Can the LEDs flash when near a terminal?

* **What's possible:** a separate passive "field detector" (a small coil, a rectifier and an LED, as in
  £1 NFC nail-art LEDs) lights up when a reader's field is present. It needs no battery.
* **Why we don't, for now:** that coil takes energy from the *same* field the payment chip needs, so it
  can push a ring that's already marginal into failure. It also only means "a reader is near". It
  **cannot** know whether a payment was approved. The approval travels encrypted between chip, terminal
  and issuer, and nothing outside that exchange can legitimately read it.
* **If wanted later:** test it as an optional upgrade, placed as far from the payment loop as possible,
  and accept only if PAY-04 (success rate) does not drop.

## 8. Diagrams

* Ring schematic: [`schematic/ring_led_schematic.svg`](schematic/ring_led_schematic.svg)
* Cradle schematic: [`schematic/cradle_charger_schematic.svg`](schematic/cradle_charger_schematic.svg)
* Regenerate with `python3 schematic/draw_schematic.py` (needs `pip install schemdraw`).
