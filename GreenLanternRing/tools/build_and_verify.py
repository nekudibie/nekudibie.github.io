#!/usr/bin/env python3
"""Export every STL from the OpenSCAD sources and verify the meshes.

Usage (from GreenLanternRing/):
    python3 tools/build_and_verify.py              # all designs
    python3 tools/build_and_verify.py --design B   # one design
    python3 tools/build_and_verify.py -D finger_d=18.6   # extra overrides

Requires: openscad (2021.01+), python3, numpy, trimesh, manifold3d, matplotlib.

Checks performed per mesh:
  * watertight / winding-consistent / positive volume
  * number of disconnected bodies
  * bounding box, volume, estimated mass (PETG 1.27 g/cm3)
  * sampled minimum wall thickness (ray-cast from surface inward)
  * print-orientation overhang share (faces steeper than 45 deg facing down)
Assembly checks (design layout="assembly"): pairwise interference volume
between parts that must not overlap.
"""
import argparse, itertools, json, subprocess, sys
from pathlib import Path
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
CAD, STL, IMG, TESTS = ROOT / "cad", ROOT / "stl", ROOT / "images", ROOT / "tests"
PETG = 1.27e-3  # g/mm3

# (output name, scad file, overrides)
PRINT_PARTS = [
    ("ring_body",         "main_ring.scad",           {"part": "body"}),
    ("retainer_cring",    "main_ring.scad",           {"part": "retainer"}),
    ("emblem_bezel",      "emblem.scad",              {"part": "bezel"}),
    ("emblem_lens",       "emblem.scad",              {"part": "lens"}),
    ("emblem_center_disc", "emblem.scad",             {"part": "center"}),
    ("electronics_cartridge", "electronics_housing.scad", {"part": "cartridge"}),
    ("led_diffuser",      "electronics_housing.scad", {"part": "diffuser"}),
]
SHARED_PARTS = [  # design-independent (use design B head for the cradle)
    ("charging_cradle_base",  "charging_cradle.scad", {"part": "base"}),
    ("charging_cradle_cover", "charging_cradle.scad", {"part": "cover"}),
    ("ring_sizer_set",        "sizer.scad",           {}),
    ("jig_coil_former",       "jigs.scad",            {"part": "coil_former"}),
    ("jig_pancake_base",      "jigs.scad",            {"part": "pancake_base"}),
    ("jig_pancake_top",       "jigs.scad",            {"part": "pancake_top"}),
    ("payment_insert_holder_B_insert_mode", "payment_holder.scad", {}),
]
ASM_PARTS = [  # name, scad, overrides (layout=assembly)
    ("body",      "main_ring.scad",           {"part": "body"}),
    ("retainer",  "main_ring.scad",           {"part": "retainer"}),
    ("cartridge", "electronics_housing.scad", {"part": "cartridge"}),
    ("diffuser",  "electronics_housing.scad", {"part": "diffuser"}),
    ("lens",      "emblem.scad",              {"part": "lens"}),
    ("bezel",     "emblem.scad",              {"part": "bezel"}),
    ("center",    "emblem.scad",              {"part": "center"}),
]


def scad_val(v):
    return f'"{v}"' if isinstance(v, str) and not v.replace(".", "").isdigit() else str(v)


def run_scad(scad, out, overrides, extra):
    cmd = ["openscad", "-o", str(out)]
    for k, v in overrides.items():
        cmd += ["-D", f"{k}={scad_val(v)}"]
    for e in extra:
        cmd += ["-D", e]
    cmd.append(str(CAD / scad))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists() or "ERROR" in r.stderr:
        sys.exit(f"OpenSCAD failed for {out.name}:\n{r.stderr}")
    return r.stderr


def min_wall(mesh, n=1500, seed=1):
    """Sampled wall thickness: cast a ray inward from surface samples."""
    pts, fi = trimesh.sample.sample_surface(mesh, n, seed=seed)
    dirs = -mesh.face_normals[fi]
    origins = pts + dirs * 1e-3
    locs, idx_ray, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
    if len(idx_ray) == 0:
        return float("nan"), float("nan")
    d = np.linalg.norm(locs - origins[idx_ray], axis=1)
    d = d[d > 0.02]
    return float(d.min()), float(np.percentile(d, 2))


