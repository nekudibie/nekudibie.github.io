# Troubleshooting

## Payment

| Symptom | Likely cause | What to do |
|---|---|---|
| Terminal doesn't react at all | Wrong pose, ring antenna not coupling | Hold still for 3–4 s. Try palm side, then side of the finger, then "fist bump" on the screen centre. Test the core *outside* the shell (PAY-01) |
| Works outside the shell, not inside | Shell material or electronics detuning | Take the cartridge out and retest. If it now works, the cell or PCB copper is the cause: add or enlarge the ferrite, or move the cell (log under ANT-04) |
| Beep but "declined" | Issuer or Curve decision (limit, SCA, funds) | Check the Curve app. Not a hardware fault |
| "Insert card" / PIN request | SCA cumulative limit, or the £100 limit | See PAY-06. Pay once with the phone or card to reset, if your issuer resets that way |
| Stopped working after months | Token expiry, card replaced, Curve changes | Check the Manage-Mii or Fidesmo app status before suspecting hardware |

## Lights

| Symptom | Check (multimeter) | Fix |
|---|---|---|
| No light | Cell voltage at the tabs (DC V). Below 3.0 V → flat or PCM tripped | Charge it. If 0 V, the PCM may be latched: charging normally resets it |
| One LED dark | Voltage across that LED while on: about 0 V means a short; about the cell voltage means open | Reflow the joint or replace the LED (check its polarity mark) |
| Very dim | Cell below 3.4 V (normal behaviour), or R too high | Recharge, or fit 470 Ω |
| Hotspots | Diffuser not seated, or LEDs off-centre | Re-seat it. Sand the diffuser top. Consider a thicker `chamber_h` (Design C) |

## Charging

| Symptom | Likely cause | Fix |
|---|---|---|
| Charge LED never lights | No contact | Clean the pins with IPA. Check the pogo spring travel. Check the ring's pins aren't recessed too far (aim for 0.2–0.3 mm) |
| LED never goes out | Termination at the low PROG current (CHG-02), or a faulty cell | Measure the current. If it stays above 2 mA after 4 h, unplug it and investigate |
| Ring warm | Fault | Stop and log CHG-04. Check the charge current is about 15 mA |

## How to debug any circuit (method)

1. **Look**: solder bridges, wrong polarity, cracked parts. Use a magnifier.
2. **Power**: is the supply voltage where it should be? Measure from the source to the load, point by point.
3. **Divide**: disconnect half the circuit. Does the fault move? Repeat.
4. **Compare**: measure a good LED branch against the bad one.
5. **Change one thing at a time**, and log it in `tests/results.csv`.
