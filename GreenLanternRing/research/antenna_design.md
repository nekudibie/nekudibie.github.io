# NFC antenna engineering (lessons, options, and experiments)

> **Rule for this project:** payment hardware keeps its **original, approved antenna**. Everything in
> §4–§6 is for *non-payment* NTAG/MIFARE experiments, which teach the skills and let us measure how our
> enclosure, battery and LEDs affect a 13.56 MHz coil.

## 1. Lesson: how NFC works, from simple to deeper

**Simple picture.** The terminal contains a coil carrying an alternating current that reverses
13.56 million times a second. That makes a magnetic field that keeps flipping direction. Put another coil
(the card's antenna) in that field and a voltage appears across it. This is **electromagnetic induction**,
the same principle as a transformer, except the two coils are separated by air. The card's chip lives on
that voltage, so it needs no battery. To answer, the chip switches a small load on and off, which slightly
changes how much energy it draws. The terminal sees tiny dips in its own coil current and decodes them
(**load modulation**).

**Deeper.**
* **Inductance (L)** is how strongly a coil stores energy in its magnetic field. It grows with the
  *square* of the number of turns (N²) and roughly with the loop size.
* **Capacitance (C)** stores energy in an electric field. The chip has a built-in input capacitance,
  for example 50 pF for NTAG213 (NXP datasheet).
* **Resonance.** An L and a C together form a tuned circuit that "rings" most strongly at
  f = 1 / (2π√(LC)). Tune it to 13.56 MHz and the card collects far more voltage from the same field,
  like pushing a swing at its natural rhythm.
* **Q factor** measures how sharp that resonance is. High Q gives more voltage but a narrow tuning window,
  so a slight detune (a hand, metal, temperature) and performance drops. Too high a Q also distorts the
  data sidebands (847 kHz subcarrier), so practical NFC antennas use a moderate Q, roughly 10–40.
* **Coupling (k)** is the fraction of the reader's field that passes through your coil. It depends mainly
  on **area and distance**. A bank card's 80 × 50 mm loop catches a lot of field, which is why cards
  read at about 4 cm. A ring's 20 mm loop catches far less, so rings typically work at 0–2 cm and are
  sensitive to angle.
* **Impedance matching.** The reader's antenna is matched to its transmitter (50 Ω systems). On the tag
  side "matching" just means resonating the coil with the chip's capacitance. The chip's own
  capacitance does the job if the coil has the right L, which is why tags need no extra parts.
* **Why rings work at all.** Payment-ring makers use tightly optimised modules (and sometimes ferrite)
  and accept a short range. EMV contactless only needs a few millimetres to a few centimetres.

## 2. Effect of nearby materials

| Material | Effect at 13.56 MHz | Mitigation |
|---|---|---|
| **Li-ion cell (steel or aluminium can, foil pouch)** | Eddy currents cancel the field and lower L and Q, so the coil detunes upward and loses range | Keep it out of the antenna's loop area. Put a **ferrite sheet** (0.1–0.3 mm NFC "anti-metal" sheet) between them. Test with the cell in place (ANT-04) |
| PCB copper pours | Same as above, but smaller | No ground pour on the LED PCB; use thin traces |
| Steel screws, magnets | Detuning and loss. Magnets can also saturate ferrite | Plastic or brass screws near the antenna; no magnets in the ring |
| Skin and water | Slight capacitive detune and loss | Test while worn (PAY-05) |
| Plastics (PETG, PLA, resin) | Negligible | — |
| Brass charging pins (2 × Ø1 mm) | Small loss | Placed on the head's side, away from the payment ring's band loop |

## 3. Antenna configurations considered

| # | Configuration | Pros | Cons | Use in this project |
|---|---|---|---|---|
| 1 | **Circular wire coil round the band** | Largest loop a ring can have; axis lies along the finger | Couples best with the hand turned sideways; easy to damage | Inside a commercial payment ring (D). Also our Phase 2 experiment (coil-former jig) |
| 2 | **Flat spiral under the emblem** | Faces the terminal on a "fist bump"; easy to make as a flex PCB | Small area (Ø12–16 mm); battery directly underneath | Approach E with a ferrite layer; Phase 2 pancake-jig experiments |
| 3 | **Flexible PCB antenna** | Repeatable and cheap at JLCPCB-type fabs (~£10–£20 for 5) | Needs the chip's capacitance to design; can't hold a payment SE | Optional Phase 2: NTAG chip plus flex spiral |
| 4 | **Coil-on-module coupling** | How modern cards work | You'd need to build a booster antenna matched to an unknown module | Not pursued (see the prepaid feasibility doc) |
| 5 | **Intact payment-module antenna** | Certified; no tuning | You're limited to the vendor's shape | **Primary (D/E)** |

## 4. Proposed experimental antennas (non-payment)

From [`../electronics/calculations/antenna_results.md`](../electronics/calculations/antenna_results.md)
(run `antenna_calc.py`; these are first-order estimates, ±30%):

* **Band coil for NTAG213 (50 pF → target ~2.76 µH):** 0.20 mm (≈32 AWG) self-bonding or
  solderable-enamel ("self-fluxing", polyurethane) magnet wire, **8 turns** on a 20 mm loop (finger
  Ø18–19 mm) predicts f ≈ 13.5 MHz. Wind 7, 8 and 9-turn versions.
* **Band coil for MIFARE Classic (17 pF → ~8.1 µH):** about 14 turns.
* **Flat spiral, Ø14 mm, 0.30 mm pitch:** even 12 turns reaches only about 1.9 µH, short of NTAG213's
  2.76 µH. A small spiral **needs a parallel tuning capacitor** (for NTAG213, about 22–33 pF extra,
  found by measurement) or a larger diameter. This is a valuable result: it shows why a flat emblem
  antenna is hard.
* **Cross-check with your PDF:** its 15 in (381 mm) of wire is about 6 turns on a 20 mm ring, which the
  table puts at about 1.6–1.9 µH. That is a reasonable resonance for a payment chip with a higher input
  capacitance than NTAG. Treat it as consistent, not proven (the payment chip's C is unpublished).

How to get the parts for these experiments: cheap NTAG213 or MIFARE **PVC cards** (dissolve in acetone
exactly as the Instructable does) or **wet inlays**. Their chip modules have two antenna pads you can
solder to. This is the dress rehearsal for the risky part of Approach A.

## 5. Measuring performance

| Tool | Cost (est.) | What it gives you |
|---|---|---|
| iPhone + "NFC Tools" app | £0 | Read or no-read, and range with a ruler. Crude but free |
| PN532 module + Raspberry Pi (libnfc / `nfcpy`) | ~£8–£12 | Repeatable read-success rate at fixed heights; scriptable logging into `tests/results.csv` |
| **NanoVNA** (H or H4) | ~£50–£70 | Resonant frequency and Q of the coil. Measure with a small "sniffer" loop (2–3 turns, Ø15 mm) on CH0/CH1 and look for the dip or peak in S21. *Optional but the single best learning tool* |
| NFC field-detector LED card | ~£2 | Shows where the reader's field is strongest on a real terminal |

**Experimental tuning:** wind the coil with 1–2 extra turns, connect the chip, and measure the range or
the VNA resonance. Remove a quarter-turn at a time until the range peaks. If you can't add turns (flat
spiral), add small C0G capacitors (5–22 pF) across the chip pads, one value at a time.

**What success looks like:** an NTAG213 reads at ≥ 10 mm on the PN532 and ≥ 5 mm on a phone, 50/50 times
(ANT-02). With the battery and ferrite installed it drops by no more than 30% (ANT-04).

## 6. What we will not do

No retuning, re-winding or modification of the antenna on a payment device we rely on (D/E). No attempt
to read, copy, relay or emulate a payment credential.