def overhang_share(mesh, limit_deg=45):
    nz = mesh.face_normals[:, 2]
    zmin = mesh.bounds[0, 2]
    on_bed = mesh.triangles_center[:, 2] < zmin + 0.05
    down = (nz < -np.cos(np.radians(90 - limit_deg))) & ~on_bed
    return float(mesh.area_faces[down].sum() / mesh.area)


def check_mesh(path):
    m = trimesh.load(path, force="mesh")
    bodies = m.split(only_watertight=False)
    mw, p2 = min_wall(m)
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "watertight": bool(m.is_watertight),
        "winding_consistent": bool(m.is_winding_consistent),
        "bodies": len(bodies),
        "volume_mm3": round(float(m.volume), 1),
        "mass_g_PETG": round(float(m.volume) * PETG, 2),
        "bbox_mm": [round(float(x), 2) for x in m.extents],
        "min_wall_mm_sampled": round(mw, 2),
        "wall_p2_mm": round(p2, 2),
        "overhang_share_45deg": round(overhang_share(m), 3),
    }


def interference(paths):
    meshes = {k: trimesh.load(p, force="mesh") for k, p in paths.items()}
    out = []
    for a, b in itertools.combinations(meshes, 2):
        try:
            inter = trimesh.boolean.intersection([meshes[a], meshes[b]], engine="manifold")
            v = float(inter.volume) if inter is not None and not inter.is_empty else 0.0
        except Exception as e:  # pragma: no cover
            v = float("nan")
        out.append({"a": a, "b": b, "overlap_mm3": round(v, 3), "pass": bool(v < 0.05)})
    return out


