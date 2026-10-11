# Point-to-point wiring plan (v0.1)

All of this sits in the removable **electronics cartridge** (`stl/design_X/electronics_cartridge.stl`).
Coordinates match the CAD: +X is the switch side, −X the contact side, and the emblem faces up.

## Ring cartridge

| # | From | To | Wire / method | Notes |
|---|---|---|---|---|
| 1 | J1 brass pin (−X wall, the pin toward −Z) | D1 anode pad | 0.2 mm enamelled wire, ~8 mm | Press the pin in first, then tin it |
| 2 | D1 cathode | B1 **+** tab (PCM output +) | PCB trace / short wire | Mark polarity on the PCB silkscreen |
| 3 | B1 + | S1 common (middle pin) | PCB trace | |
| 4 | S1 "on" throw | R1, R2, R3 (one end each) | PCB trace | The other throw is left unconnected |
| 5 | R*n* | LED*n* anode | PCB trace | LEDs on the PCB **top** face, centred on the diffuser pockets |
| 6 | LED*n* cathode | GND net | PCB trace | |
| 7 | B1 **−** tab (PCM output −) | GND net | Short wire | |
| 8 | J2 brass pin (−X wall, the pin toward +Z) | GND net | 0.2 mm enamelled wire, ~8 mm | |

Order: (1) press the pins into the cartridge and fit the ferrite sheet in the floor pocket; (2) solder all
SMD parts on the PCB and test it from a bench supply limited to 4.0 V and 20 mA; (3) solder the cell
leads **last**, with the switch OFF; (4) lay the cell in its pocket, fold the leads, and seat the PCB
in its recess.

Polarity check before closing (multimeter, **DC volts**): J1 (+) to J2 (−) should read about **0 V**,
because D1 blocks the battery from the contacts. Battery tabs should read 3.0–4.2 V. The LEDs light
when S1 is on.

## Cradle

| # | From | To | Notes |
|---|---|---|---|
| 1 | USB-C charger board VBAT / BAT+ | Pogo pin P+ (pin toward −Z, lower) | Through the tower's wire hole |
| 2 | Charger board GND / BAT− | Pogo pin P− | |
| 3 | Charger board STAT LED | Visible through a 2 mm hole in the base (optional) | Adafruit #4410 has an on-board charge LED |
| 4 | R_PROG | Replace the 10 kΩ PROG resistor with **66.5 kΩ** (or 68 kΩ) | **Check the board's actual PROG resistor location on its schematic before desoldering** |

Before any real cell: connect a **dummy load** (a 3.6 V bench supply as a sink, or a 100 Ω resistor plus
a voltmeter) and confirm about 15 mA flows and that the voltage regulates at 4.20 V (CHG-01).

## Connectors and contacts

* Ring contacts: brass Ø1.0 mm rod. Brass resists sweat better than steel and is non-magnetic.
  Gold-plated pogo targets are a future upgrade.
* Cradle: 2 × spring test probes (P75-series, Ø1.02 mm plunger, in R75 receptacles), spring force about
  50–100 g, 3.5 mm pitch. The mandrel holds the ring radially, so spring force cannot push it off.
