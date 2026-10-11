// Removable electronics cartridge (battery + PCB + LEDs + switch + contacts)
// and the LED diffuser / light chamber.
include <gl_lib.scad>
part = "cartridge";  // "cartridge" | "diffuser"
if (layout == "assembly") { if (part == "cartridge") cartridge(); else diffuser(); }
else if (part == "cartridge") face_up(y_cf) cartridge();
else face_down(y_cart1 + chamber_h) diffuser();          // LED pockets up
