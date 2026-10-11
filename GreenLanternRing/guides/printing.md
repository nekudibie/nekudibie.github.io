# Materials and print settings (v0.1)

Your printer, nozzle and materials are unknown, so these are starting points. **Tell me the printer
model and nozzle** and I'll tune the clearances (`slide_clear`, `press_clear`, `core_clear` in
`cad/gl_lib.scad`).

## Material choices

| Material | Use | Why / caution |
|---|---|---|
| **PLA** | Sizer, fit prototypes, jigs | Cheap and accurate; softens at ~55 °C (a car dashboard in summer), so not for the final ring |
| **PETG** | Final body, bezel, cradle | Tougher, sweat-resistant, ~75 °C. Black or dark metallic green |
| **Translucent green PETG** | Lens | Glows evenly when backlit; print slow and hot for clarity |
| **Natural/clear PETG or white translucent** | Diffuser | Scatters LED light |
| **Resin (SLA/MSLA)** | Lens, diffuser, centre disc, cartridge; ideally the body too | Sub-0.5 mm walls and smooth surfaces. **Uncured resin is a skin sensitiser**: wear nitrile gloves, wash in IPA, then UV post-cure *fully* (follow the resin maker's time, typically 10–30 min each side). For skin-contact parts, prefer a resin sold for skin contact or rely on the ceramic payment core as the skin surface (in core mode only the core and the lip edges touch the finger) |
| TPU | Not needed in v0.1 | Possible future soft retainer |

Avoid unverified coatings on skin-contact areas. A clear coat on the *bezel top only* is fine.

## Per-part settings (0.4 mm nozzle FDM unless noted)

| Part (STL) | Material | Layer | Walls | Infill | Orientation (as exported) | Supports | Notes |
|---|---|---|---|---|---|---|---|
| `ring_body` | PETG (or resin) | 0.12 mm | 4+ (all solid) | 100% | Finger axis vertical, lip side down | **Yes, inside the head cavity ceiling only** (the U-slots and switch window bridge 3 mm) | Sampled wall (p2): B and C ≥ 0.8 mm; A ≈ 0.6 mm. Resin preferred for A |
| `retainer_cring` | PETG | 0.12 | all solid | 100% | Flat | No | Must flex: PETG, not PLA |
| `emblem_bezel` | PETG black / dark green | 0.12 | 3 | 100% | Visible face down on a smooth PEI or glass bed | No | Gives a glossy face |
| `emblem_lens` | Translucent green PETG or resin | 0.12 | — | 100% | Symbol boss up | No | Sand the top flush with the bezel after a dry fit |
| `emblem_center_disc` | Same as bezel | 0.08 | — | 100% | Face down | No | Tiny part: brim, or print several |
| `led_diffuser` | White/clear PETG or resin | 0.12 | — | 100% | LED pockets up | No | Lightly sand the top face to diffuse |
| `electronics_cartridge` | **Resin** (tough) or PETG with a 0.25 mm nozzle | 0.08–0.1 | — | 100% | Open side up | No | Sampled wall ≈ 0.35 mm, too thin for a 0.4 mm nozzle in v0.1 |
| `charging_cradle_base` | PETG or PLA | 0.2 | 3 | 20% gyroid | As exported | Yes (electronics bay roof) | |
| `charging_cradle_cover` | PETG / PLA | 0.2 | 3 | 30% | Flat | No | |
| `ring_sizer_set` | PLA | 0.16 | 3 | 100% | Flat | No | **Print this first** |
| `jig_*` | PLA | 0.16 | 3 | 30% | Flat | No | Phase 2 antenna experiments |

## Tolerances and shrinkage

* `core_clear` 0.25 mm radial (FDM) or 0.12 (resin): the core must slide in by hand.
* `slide_clear` 0.20 mm per side for the cartridge; `press_clear` 0.12 mm for the lens and diffuser.
* PETG shrinks ~0.2–0.5% and holes print undersize by ~0.1–0.2 mm. **Calibrate with the sizer**: if a
  gauge's measured inner diameter (calipers) is smaller than its label value, apply that offset to
  `finger_d` and the clearances.
* Resin prints can *grow* by 0.05–0.1 mm on outer faces. Use the resin clearance values.

## Post-processing

1. Remove supports from the head cavity with flush cutters. Deburr the slots with a needle file.
2. Wet-sand the bezel face 400 → 800 → 1500 grit for a polished look (clear-coat optional, bezel only).
3. Dry-fit the lens: its symbol should sit flush with or proud of the bezel by ≤ 0.1 mm. Sand it flush.
4. Test-screw the M1.4 screws into the pilot holes once (forms the thread), then remove them.
5. Resin parts: wash, cure, and wait 24 h before skin contact.
