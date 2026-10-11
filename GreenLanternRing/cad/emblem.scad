// Emblem parts: opaque bezel (cap) and translucent green lens.
include <gl_lib.scad>
part = "bezel";  // "bezel" | "lens" | "center"
if (layout == "assembly") { if (part == "bezel") bezel(); else if (part == "center") emblem_center(); else lens(); }
else if (part == "bezel")  face_down(y_top) bezel();     // visible face on the (smooth) bed
else if (part == "center") face_down(y_top) emblem_center();
else face_up(y_ins1) lens();                             // symbol boss up
