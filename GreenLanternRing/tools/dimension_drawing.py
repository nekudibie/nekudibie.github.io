#!/usr/bin/env python3
"""Dimensional drawing (two orthographic sections) generated from the
assembly-frame STLs, so the dimensions shown are measured from the meshes.
Usage: python3 tools/dimension_drawing.py [A|B|C]
"""
import sys
from pathlib import Path
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
d = sys.argv[1] if len(sys.argv) > 1 else "B"
A = ROOT / "stl" / f"design_{d}" / "assembly_frame"
parts = {"body": "#222", "core_dummy": "#888", "cartridge": "#bbb", "diffuser": "#eee",
         "lens": "#2c5", "bezel": "#063", "center": "#063", "retainer": "#555"}
meshes = {k: trimesh.load(A / f"{k}.stl", force="mesh") for k in parts if (A / f"{k}.stl").exists()}


def draw_section(ax, normal, origin, ax_u, ax_v, title):
    for k, m in meshes.items():
        s = m.section(plane_origin=origin, plane_normal=normal)
        if s is None:
            continue
        for poly in s.discrete:
            ax.plot(poly[:, ax_u], poly[:, ax_v], color=parts[k] if parts[k] not in ("#eee", "#bbb") else "#777", lw=1.2)
    ax.set_aspect("equal"); ax.set_title(title, fontsize=10); ax.grid(alpha=0.3)


def dim(ax, p0, p1, text, off=(0, 0), horiz=True):
    ax.annotate("", p0, p1, arrowprops=dict(arrowstyle="<->", lw=0.8))
    mid = ((p0[0] + p1[0]) / 2 + off[0], (p0[1] + p1[1]) / 2 + off[1])
    ax.text(*mid, text, fontsize=8, ha="center", va="center", rotation=0 if horiz else 90,
            bbox=dict(fc="white", ec="none", pad=0.5))


fig, axs = plt.subplots(1, 2, figsize=(12, 6.5))
b, bz, core = meshes["body"], meshes["bezel"], meshes.get("core_dummy")
# Front section: plane z=0 (looking along the finger), axes x (u) and y (v)
draw_section(axs[0], [0, 0, 1], [0, 0, 0], 0, 1, f"Section A-A (finger axis), design {d}")
# Side section: plane x=0, axes z (u) and y (v)
draw_section(axs[1], [1, 0, 0], [0, 0, 0], 2, 1, f"Section B-B (across finger), design {d}")

xmin, xmax = b.bounds[:, 0]; ymin = b.bounds[0, 1]; ytop = bz.bounds[1, 1]
r_f = float(np.min(np.linalg.norm(core.vertices[:, :2], axis=1))) if core is not None else None
ax = axs[0]
dim(ax, (xmin, ymin - 3), (xmax, ymin - 3), f"{xmax - xmin:.1f} overall width")
dim(ax, (xmax + 3, ymin), (xmax + 3, ytop), f"{ytop - ymin:.1f} overall height", horiz=False)
if r_f:
    dim(ax, (-r_f, 0), (r_f, 0), f"Ø{2 * r_f:.1f} finger")
    dim(ax, (xmin - 3, r_f), (xmin - 3, ytop), f"{ytop - r_f:.1f} above finger", horiz=False)
hw = b.section(plane_origin=[0, ytop - 2, 0], plane_normal=[0, 1, 0]).vertices[:, 0]
dim(ax, (hw.min(), ytop + 2.5), (hw.max(), ytop + 2.5), f"head {hw.max() - hw.min():.1f}")
ax.set_xlim(xmin - 9, xmax + 9); ax.set_ylim(ymin - 6, ytop + 6)

ax = axs[1]
zmin, zmax = b.bounds[:, 2]
bw = b.section(plane_origin=[0, ymin + 0.5, 0], plane_normal=[0, 1, 0]).vertices[:, 2]
dim(ax, (zmin, ytop + 2.5), (zmax, ytop + 2.5), f"head {zmax - zmin:.1f}")
dim(ax, (bw.min(), ymin - 3), (bw.max(), ymin - 3), f"band {bw.max() - bw.min():.1f}")
ax.set_xlim(zmin - 8, zmax + 8); ax.set_ylim(ymin - 6, ytop + 6)
fig.suptitle("Green Lantern ring v0.1: dimensions in mm, measured from the CAD meshes "
             "(PROVISIONAL: finger Ø and core size are placeholders)", fontsize=10)
fig.tight_layout()
out = ROOT / "images" / f"dimensions_design_{d}.png"
fig.savefig(out, dpi=130)
print("wrote", out)
