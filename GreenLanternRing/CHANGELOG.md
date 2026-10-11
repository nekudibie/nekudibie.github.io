# Changelog

## v0.1.1 (2026-10-11)
* Removed the IDEMIA enquiry draft from the public repository.

## v0.1 (2026-10-11): Phase 1 feasibility + first designs

### Research
* Approaches A (card transplant), B (OEM module: IDEMIA, Infineon, Tappy, USC), C (fob teardown),
  D (intact payment ring as core), E (intact flat tag) researched and scored. **D selected, E fallback.**
* Cash App Wand analysed as the reference pattern (an issuer-provisioned tag). Not available in the UK.
* Antenna engineering notes, with first-order calculators.

### CAD (OpenSCAD)
* Parametric ring body for payment-core, insert or no-payment modes; side lip plus printed C-ring
  retainer for the core.
* Emblem bezel, translucent lens with an opaque centre disc, LED diffuser, removable electronics
  cartridge, insert holder.
* Lantern charging cradle (mandrel, keyed pocket, pogo tower, charger bay, cover).
* UK ring-sizer set (N–W) and antenna winding jigs.
* `tools/build_and_verify.py`: STL export for designs A/B/C, mesh integrity, wall sampling,
  overhang share, assembly interference (ring parts plus a dummy core, and ring-in-cradle), renders.
* Fixes found by verification: the floating emblem-centre island became a separate part; the head side
  faces were made vertical for a flat contact face; the cradle pocket was corrected.

### Electronics
* Ring: protected LiPo, BAT54, slide switch, 3× (680 Ω + green 0603 LED). No microcontroller.
* Cradle: USB-C MCP73831 board at 15 mA (R_PROG 66.5 kΩ).
* Calculations: LED currents and runtime; charge rate and time; antenna inductance and resonance.

### Known issues (open)
* CAD-03: thin walls in the cartridge (≈0.35 mm) and the body contact recess, so print in resin.
* E-03: the Design A battery envelope is too small for ≥30 mAh at 0.5 C.
* All prices are unverified estimates. No hardware has been tested.
