// =====================================================================
// PROJECT GREEN LANTERN — parametric ring library  (v0.1, PROVISIONAL)
// ---------------------------------------------------------------------
// All dimensions in millimetres.  Every value marked PROVISIONAL must be
// replaced by a measurement before a "final" print (see README / tests).
//
// Coordinate frame (assembly):
//   * finger axis  = Z   (band mid-plane at z = 0)
//   * head/emblem  = +Y  (emblem face normal points +Y)
//   * charging contacts on the head's -X face, switch on the +X face
//
// Part files (main_ring.scad, emblem.scad, ...) include this library and
// set `part` / `layout`.  Override anything from the command line, e.g.
//   openscad -D 'design="A"' -D finger_d=18.6 -o out.stl main_ring.scad
// =====================================================================

$fn = 96;

// ----------------------------- user parameters -----------------------
design    = "B";        // "A" compact | "B" classic | "C" max illumination
layout    = "print";    // "print" (plate-ready) | "assembly" (ring frame)
explode   = 0;          // assembly explode distance (mm), 0 = assembled

// Finger.  PROVISIONAL: 19.0 mm ≈ UK size R½ (BS 6820: circ = 37.5 + 1.25*n).
// Measure with the printed sizer (sizer.scad) and set this.
finger_d  = 19.0;

// Payment architecture:
//   "core"   – an intact, issuer-activated commercial payment ring is the
//              inner band; the printed ring is a shell around it (PRIMARY)
//   "insert" – an intact flat payment insert/module sits under the lens
//   "none"   – no payment hardware (fit / lighting prototypes)
payment_mode = "core";

// Donor payment ring (core mode).  PROVISIONAL until the ring is in hand.
core_t     = 2.3;       // radial wall of donor ring
core_w     = 7.0;       // axial width of donor ring
core_clear = 0.25;      // radial clearance shell<->core (FDM: 0.25, resin: 0.12)
core_ax_clear = 0.3;    // axial clearance

// Flat payment insert (insert mode).  PROVISIONAL — e.g. SIM-size 25x15.
mod_l = 15.0;  mod_w = 12.0;  mod_t = 0.8;

// Fit / tolerance knobs
fit_clear   = 0.15;     // finger bore allowance when there is no core
slide_clear = 0.20;     // per side, sliding parts inside head cavity
press_clear = 0.12;     // per side, light press fits (lens, diffuser)

// ----------------------------- design presets ------------------------
//            head_w head_l head_r shell_t chamber lens bezel  bat_l bat_w bat_t n_led emblem_d
PA = [         18.0,  15.0,  2.5,   1.2,    1.4,   0.9,  1.0,  10.0, 10.0, 3.0,  3,    10.5];
PB = [         21.0,  17.0,  3.0,   1.4,    2.0,   1.0,  1.2,  12.0, 10.0, 3.0,  3,    13.0];
PC = [         23.0,  19.0,  3.0,   1.4,    2.8,   1.0,  1.2,  15.0, 12.0, 4.0,  5,    15.0];
PS = design == "A" ? PA : design == "C" ? PC : PB;

head_w   = PS[0];   // across finger (X)
head_l   = PS[1];   // along finger (Z)
head_r   = PS[2];   // plan-view corner radius
shell_t  = PS[3];   // printed band wall
chamber_h= PS[4];   // diffuser / light-chamber height
lens_t   = PS[5];   // lens base plate
bezel_t  = PS[6];   // emblem bezel
bat_l    = PS[7];   bat_w = PS[8];  bat_t = PS[9];   // LiPo envelope incl. PCM bulge
n_led    = PS[10];
emblem_d = PS[11];

// Fixed construction values
wall      = 1.2;    // head side wall
floor_t   = 1.0;    // between core/bore and cavity floor
boss_b    = 3.2;    // corner screw boss size
screw_pilot = 1.1;  // M1.4 self-tapping pilot
screw_clear = 1.6;
tray_floor= 0.6;
tray_wall = 0.6;
ferrite_t = 0.3;    // NFC ferrite sheet under battery
wire_gap  = 0.4;
pcb_t     = 0.8;
pin_d     = 1.0;    // brass contact pins (charging)
pin_sp    = 3.5;    // contact pitch (Z)
sw_slot_w = 3.2;    // slide-switch actuator window (Z)
sw_slot_h = 1.8;
led_pocket= [2.0, 1.3, 0.9];  // 0603 LED recess in diffuser underside

// ----------------------------- derived geometry ----------------------
core_mode = payment_mode == "core";
core_id   = finger_d;                    // core ring sits on the finger
core_od   = core_id + 2*core_t;
bore_d    = core_mode ? core_od + 2*core_clear : finger_d + 2*fit_clear;
shell_od  = bore_d + 2*shell_t;

