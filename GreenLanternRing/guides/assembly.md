# Assembly instructions (v0.1, primary architecture D, "core" mode)

> Do these steps **in order**. Each stage has a gate: don't continue until its test passes.

## Stage 0: Size and buy the payment core

1. Print `stl/shared/ring_sizer_set.stl` (UK sizes N–W). Wear the best-fitting gauge for two hours
   (fingers swell in the evening and in warm weather). → **MECH-01**
2. Confirm in the Curve app (and the Manage-Mii or Fidesmo app) that your chosen ring model can still be
   linked in 2026. → **P1-03**
3. Buy the Curve-compatible payment ring in that size. Activate it **as delivered** and make three small
   purchases with it alone. → **PAY-01**. If this fails, stop: the issue is the ring or the account,
   not our design.
4. Measure the ring with calipers: inner diameter, outer diameter and width, at three points each. Update
   `cad/gl_lib.scad`: `finger_d` = the core's inner diameter, `core_t` = (OD − ID)/2, `core_w` = width.

## Stage 1: Print and fit the shell

```bash
cd GreenLanternRing
python3 tools/build_and_verify.py --design B -D finger_d=<ID> -D core_t=<t> -D core_w=<w>
```

1. Print `ring_body` and `retainer_cring` in PLA first (cheap fit test), then in PETG or resin.
2. Slide the payment ring in from the open side until it meets the lip. Squeeze the C-ring and snap it
   into its groove. The split goes on the palm side. → **MECH-02**
3. Repeat the payment tests with the core in the shell. → **PAY-02**

## Stage 2: Build the electronics cartridge

Follow [`../electronics/wiring/point_to_point.md`](../electronics/wiring/point_to_point.md).

1. Cut the ferrite sheet to 12 × 10 mm (Design B) and lay it in the floor of the battery pocket.
2. Press the two Ø1.0 × 3 mm brass pins into the −X wall holes. They should stand about 1.0 mm proud of
   the cartridge wall.
3. Assemble and test the LED PCB from a **current-limited bench supply (4.0 V, 20 mA limit)** before
   connecting the cell. → **LED-01, LED-02**
4. Solder the cell leads last, with the switch OFF. Insulate the tabs with Kapton.
5. Seat the cell, fold the wires into the channel, and seat the PCB. The switch actuator must line up
   with the +X notch.

## Stage 3: Close the head

1. Drop the cartridge into the head cavity. The pins slide down their U-slots and the switch drops into
   its window.
2. Place the diffuser (LED pockets down, over the LEDs).
3. Place the lens (symbol up), then press the **centre disc** onto the lens's locating pin.
4. Fit the bezel and drive two M1.4 × 4 self-tapping screws. **Snug, not tight**: they're threading into
   plastic.
5. Switch on and check the emblem lights evenly. → **LED-05**

## Stage 4: Cradle

1. Fit the pogo receptacles into the tower holes and solder wires (red = toward −Z, black = toward +Z;
   match your ring's J1 and J2).
2. Fit the modified MCP73831 USB-C board (PROG = 66.5 kΩ) in the bay, with the USB-C port in the slot.
   Screw on the cover.
3. **Dummy-load test before any ring.** → **CHG-01, CHG-02**
4. Slide the ring onto the mandrel, head into the pocket, and check the charge LED. → **CHG-05**

## Stage 5: Integration tests

Run **PAY-03 … PAY-06** and **LED-06**. Log everything in `tests/results.csv`.

## Disassembly (service)

Unscrew the 2 bezel screws, then lift out the bezel, centre disc, lens, diffuser and cartridge. The
payment core comes out by squeezing out the C-ring. **No step needs glue or cutting**, so the
battery, LEDs and switch can each be replaced on their own, and the payment core is never touched.
