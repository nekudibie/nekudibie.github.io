# Test plan (v0.1)

Log every run in [`results.csv`](results.csv) (one row per measurement; keep failures). The CAD
self-checks are in [`cad_verification.json`](cad_verification.json); regenerate them with
`python3 tools/build_and_verify.py`.

**Three different things, never to be confused:**
1. **Reader detection**: the terminal's field sees *something* (a generic tag read proves only this).
2. **EMV communication**: the terminal and the payment applet complete the contactless transaction
   protocol (the terminal beeps or shows "processing").
3. **Authorisation**: the issuer approves the payment ("Approved" on the terminal, and the transaction
   appears in the Curve app and on your bank statement). **Only this counts as a pass for payment
   tests.**

## A. CAD and mechanical

| ID | Test | Method | Pass criterion |
|---|---|---|---|
| CAD-01 | Mesh integrity | `build_and_verify.py` | All STLs watertight, 1 body per part (the sizer is 10 by design) |
| CAD-02 | Interference | Same script (assembly frame) | Overlap < 0.05 mm³ for every part pair, and ring vs cradle |
| CAD-03 | Wall thickness | Same (sampled) | p2 wall ≥ 0.8 mm for FDM parts; < 0.8 mm → print in resin |
| MECH-01 | Finger size | Print `ring_sizer_set.stl`, wear for 2 h incl. evening | Slides over the knuckle with mild resistance; no spin; no marks |
| MECH-02 | Core fit | Insert the payment ring into the printed body; fit the C-ring | Core inserts by hand; no rattle; C-ring seats; removable without tools damage |
| MECH-03 | Cartridge fit | Drop in; tip upside down | Slides in under its own weight ±; retained once the bezel is screwed |
| MECH-04 | Edges | Fingertip and cotton-wool test | No snag, no sharp edges |
| MECH-05 | Weight | Kitchen scale (0.1 g) | ≤ 15 g assembled (estimate: ~5.5 g printed PETG + core + ~3 g electronics) |
| MECH-06 | Durability | 100 cartridge remove/insert cycles; 1 m drop onto wood ×5 | No cracks; the bezel stays put |
| MECH-07 | Sweat | 24 h on finger over 3 days; inspect contacts | No corrosion; no skin irritation |

## B. NFC antenna experiments (non-payment)

| ID | Test | Method | Pass criterion |
|---|---|---|---|
| ANT-01 | Baseline | Unmodified NTAG213 card on PN532/phone: max read height (mm), 20 tries per height | Record (reference) |
| ANT-02 | Band coil | Recovered NTAG chip + 7/8/9-turn coil on `jig_coil_former` | ≥ 10 mm on PN532, 50/50 reads at 5 mm |
| ANT-03 | Resonance | NanoVNA sniffer loop | f_res within 13.56–15 MHz; record Q |
| ANT-04 | Battery and ferrite | Repeat ANT-02 with a dummy cell (same size, *discharged*) above the coil, with and without ferrite | Range loss ≤ 30% with ferrite |
| ANT-05 | Orientation | 0°, 45°, 90° to the reader; palm, side, back of the hand | Map the best orientation |

## C. Payment (authorised account only, low value)

Preconditions: the device is activated in the official app and linked to **your own** card. Each test is
a real purchase you intended to make anyway (≤ £5, e.g. a vending machine or coffee). Never test at
someone else's expense, and stop if the issuer flags anything.

| ID | Test | Pass criterion |
|---|---|---|
| PAY-01 | Core ring alone, as delivered | 5/5 approved transactions at ≥ 3 different merchants / terminal brands |
| PAY-02 | Core inside the printed shell, no electronics | Same success rate as PAY-01 |
| PAY-03 | Shell + cartridge with battery, LEDs off | ≥ 9/10 approved |
| PAY-04 | Same, LEDs on | ≥ 9/10 approved; no worse than PAY-03 |
| PAY-05 | Worn on finger, 3 orientations | Note the best "tap pose"; ≥ 9/10 in that pose |
| PAY-06 | SCA / PIN behaviour | Record what happens when the terminal requests a PIN (online-PIN prompt? decline?) and how the counter resets |
| PAY-07 | Over £100 limit behaviour | Record only (expected: decline or PIN) |

## D. LED and power

| ID | Test | Method | Pass criterion |
|---|---|---|---|
| LED-01 | Vf at low current | Bench supply 3.7 V through 680 Ω; measure V across the LED | Record (replaces the 2.75 V estimate) |
| LED-02 | Current draw | Multimeter in series (mA range), switch on, cell at 3.7 V | 3–5 mA total |
| LED-03 | Off current | µA range, switch off | ≤ 5 µA (PCM only) |
| LED-04 | Temperature | 30 min on, thermometer/thermocouple on the bezel | ≤ 5 °C rise above ambient |
| LED-05 | Uniformity | Photo in a dark room; judge by eye | No individual hotspot obvious at 30 cm |
| LED-06 | Runtime | Full charge → on until the PCM cuts off or the light is too dim; log every 30 min | ≥ 4 h usable light |
| LED-07 | Short-circuit protection | Bench test of a *spare* cell's PCM: short through a 0.1 Ω shunt plus a fuse, in a fire-safe tray | PCM opens; cell < 40 °C |

## E. Charging

| ID | Test | Method | Pass criterion |
|---|---|---|---|
| CHG-01 | Charge current | Cradle on a dummy load (3.6 V sink or resistor) | 13–17 mA in CC; 4.15–4.25 V CV |
| CHG-02 | Termination | Watch the STAT LED and current as V → 4.2 V | Terminates (current → 0, LED off) within 4 h |
| CHG-03 | Reverse block | Short J1–J2 on the ring with a coin | Cell voltage unchanged; nothing warm |
| CHG-04 | Temperature while charging | Thermometer on the ring during a full charge | ≤ 40 °C absolute, ≤ 10 °C rise |
| CHG-05 | Contact reliability | 20 place/remove cycles | Charging indicated 20/20 |

## F. Integration and environment

| ID | Test | Pass criterion |
|---|---|---|
| INT-01 | Ring near keys, phone, watch | No payment degradation; no unintended charging contacts |
| INT-02 | Hand-wash splash (not immersion) | Still lights and pays; no water in the cartridge |
| INT-03 | Two weeks daily wear | No unresolved issues in the log |

## Open issues tracker

Track in `results.csv` with `result = OPEN` rows, or as GitHub issues once the project is pushed.