lip_t       = 0.8;   // fixed side lip (axial)
lip_overlap = 0.8;   // radial overlap of lip onto core side face
ret_t       = 0.8;   // retainer C-ring thickness
groove_d    = 0.6;   // retainer groove depth
groove_w    = ret_t + 0.15;
end_wall    = 0.8;

band_w = core_mode ? lip_t + core_w + core_ax_clear + groove_w + end_wall
                   : (design == "A" ? 5.0 : 6.0);
z_lo   = -band_w/2;                      // lip side
z_core0= z_lo + lip_t;                   // core starts here
z_grv0 = z_core0 + core_w + core_ax_clear;
z_grv1 = z_grv0 + groove_w;

insert_h = payment_mode == "insert" ? mod_t + 0.6 : 0;
cart_h   = tray_floor + ferrite_t + bat_t + wire_gap + pcb_t;

y_cf  = bore_d/2 + floor_t;                       // cavity floor
y_cart1 = y_cf + cart_h;                          // top of cartridge (PCB top)
y_diff1 = y_cart1 + chamber_h;                    // top of diffuser
y_ins1  = y_diff1 + insert_h;                     // top of module holder
y_ht    = y_ins1 + lens_t;                        // head top (lens top face)
y_top   = y_ht + bezel_t;                         // outermost point
y_pin   = y_cf + tray_floor + ferrite_t + bat_t/2 + 0.4;  // contact pin height

cav_w = head_w - 2*wall;
cav_l = head_l - 2*wall;

// Sanity checks (OpenSCAD 2021 has assert)
assert(cav_w > bat_l + 2*tray_wall + 0.8, "battery too long for head");
assert(cav_l > bat_w + 2*tray_wall + 0.8, "battery too wide for head");
assert(emblem_d < min(cav_w, cav_l) - 0.6, "emblem larger than lens");
assert(payment_mode != "insert" || (mod_l < cav_w - 1 && mod_w < cav_l - 1),
       "payment insert does not fit this head preset");

// ----------------------------- 2D helpers -----------------------------
// 2D (u,v) -> 3D (x = u, z = -v) when extruded with toY()
module rrect(w, l, r) { offset(r = r) square([w - 2*r, l - 2*r], center = true); }

module toY(y0, h) { translate([0, y0, 0]) rotate([-90, 0, 0]) linear_extrude(h) children(); }

module screw_pts() {
    for (s = [-1, 1]) translate([s*(cav_w/2 - boss_b/2 + 0.4), s*(cav_l/2 - boss_b/2 + 0.4)]) children();
}

// Cavity footprint: rounded rectangle minus two diagonal screw bosses
module cav_2d(o = 0) {
    offset(r = -o)
    offset(r = 0.5) offset(delta = -0.5)
    difference() {
        rrect(cav_w, cav_l, max(0.6, head_r - wall));
        for (s = [-1, 1]) translate([s*(cav_w/2 - boss_b/2), s*(cav_l/2 - boss_b/2)])
            square(boss_b + 0.02, center = true);
    }
}

// Green Lantern Corps emblem (stylised: ring between two bars)
module gl_symbol(d) {
    ro = d*0.36; ri = d*0.22;
    bar_w = d*0.86; bar_h = d*0.14; bar_y = d*0.43;
    union() {
        difference() { circle(ro); circle(ri); }
        for (s = [-1, 1]) translate([0, s*bar_y]) square([bar_w, bar_h], center = true);
        // short necks so the bars are solidly joined to the ring
        for (s = [-1, 1]) translate([0, s*(bar_y - bar_h/2 + 0.001 - d*0.02)])
            square([d*0.30, d*0.06], center = true);
    }
}

function led_pos(i) = n_led == 1 ? [0, 0] :
    (n_led == 5 && i == 4) ? [0, 0] :
    let(n = n_led == 5 ? 4 : n_led, a = 90 + 360*i/n)
        [emblem_d*0.30*cos(a), emblem_d*0.30*sin(a)];

// ----------------------------- RING BODY -----------------------------
module body_outer() {
    // band disc + a head whose side faces stay vertical (flat contact face)
    translate([0, 0, -band_w/2]) cylinder(d = shell_od, h = band_w);
    hull() {
        intersection() {
            translate([0, 0, -band_w/2]) cylinder(d = shell_od, h = band_w);
            translate([-head_w/2, 0, -band_w]) cube([head_w, shell_od, 2*band_w]);
        }
        toY(shell_od/2 - 2.0, y_ht - (shell_od/2 - 2.0)) rrect(head_w, head_l, head_r);
    }
}

