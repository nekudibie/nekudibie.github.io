#!/usr/bin/env python3
"""Draws the ring + cradle schematics to schematic/*.svg (schemdraw).
Run: python3 draw_schematic.py
"""
import schemdraw
import schemdraw.elements as elm
from pathlib import Path
OUT = Path(__file__).parent

# ---------------- Ring (LED module) ----------------
with schemdraw.Drawing(file=str(OUT / "ring_led_schematic.svg"), show=False) as d:
    d.config(fontsize=11)
    TOP, GND = 6.0, 0.0
    d += elm.Label().at((7, 8.3)).label("RING — LED MODULE (no microcontroller)", fontsize=13)
    d += elm.Label().at((7, 7.6)).label("Payment hardware = separate, unpowered, electrically isolated part")
    d += elm.Dot(open=True).at((0, TOP)).label("J1 CHG+ (brass pin)", loc="left")
    d += elm.Diode().at((0, TOP)).to((3, TOP)).label("D1 BAT54 Schottky", loc="top")
    d += elm.Line().at((3, TOP)).to((4.5, TOP))
    d += elm.Dot().at((4.5, TOP))
    d += elm.Battery().at((4.5, TOP)).to((4.5, GND)).reverse().label("B1 LiPo 3.7 V ≥30 mAh\nwith PCM", loc="bottom", ofst=0.2)
    d += elm.Label().at((4.15, 3.55)).label("+")
    d += elm.Switch().at((4.5, TOP)).to((7.5, TOP)).label("S1 slide on/off", loc="top")
    xs = [8.5, 10.5, 12.5]
    d += elm.Line().at((7.5, TOP)).to((xs[-1], TOP))
    for i, x in enumerate(xs):
        d += elm.Dot().at((x, TOP))
        d += elm.Resistor().at((x, TOP)).to((x, 3.2)).label(f"R{i+1} 680 Ω", loc="bottom")
        d += elm.LED().at((x, 3.2)).to((x, GND)).label(f"LED{i+1}", loc="bottom", ofst=(0, -0.2))
        d += elm.Dot().at((x, GND))
    d += elm.Line().at((0, GND)).to((xs[-1], GND))
    d += elm.Dot(open=True).at((0, GND)).label("J2 CHG− (brass pin)", loc="left")
    d += elm.Dot().at((4.5, GND))
    d += elm.Ground().at((2.2, GND))
    d += elm.Label().at((7, -1.6)).label(
        "D1 lets charge current in but stops the cell discharging if J1/J2 are bridged by metal or sweat.\n"
        "LEDs: green 0603 (e.g. Kingbright APTD1608LZGCK). R = 680 Ω → ≈1.3 mA each at 3.7 V.\n"
        "B1's PCM provides over-charge, over-discharge and short-circuit cut-off. No part connects to the payment ring.")

# ---------------- Cradle (charger) ----------------
with schemdraw.Drawing(file=str(OUT / "cradle_charger_schematic.svg"), show=False) as d:
    d.config(fontsize=11)
    d += elm.Label().at((6, 7.6)).label("CRADLE — USB-C 5 V → MCP73831 single-cell Li-ion charger", fontsize=13)
    u = elm.Ic(pins=[elm.IcPin(name="VDD", side="left", slot="1/2"),
                     elm.IcPin(name="VSS", side="left", slot="2/2"),
                     elm.IcPin(name="PROG", side="right", slot="1/3"),
                     elm.IcPin(name="VBAT", side="right", slot="2/3"),
                     elm.IcPin(name="STAT", side="right", slot="3/3")],
               edgepadW=1.6, edgepadH=0.8, label="U1 MCP73831 (4.20 V)", lblloc="bottom", lblofst=0.3).at((4, 2))
    d += u
    # input
    d += elm.Line().at(u.VDD).left(2.0)
    vin = d.here
    d += elm.Dot()
    d += elm.Capacitor().at(vin).down(2.2).label("C1 4.7 µF", loc="bottom")
    d += elm.Ground()
    d += elm.Line().at(vin).left(1.0)
    d += elm.Dot(open=True).label("VBUS 5 V from USB-C board\n(board has 5.1 kΩ CC pull-downs)", loc="left")
    d += elm.Line().at(u.VSS).left(0.6)
    d += elm.Line().up(0.8)
    d += elm.Ground().reverse() if False else elm.Label().label("GND", loc="top")
    # PROG
    d += elm.Line().at(u.PROG).right(1.0)
    d += elm.Resistor().down(2.6).label("R_PROG 66.5 kΩ\nI ≈ 15 mA", loc="bottom")
    d += elm.Ground()
    # VBAT
    d += elm.Line().at(u.VBAT).right(3.2)
    vb = d.here
    d += elm.Dot()
    d += elm.Capacitor().at(vb).down(2.0).label("C2 4.7 µF", loc="bottom")
    d += elm.Ground()
    d += elm.Line().at(vb).right(1.5)
    d += elm.Dot(open=True).label("POGO+ → ring J1", loc="right")
    # STAT (open-drain low while charging): 5 V → LED → R → STAT
    d += elm.Line().at(u.STAT).right(1.0)
    d += elm.Line().up(2.0)
    d += elm.Resistor().right(2.2).label("R2 1 kΩ", loc="top")
    d += elm.LED().right(2.2).reverse().label("LED red = charging", loc="top")   # anode toward 5 V
    d += elm.Dot(open=True).label("5 V", loc="right")
    d += elm.Dot(open=True).at((vb[0] + 1.5, vb[1] - 3.2)).label("POGO− → ring J2 (GND)", loc="right")
    d += elm.Ground().at((vb[0] + 1.5, vb[1] - 3.2))
    d += elm.Label().at((6, -2.6)).label(
        "Easiest build: a ready-made USB-C MCP73831 board (e.g. Adafruit Micro-Lipo USB-C, #4410) with its\n"
        "PROG resistor replaced by 66.5 kΩ (68 kΩ acceptable, ≈14.7 mA). Verify charge current and termination\n"
        "on a dummy load before connecting a real cell (tests CHG-01/02).")
print("schematics written")
