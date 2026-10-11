# Learn-as-we-build lessons

Each lesson gives a simple practical example first, then the deeper engineering. Terms are defined the
first time they appear.

---

## L1. How NFC works
See [`../research/antenna_design.md`](../research/antenna_design.md) §1 (induction, resonance, Q,
coupling). **Try it:** hold an NTAG sticker against your phone and move it away a millimetre at a time.
Then tape a coin behind it and repeat. The coin's eddy currents shorten the range, which is the
same effect our battery has.

## L2. Payment cards vs generic NFC tags
* An **NFC tag** (NTAG213, for example) is a memory chip: anyone with a reader can read it, and often
  write to it. That's fine for a URL sticker.
* A **payment card** is a **secure element (SE)**: a tiny computer running a payment *applet* that never
  reveals its secret keys. It answers challenges instead of handing over data.
* So "my phone can read the tag in my ring" proves only that NFC radio works. It proves **nothing** about
  payments.

## L3. EMV security, conceptually
1. The terminal asks the card to approve an amount and supplies a random number (the *unpredictable
   number*).
2. The card computes a **cryptogram**: a cryptographic signature over the amount, the terminal's random
   number, its own transaction counter and other data, using a key that only it and the issuer know.
3. The terminal sends that cryptogram to the issuer (via the acquirer and the network). The issuer checks
   it with its copy of the key and approves or declines.
4. Copying the card's public data (card number, expiry) is useless for an in-store contactless payment,
   because you can't produce new cryptograms without the key, and the key can't be read out. That is why
   the only legitimate routes are **(a) use an intact issued chip, or (b) have an issuer or TSP provision
   a token onto certified hardware.**
* **Tokenisation**: wearables and phones usually hold a *token* (a substitute card number linked to your
  real card) instead of your actual card number. Manage-Mii and Fidesmo provision tokens; Curve acts as
  the card the token points to.

## L4. Why an antenna must be tuned
Simple: a playground swing goes highest when you push at its natural rhythm. A coil plus capacitor has a
natural rhythm too, f = 1/(2π√LC), and the reader pushes at 13.56 MHz. Match them and you get far more
voltage for the same push. Deeper: [`antenna_design.md`](../research/antenna_design.md) and the numbers in
[`antenna_results.md`](../electronics/calculations/antenna_results.md).

## L5. LED resistor values
An LED is not a resistor. Above its "forward voltage" (V_f) its current rises steeply, so you must limit
the current with a series resistor: **R = (V_supply − V_f) / I**. Example: 3.7 V cell, green LED
V_f ≈ 2.75 V at 1.4 mA → R = 0.95 V / 0.0014 A ≈ 680 Ω. Use one resistor **per** LED: LEDs in parallel
on one resistor don't share current evenly, because their V_f values differ slightly.

## L6. How tiny lithium chargers work
* **CC/CV**: the charger pushes a *constant current* (15 mA for us) until the cell reaches 4.20 V, then
  holds *constant voltage* while the current tapers off. It stops at about 7.5% of the set current
  (*termination*).
* **The C-rate** expresses current relative to capacity: 15 mA into a 30 mAh cell = 0.5 C. Tiny cells
  are often limited to 0.5–1 C. More than that heats and ages them.
* **PCM (protection circuit module)**: a tiny board on the cell with a controller (DW01-type) and
  MOSFET switches. It disconnects the cell on over-voltage, under-voltage or excessive current. It's a
  safety net, not a charger.
* Why the charger lives in the cradle: fewer parts in the ring, one place to set the current, and the
  ring holds nothing that can force current into the cell except through the cradle.

## L7. Designing printable enclosures
* **Parametric**: every dimension derives from a few inputs (`finger_d`, `core_t`, and so on), so a
  different finger or part is a one-number change. Open `cad/gl_lib.scad`, change `finger_d`, and re-run.
* **Clearance is a design value**, not an afterthought: sliding fit about 0.2 mm per side, press fit about
  0.1 mm, on FDM.
* **Print orientation decides strength.** FDM layers are weakest in tension *across* layers, which is why
  the ring band prints with the finger axis vertical (the hoop stress then runs *along* the layers).
* **Design for service**: screws plus a stack of drop-in parts rather than glue, so a cheap part never
  traps an expensive one.

## L8. Using a multimeter
* **DC volts (V⎓)**: probes *across* the thing (in parallel). Black on GND or −, red on +.
  Use it for battery voltage and LED V_f.
* **Current (mA / µA)**: the meter goes *in series*, so you break the circuit and route the current
  through it. **Move the red lead to the mA socket**, and move it back afterwards (forgetting this is the
  classic way to blow the meter's fuse).
* **Continuity / Ω**: power **off**. Use it to find broken wires, shorts and solder bridges.
* **Diode test**: shows about 2.5–2.9 V on a green LED (often lighting it faintly) and about 0.2–0.3 V on
  the BAT54. Great for checking polarity before soldering.

## L9. Testing and debugging
See the method at the end of [`troubleshooting.md`](troubleshooting.md). The core habit: **predict →
measure → compare → log**.

## L10. From prototype to reliable product
1. **Prove the risky thing first** (payment activation), cheaply and in isolation.
2. **Freeze interfaces** (core dimensions, cartridge envelope), then iterate inside them.
3. **Test the way it will be used** (worn, warm, sweaty, in different shops).
4. **Write down every failure.** The log in `tests/results.csv` is what turns hacks into engineering.
5. **Revise in versions**: v0.1 (this), v0.2 after measurements, v1.0 after two weeks' wear.
