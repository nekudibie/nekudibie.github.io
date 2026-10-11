// Main ring body (+ retainer C-ring in core mode). Print: finger axis vertical.
include <gl_lib.scad>
part = "body";   // "body" | "retainer"
if (layout == "assembly") { if (part == "body") ring_body(); else retainer_asm(); }
else if (part == "body") translate([0, 0, band_w/2]) ring_body();   // lip side on the bed
else retainer();
module retainer_asm() translate([0, 0, z_grv0 + 0.075]) retainer();
