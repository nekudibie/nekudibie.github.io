// Green Lantern "lantern" charging cradle.
// The ring slides onto a mandrel (finger axis vertical); a pocket keys the
// head so the head's -X face presses onto two spring (pogo) pins.
// The Li-ion charger (MCP73831 USB-C board) lives inside the base, NOT in the ring.
include <gl_lib.scad>
part = "base";          // "base" | "cover"
H        = 18;          // base height
R        = 32;          // base radius
ring_off = [0, -5];     // ring centre relative to cradle centre
pogo_hole= 1.7;         // PROVISIONAL: receptacle OD for P75-series pogo pins
board    = [30, 24, 9]; // PROVISIONAL: charger board envelope (L, W, H incl. USB-C)
usb_slot = [10.5, 4.6]; // USB-C plug opening
mandrel_d= (core_mode ? core_id : bore_d) - 0.8;
z_ring   = H + band_w/2;  // ring z=0 plane in cradle coordinates

module ring_in_cradle() translate([ring_off[0], ring_off[1], z_ring]) children();

module head_pocket() {
    depth = head_l/2 - band_w/2 + 0.8;
    translate([0, 0, H - depth]) linear_extrude(depth + 1)
        offset(r = 0.6) projection() ring_in_cradle()
            intersection() { ring_body(); translate([-50, -50, -50]) cube([100, 100, 50 - band_w/2 - 0.05]); }
}

module tower() {
    x1 = -head_w/2 - 0.3;               // face touching (pins protrude 0.6–0.8 from here)
    ring_in_cradle() difference() {
        translate([x1 - 5, y_pin - 4, -band_w/2 - 1]) cube([5, 8, band_w/2 + pin_sp/2 + 4]);
        for (s = [-1, 1]) translate([x1 - 6, y_pin, s*pin_sp/2]) rotate([0, 90, 0]) cylinder(d = pogo_hole, h = 7, $fn = 24);
        translate([x1 - 2.5, y_pin, -band_w/2 - H]) cylinder(d = 2.2, h = H + band_w/2 + pin_sp/2, $fn = 24); // wires
    }
}

module base() {
    difference() {
        union() {
            cylinder(r = R, h = H - 1.2, $fn = 8);                    // octagonal lantern base
            translate([0, 0, H - 1.2]) cylinder(r1 = R, r2 = R - 1.2, h = 1.2, $fn = 8);
            for (a = [0 : 45 : 359]) rotate(a + 22.5) translate([R*cos(22.5) - 0.2, -1.5, 0]) cube([1.6, 3, H - 2]); // ribs
        }
        head_pocket();
        // electronics bay from below + cover recess
        translate([-board[0]/2 - 1, -R + 4, -0.01]) cube([board[0] + 2, board[1] + 6, board[2] + 2]);
        translate([0, 0, -0.01]) linear_extrude(1.6) offset(r = 0.25) cover_2d();
        // USB-C opening, -Y face
        translate([-usb_slot[0]/2, -R - 1, 1.6 + 2.0]) cube([usb_slot[0], 10, usb_slot[1]]);
        // wire passage from tower into bay
        ring_in_cradle() translate([-head_w/2 - 2.8, y_pin, -50]) cylinder(d = 2.2, h = 50, $fn = 24);
        translate([-head_w/2 - 2.8 + ring_off[0], ring_off[1] + y_pin, 0]) cylinder(d = 2.2, h = H, $fn = 24);
        // engraved emblem on top (behind the ring)
        translate([0, -R + 8, H - 0.6]) linear_extrude(1) gl_symbol(9);
        for (p = cover_screws()) translate([p[0], p[1], -1]) cylinder(d = 1.7, h = 8, $fn = 20);
    }
    // mandrel
    ring_in_cradle() translate([0, 0, -band_w/2]) {
        cylinder(d = mandrel_d, h = band_w + 1);
        translate([0, 0, band_w + 1]) cylinder(d1 = mandrel_d, d2 = mandrel_d - 2, h = 1.5);
    }
    translate([ring_off[0], ring_off[1], H - 1]) cylinder(d = mandrel_d, h = 1.01);
    tower();
}

function cover_screws() = [[-board[0]/2 - 4, -R + 8], [board[0]/2 + 4, -R + 8],
                           [-board[0]/2 - 4, -R + 4 + board[1] + 2], [board[0]/2 + 4, -R + 4 + board[1] + 2]];
module cover_2d() hull() for (p = cover_screws()) translate(p) circle(r = 3);
module cover() difference() {
    linear_extrude(1.5) cover_2d();
    for (p = cover_screws()) translate([p[0], p[1], -1]) { cylinder(d = 2.3, h = 5, $fn = 20); translate([0, 0, 1.6]) cylinder(d1 = 2.3, d2 = 4.2, h = 1, $fn = 20); }
}

if (part == "base") base(); else if (part == "cover") cover();