module ring_body() {
    difference() {
        body_outer();
        // ---- finger / core bore
        if (core_mode) {
            translate([0, 0, z_core0]) cylinder(d = bore_d, h = band_w);           // core seat + entry
            translate([0, 0, -50]) cylinder(d = core_od - 2*lip_overlap, h = 100);  // lip opening
            translate([0, 0, z_grv0]) cylinder(d = bore_d + 2*groove_d, h = groove_w); // retainer groove
            // comfort chamfer on lip edge
            translate([0, 0, z_lo - 0.01]) cylinder(d1 = core_od - 2*lip_overlap + 0.8,
                                                   d2 = core_od - 2*lip_overlap, h = 0.4);
        } else {
            translate([0, 0, -50]) cylinder(d = bore_d, h = 100);
            translate([0, 0, -band_w/2 - 0.01]) cylinder(d1 = bore_d + 0.8, d2 = bore_d, h = 0.41);
            translate([0, 0,  band_w/2 - 0.40]) cylinder(d1 = bore_d, d2 = bore_d + 0.8, h = 0.41);
        }
        // ---- head cavity (open at top, closed by lens + bezel)
        toY(y_cf, y_ht - y_cf + 1) cav_2d(0);
        // ---- screw pilots into bosses
        toY(y_ht - 4.0, 5) screw_pts() circle(d = screw_pilot, $fn = 24);
        // ---- charging contact U-slots, -X wall (open to top for cartridge removal)
        for (s = [-1, 1]) translate([-head_w/2 - 1, -pin_d/2 - 0.15 + y_pin, s*pin_sp/2 - (pin_d + 0.3)/2])
            cube([wall + 1.5, y_ht - y_pin + 1, pin_d + 0.3]);
        // ---- contact recess (keeps pins 0.2 mm below surface, fingers cannot bridge easily)
        translate([-head_w/2 - 0.5, y_pin - 1.6, -pin_sp/2 - 1.6]) cube([0.8, 3.2, pin_sp + 3.2]);  // 0.3 mm deep
        // ---- slide-switch window, +X wall
        translate([head_w/2 - wall - 1, y_cart1 - pcb_t - sw_slot_h + 0.2, -sw_slot_w/2])
            cube([wall + 2, y_ht - (y_cart1 - pcb_t - sw_slot_h) + 1, sw_slot_w]);
    }
}

// ----------------------------- RETAINER C-RING ------------------------
module retainer() {
    gap = 4.0;
    difference() {
        cylinder(d = bore_d + 2*groove_d - 0.25, h = ret_t);
        translate([0, 0, -1]) cylinder(d = core_od - 1.4, h = ret_t + 2);
        translate([-gap/2, -(bore_d + 10), -1]) cube([gap, bore_d + 10, ret_t + 2]);  // split at -Y (palm side)
    }
}

// ----------------------------- ELECTRONICS CARTRIDGE ------------------
module cartridge() {
    o = slide_clear;
    difference() {
        toY(y_cf, cart_h) cav_2d(o);
        // PCB recess from top
        toY(y_cart1 - pcb_t - 0.05, pcb_t + 1) cav_2d(o + tray_wall);
        // battery + ferrite pocket
        translate([0.6, y_cf + tray_floor, 0])
            translate([-(bat_l + 0.4)/2, 0, -(bat_w + 0.4)/2]) cube([bat_l + 0.4, cart_h, bat_w + 0.4]);
        // wire channel to contact pins
        translate([-cav_w/2 + o + tray_wall + 0.2, y_pin - 0.5, -pin_sp/2 - 0.6])
            cube([cav_w/2, 1.6, pin_sp + 1.2]);
        // contact pin holes (Ø1.0 brass rod, press fit)
        for (s = [-1, 1]) translate([-cav_w/2 - 1, y_pin, s*pin_sp/2]) rotate([0, 90, 0])
            cylinder(d = pin_d - 0.05, h = 4, $fn = 24);
        // switch notch at +X top
        translate([cav_w/2 - o - tray_wall - 0.5, y_cart1 - pcb_t - sw_slot_h + 0.2, -sw_slot_w/2])
            cube([tray_wall + 1.5, sw_slot_h + pcb_t + 1, sw_slot_w]);
    }
}

// Visual stand-ins (NOT printed) for interference checks
module battery_dummy() { translate([0.6, y_cf + tray_floor + ferrite_t, 0])
    translate([-bat_l/2, 0, -bat_w/2]) cube([bat_l, bat_t, bat_w]); }
