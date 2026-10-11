// Holder for a flat, intact payment insert (payment_mode="insert" only).
// In "core" mode the payment hardware is the donor ring itself and this
// part is empty.  Dimensions mod_l/mod_w/mod_t are PROVISIONAL.
include <gl_lib.scad>
payment_mode = "insert";
if (layout == "assembly") module_holder(); else face_up(y_diff1) module_holder();
