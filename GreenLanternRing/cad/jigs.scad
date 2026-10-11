// Phase-2 antenna experiment jigs (non-payment NFC only).
//   coil_former : ring-sized former with a channel for winding test coils
//   pancake_jig : two-plate jig for winding flat (spiral) coils
include <gl_lib.scad>
part = "coil_former";  // "coil_former" | "pancake_base" | "pancake_top"
cf_h = 7; cf_wall = 1.6; ch_w = 2.6; ch_d = 1.0;
pk_od = 18; pk_hub = 6; pk_gap = 0.25;  // set pk_gap ≈ 1.2 × wire OD (0.2 mm wire -> 0.25)

module coil_former() difference() {
    cylinder(d = finger_d + 0.3 + 2*cf_wall + 2*ch_d, h = cf_h);
    translate([0, 0, -1]) cylinder(d = finger_d + 0.3, h = cf_h + 2);
    translate([0, 0, (cf_h - ch_w)/2]) difference() {
        cylinder(d = finger_d + 10, h = ch_w);
        translate([0, 0, -1]) cylinder(d = finger_d + 0.3 + 2*cf_wall, h = ch_w + 2);
    }
    // flat seat for a test chip module + two lead holes
    translate([-4, finger_d/2 + cf_wall + ch_d - 0.6, -1]) cube([8, 5, cf_h + 2]);
    for (s = [-1, 1]) translate([s*3, 0, cf_h/2]) rotate([-90, 0, 0]) cylinder(d = 0.8, h = 30, $fn = 16);
}
module pancake_base() difference() {
    union() { cylinder(d = pk_od + 6, h = 2); cylinder(d = pk_hub, h = 2 + pk_gap); }
    translate([0, 0, -1]) cylinder(d = 3.2, h = 10);              // M3 bolt
    translate([pk_hub/2 - 0.2, -0.3, 2]) cube([pk_od, 0.6, 1]);   // inner lead exit slot
}
module pancake_top() difference() {
    cylinder(d = pk_od + 6, h = 2);
    translate([0, 0, -1]) cylinder(d = 3.2, h = 10);
    for (a = [0 : 60 : 359]) rotate(a) translate([pk_od/2 - 2, 0, -1]) cylinder(d = 2, h = 5); // glue/inspection ports
}
if (part == "coil_former") coil_former();
else if (part == "pancake_base") pancake_base();
else pancake_top();