module pcb_dummy()     { toY(y_cart1 - pcb_t, pcb_t) cav_2d(slide_clear + tray_wall + 0.1); }
module pins_dummy()    { for (s = [-1, 1]) translate([-head_w/2 + 0.2, y_pin, s*pin_sp/2]) rotate([0, 90, 0])
    cylinder(d = pin_d, h = (head_w - cav_w)/2 + slide_clear + tray_wall + 0.6 - 0.2, $fn = 24); }
module core_dummy()    { if (core_mode) translate([0, 0, z_core0]) difference() {
    cylinder(d = core_od, h = core_w); translate([0, 0, -1]) cylinder(d = core_id, h = core_w + 2); } }

// ----------------------------- DIFFUSER / LIGHT CHAMBER ---------------
module diffuser() {
    difference() {
        toY(y_cart1, chamber_h) cav_2d(press_clear);
        for (i = [0 : n_led - 1]) let(p = led_pos(i))
            translate([p[0], y_cart1 - 0.01, -p[1]])
                translate([-led_pocket[0]/2, 0, -led_pocket[1]/2]) cube([led_pocket[0], led_pocket[2], led_pocket[1]]);
    }
}

// ----------------------------- PAYMENT INSERT HOLDER ------------------
module module_holder() {
    if (payment_mode == "insert") difference() {
        toY(y_diff1, insert_h) cav_2d(press_clear);
        translate([-(mod_l + 0.3)/2, y_diff1 + 0.6, -(mod_w + 0.3)/2]) cube([mod_l + 0.3, insert_h, mod_w + 0.3]);
    }
}

// ----------------------------- LENS (translucent green) --------------
module lens() {
    toY(y_ins1, lens_t) cav_2d(press_clear);
    toY(y_ht - 0.01, bezel_t + 0.01) offset(delta = -0.12) gl_symbol(emblem_d);
    toY(y_ht - 0.01, 0.61) circle(d = 1.2, $fn = 24);               // locating pin for centre disc
}

// Opaque centre "pupil" of the emblem (the island inside the ring).
// Separate part: presses onto the lens pin; a drop of clear CA optional.
module emblem_center() {
    difference() {
        toY(y_ht, bezel_t) circle(r = emblem_d*0.22 - 0.12);
        toY(y_ht - 0.01, 0.71) circle(d = 1.3, $fn = 24);
    }
}

// ----------------------------- BEZEL / EMBLEM CAP (opaque) -----------
module bezel() {
    difference() {
        hull() {
            toY(y_ht, bezel_t - 0.4) rrect(head_w, head_l, head_r);
            toY(y_ht, bezel_t) offset(delta = -0.4) rrect(head_w, head_l, head_r);
        }
        toY(y_ht - 1, bezel_t + 2) union() { gl_symbol(emblem_d); circle(r = emblem_d*0.36); }
        toY(y_ht - 1, bezel_t + 2) screw_pts() circle(d = screw_clear, $fn = 24);
        // countersink
        screw_pts_3d() translate([0, y_top - 0.6, 0]) rotate([-90, 0, 0]) cylinder(d1 = screw_clear, d2 = 2.8, h = 0.61, $fn = 24);
    }
}
module screw_pts_3d() { for (s = [-1, 1]) translate([s*(cav_w/2 - boss_b/2 + 0.4), 0, -s*(cav_l/2 - boss_b/2 + 0.4)]) children(); }

// ----------------------------- ASSEMBLY ------------------------------
module assembly(show_dummies = true) {
    color("#1a1a1a") ring_body();
    if (core_mode) {
        color("#333")  translate([0, 0, z_grv0 + 0.075 - explode]) retainer();
        if (show_dummies) color("#555") translate([0, 0, -explode]) core_dummy();
    }
    translate([0, explode*1, 0]) {
        color("#e8e8e8") cartridge();
        if (show_dummies) { color("#b0b0b0") battery_dummy(); color("#1b6e2b") pcb_dummy(); color("gold") pins_dummy(); }
    }
    translate([0, explode*2, 0]) color("#ffffff", 0.7) diffuser();
    translate([0, explode*2.5, 0]) color("#00cc44", 0.6) module_holder();
    translate([0, explode*3, 0]) color("#00ff55", 0.7) lens();
    translate([0, explode*4, 0]) { color("#0b3d1a") bezel(); color("#0b3d1a") emblem_center(); }
}

// Print-orientation helpers: rotate so the emblem face (+Y) is up (+Z) or down.
module face_up(y0)   { translate([0, 0, -y0]) rotate([90, 0, 0]) children(); }
module face_down(y1) { translate([0, 0,  y1]) rotate([-90, 0, 0]) children(); }
