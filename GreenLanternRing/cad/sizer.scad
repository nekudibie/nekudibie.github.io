// Ring-size gauge set.  Print, try on, pick the one that slides over the
// knuckle and stays put.  UK sizes per BS 6820: inside circumference
// = 37.5 mm + 1.25 mm per letter (A = 0).  Half sizes add 0.625 mm.
$fn = 96;
sizes  = ["N","O","P","Q","R","S","T","U","V","W"];
letters= "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
band_w = 7.0;   // match the planned ring width (B ≈ 9.9 in core mode)
wall   = 1.6;
function idx(c) = search(c, letters)[0];
function uk_d(c, half = 0) = (37.5 + 1.25*idx(c) + 0.625*half) / PI;
module gauge(c) {
    d = uk_d(c);
    difference() {
        union() {
            cylinder(d = d + 2*wall, h = band_w);
            translate([d/2 + wall - 0.6, -3, 0]) cube([2.6, 6, band_w]);
        }
        translate([0, 0, -1]) cylinder(d = d, h = band_w + 2);
        translate([d/2 + wall + 1.5, 0, band_w/2]) rotate([90, 0, 90])
            linear_extrude(1) text(c, size = 4.2, halign = "center", valign = "center", font = "DejaVu Sans:style=Bold");
    }
}
for (i = [0 : len(sizes) - 1]) translate([(i % 5) * 32, floor(i / 5) * 30, 0]) gauge(sizes[i]);
