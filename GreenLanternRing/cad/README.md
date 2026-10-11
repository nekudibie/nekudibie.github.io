# CAD (OpenSCAD, parametric): v0.1 PROVISIONAL

**These are verified *meshes*, not a verified *ring*.** The script checks geometry (watertight, no
interference, wall thickness). Nothing has been printed or worn yet, and the payment-core dimensions are
placeholders.

## Files

| File | Parts | Notes |
|---|---|---|
| `gl_lib.scad` | Library: all parameters, presets A/B/C, every module | Edit parameters here or with `-D` |
| `main_ring.scad` | `part="body"` ring body; `part="retainer"` C-ring | |
| `emblem.scad` | `part="bezel"`, `"lens"`, `"center"` | Green Lantern Corps emblem, stylised |
| `electronics_housing.scad` | `part="cartridge"`, `"diffuser"` | Removable electronics cartridge and light chamber |
| `payment_holder.scad` | Flat payment-insert holder | `payment_mode="insert"` only (fallback E); dims `mod_l/w/t` |
| `charging_cradle.scad` | `part="base"`, `"cover"` | Lantern-style base: mandrel, keyed head pocket, pogo-pin tower, charger bay |
| `sizer.scad` | UK ring gauges N–W | BS 6820: circumference = 37.5 + 1.25 × letter index (mm) |
| `jigs.scad` | `coil_former`, `pancake_base`, `pancake_top` | Phase 2 antenna winding jigs |
| `assembly.scad` | Whole ring, coloured; `-D explode=6` | Preview only |

## Build everything (STL + checks + images + dimension drawings)

```bash
sudo apt install openscad          # 2021.01 or newer
pip install trimesh manifold3d numpy scipy networkx rtree matplotlib
python3 tools/build_and_verify.py                 # all designs, ~3 min
python3 tools/build_and_verify.py --design B -D finger_d=18.6 -D core_t=2.1 -D core_w=6.5
python3 tools/dimension_drawing.py B      # images/dimensions_design_B.png
```

Outputs: `stl/design_{A,B,C}/*.stl` (print orientation), `stl/design_X/assembly_frame/*.stl`
(assembled positions, used for the interference check), `stl/shared/*.stl`, `images/*.png`,
`tests/cad_verification.json`.

## Key parameters

| Parameter | Default | Meaning |
|---|---|---|
| `design` | `"B"` | `"A"` compact, `"B"` classic, `"C"` maximum illumination |
| `finger_d` | 19.0 (**PROVISIONAL**, about UK R½) | Finger bore. In core mode this is the payment ring's inner diameter |
| `payment_mode` | `"core"` | `"core"` (primary D), `"insert"` (fallback E), `"none"` (fit or experiments) |
| `core_t`, `core_w` | 2.3, 7.0 (**PROVISIONAL**) | Donor payment ring wall and width. **Measure the purchased ring** |
| `core_clear` | 0.25 | Radial clearance, shell to core (0.12 for resin) |
| `slide_clear` / `press_clear` | 0.20 / 0.12 | Cartridge / lens and diffuser fits |
| `mod_l, mod_w, mod_t` | 15 × 12 × 0.8 | Flat insert envelope (insert mode) |

## The three designs (v0.1 numbers from `tests/cad_verification.json`, finger Ø19, core 2.3 × 7 mm)

| | **A: Compact** | **B: Classic** | **C: Max illumination** |
|---|---|---|---|
| Head plan (across × along finger) | 18 × 15 mm | 21 × 17 mm | 23 × 19 mm |
| Overall width across the finger | 26.5 mm (band OD) | 26.9 mm | 26.9 mm |
| Band width (axial) / wall over finger | 9.85 mm / 3.75 mm (core 2.3 + shell) | 9.85 / 3.95 | 9.85 / 3.95 |
| Emblem size | 10.5 mm | 13 mm | 15 mm |
| Head cavity | 15.6 × 12.6 mm | 18.6 × 14.6 mm | 20.6 × 16.6 mm |
| Light chamber | 1.4 mm | 2.0 mm | 2.8 mm |
| LEDs | 3 | 3 | 5 |
| Battery envelope | 10 × 10 × 3 mm (~20–30 mAh) | 12 × 10 × 3 (~30–40 mAh) | 15 × 12 × 4 (~60–80 mAh) |
| **Height above finger** | **≈ 12.0 mm** | **≈ 12.9 mm** | **≈ 14.7 mm** |
| Printed mass (PETG) | ≈ 3.8 g | ≈ 5.5 g | ≈ 7.3 g |
| + core + electronics (est.) | ≈ 10 g | ≈ 12 g | ≈ 15 g |
| Comfort (expected) | Best of the three; still a statement ring | Chunky signet | Large; occasional wear |
| Print complexity | Highest (thinnest walls) | Medium | Lowest |
| Antenna implication | Cell closest to the band loop: most detuning risk | Medium | Largest cell: needs ferrite |
| Runtime at 680 Ω (est.) | ~4–6 h (20–30 mAh, 3 LEDs) | ~6 h (30 mAh) | ~8–10 h (60–80 mAh, 5 LEDs ≈ 6.4 mA) |

Note: Design A's battery envelope (10 × 10 mm) only takes cells under ~25 mAh, and the 15 mA charger
setting needs ≥30 mAh at 0.5 C. **Design A therefore needs a cell with a ≥0.6 C charge rating, or a
lower-current charger. Unresolved: tracked as issue E-03.**

## Honest assessment of v0.1 geometry

* **It is tall.** About 13 mm above the finger for B. The stack is: core and shell (about 3.8 mm) +
  cartridge (5.1 mm: floor, ferrite, 3 mm cell, wires, PCB) + light chamber 2 + lens 1 + bezel 1.2.
  Biggest levers for v0.2: a thinner cell (2 mm), side-firing LEDs to merge the PCB and chamber, and a
  thinner core ring.
* **The band is wide** (9.85 mm) because it wraps a 7 mm core with a lip, retainer and end wall.
* Thinnest sampled walls (p2): the cartridge is about 0.35 mm (A/B), the Design A body about 0.6 mm, and
  the emblem centre disc 0.3–0.5 mm. Print these in **resin** or thicken them in v0.2 (CAD-03 is OPEN).
* The Green Lantern emblem is a stylised geometric version (ring between two bars). It is a DC Comics
  trademark: fine for a personal build, not for sale.