def render(paths, png, title, explode=None, swap=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    colours = {"body": "#202020", "retainer": "#555555", "cartridge": "#d8d8d8", "diffuser": "#f5f5f5",
               "lens": "#22dd55", "bezel": "#0b5d24", "center": "#0b5d24", "core": "#7a7a7a"}
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection="3d")
    allpts = []
    for i, (k, p) in enumerate(paths.items()):
        m = trimesh.load(p, force="mesh")
        if explode:
            m.apply_translation([0, explode.get(k, 0), 0])
        if len(m.faces) > 40000:
            m = m.simplify_quadric_decimation(face_count=40000) if hasattr(m, "simplify_quadric_decimation") else m
        tri = m.triangles
        # simple Lambert shading
        light = np.array([0.4, 0.6, 0.7]); light /= np.linalg.norm(light)
        shade = 0.35 + 0.65 * np.clip(m.face_normals @ light, 0, 1)
        base = np.array(matplotlib.colors.to_rgb(colours.get(k, "#888888")))
        fc = np.clip(base[None, :] * shade[:, None] + 0.08, 0, 1)
        # matplotlib's 3D is (x, y, z) with z up; show ring with head (+Y) up -> swap y/z
        if swap:
            tri = tri[:, :, [0, 2, 1]]
        ax.add_collection3d(Poly3DCollection(tri, facecolors=fc, edgecolors="none"))
        allpts.append(tri.reshape(-1, 3))
    pts = np.vstack(allpts)
    c = (pts.max(0) + pts.min(0)) / 2; r = (pts.max(0) - pts.min(0)).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.view_init(elev=22, azim=-58)
    if swap:
        ax.set_xlabel("X mm"); ax.set_ylabel("Z (finger axis) mm"); ax.set_zlabel("Y (up) mm")
    ax.set_title(title, fontsize=10)
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", choices=["A", "B", "C"], nargs="*", default=["A", "B", "C"])
    ap.add_argument("-D", action="append", default=[], help="extra OpenSCAD override, e.g. finger_d=18.6")
    ap.add_argument("--no-shared", action="store_true")
    a = ap.parse_args()
    STL.mkdir(exist_ok=True); IMG.mkdir(exist_ok=True)
    report = {"overrides": a.D, "parts": [], "assembly": {}, "derived": {}}

    for d in a.design:
        ddir = STL / f"design_{d}"; ddir.mkdir(exist_ok=True)
        for name, scad, ov in PRINT_PARTS:
            out = ddir / f"{name}.stl"
            run_scad(scad, out, {**ov, "design": d}, a.D)
            report["parts"].append({"design": d, "part": name, **check_mesh(out)})
            print("ok", out.relative_to(ROOT))
        # assembly-frame exports for interference checks + renders
        adir = STL / f"design_{d}" / "assembly_frame"; adir.mkdir(exist_ok=True)
        paths = {}
        for name, scad, ov in ASM_PARTS:
            out = adir / f"{name}.stl"
            run_scad(scad, out, {**ov, "design": d, "layout": "assembly"}, a.D)
            paths[name] = out
        core = adir / "core_dummy.stl"
        (CAD / "_core_dummy.scad").write_text("include <gl_lib.scad>\ncore_dummy();\n")
        run_scad("_core_dummy.scad", core, {"design": d}, a.D)
        (CAD / "_core_dummy.scad").unlink()
        paths_with_core = {**paths, "core": core}
        report["assembly"][d] = interference(paths_with_core)
        render(paths_with_core, IMG / f"assembly_design_{d}.png", f"Design {d} – assembled (v0.1, provisional dims)")
        render(paths_with_core, IMG / f"exploded_design_{d}.png", f"Design {d} – exploded",
               explode={"cartridge": 10, "diffuser": 18, "lens": 24, "bezel": 30, "center": 30, "retainer": 0, "core": 0})
        # height above finger + total mass
        b = trimesh.load(paths["body"], force="mesh"); bz = trimesh.load(paths["bezel"], force="mesh")
        core_m = trimesh.load(core, force="mesh") if core.stat().st_size > 0 else None
        finger_r = None
        if core_m is not None and not core_m.is_empty:
            finger_r = float(np.min(np.linalg.norm(core_m.vertices[:, :2], axis=1)))
        report["derived"][d] = {
            "outer_top_y_mm": round(float(bz.bounds[1, 1]), 2),
            "finger_radius_mm": round(finger_r, 2) if finger_r else None,
            "height_above_finger_mm": round(float(bz.bounds[1, 1]) - finger_r, 2) if finger_r else None,
            "band_bottom_thickness_mm": round(float(-b.bounds[0, 1]) - finger_r, 2) if finger_r else None,
            "head_extent_xz_mm": [round(float(x), 2) for x in (b.extents[0], b.extents[2])],
            "printed_mass_g_PETG": round(sum(trimesh.load(p, force='mesh').volume for p in paths.values()) * PETG, 2),
        }

    if not a.no_shared:
        sdir = STL / "shared"; sdir.mkdir(exist_ok=True)
        for name, scad, ov in SHARED_PARTS:
            out = sdir / f"{name}.stl"
            run_scad(scad, out, {**ov, "design": "B"}, a.D)
            report["parts"].append({"design": "shared", "part": name, **check_mesh(out)})
            print("ok", out.relative_to(ROOT))
        # ring sitting in cradle: interference check
        (CAD / "_ring_in_cradle.scad").write_text(
            "include <charging_cradle.scad>\nring_in_cradle() ring_body();\n")
        rc = sdir / "_ring_in_cradle.stl"
        run_scad("_ring_in_cradle.scad", rc, {"design": "B", "part": "none"}, a.D)
        (CAD / "_ring_in_cradle.scad").unlink()
        report["assembly"]["cradle_B"] = interference({"cradle": sdir / "charging_cradle_base.stl", "ring": rc})
        render({"bezel": sdir / "charging_cradle_base.stl", "body": rc}, IMG / "charging_cradle_B.png",
               "Charging cradle with Design B ring", swap=False)
        rc.unlink()

    TESTS.mkdir(exist_ok=True)
    (TESTS / "cad_verification.json").write_text(json.dumps(report, indent=2))
    fails = [p for p in report["parts"] if not (p["watertight"] and p["volume_mm3"] > 0)]
    ifails = [(k, i) for k, v in report["assembly"].items() for i in v if not i["pass"]]
    print(json.dumps(report["derived"], indent=2))
    print(f"mesh failures: {len(fails)}  interference failures: {len(ifails)}")
    for k, i in ifails:
        print("  INTERFERENCE", k, i)
    return 1 if fails or ifails else 0


if __name__ == "__main__":
    sys.exit(main())
