"""Build the Duckling print pack: official parts + reshaped Duckling shells in official orientation.

usage: make_print_pack.py <workdir> <pack_dir>
"""
import json
import os
import shutil
import sys

import numpy as np
from scipy.spatial import cKDTree

S, PACK = sys.argv[1], sys.argv[2]
ns = {}
exec(open(f"{S}/build/align_to_print.py").read().split('if __name__ == "__main__":')[0], ns)
read_stl, write_stl, volume, samples, bed_contact = ns["read_stl"], ns["write_stl"], ns["volume"], ns["samples"], ns["bed_contact"]

frames = json.load(open(f"{S}/mujoco_mesh_frames.json"))
transforms = json.load(open(f"{S}/print_transforms.json"))
HEAD_GROUP = {"head", "head_bot_sheet", "left_antenna_holder", "right_antenna_holder"}
SHELLS = ["head", "head_bot_sheet", "left_antenna_holder", "right_antenna_holder", "body_front", "body_back",
          "body_middle_top", "body_middle_bottom", "battery_pack_lid", "left_cache", "right_cache"]


def closed(tris):
    """True when every edge is shared by exactly two triangles (a printable closed solid)."""
    v = np.round(tris.reshape(-1, 3), 3)
    _, idx = np.unique(v, axis=0, return_inverse=True)
    f = idx.reshape(-1, 3)
    e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return bool(np.all(counts == 2)), int((counts != 2).sum())


for sub in ("1_original_parts", "2_duckling_shells", "3_duckling_bill"):
    os.makedirs(f"{PACK}/{sub}", exist_ok=True)

for f in sorted(os.listdir(f"{S}/print_official")):
    if f[:-4] not in SHELLS:
        shutil.copy(f"{S}/print_official/{f}", f"{PACK}/1_original_parts/{f}")

report = []
for name in SHELLS:
    src = f"{S}/reshape/stl_official/duckling/{name}.stl" if name in HEAD_GROUP else f"{S}/reshape/stl/duckling/{name}.stl"
    local = read_stl(src)                                     # MuJoCo-centred frame, mm
    Rq, pos = np.array(frames[name]["R"]), np.array(frames[name]["pos"]) * 1000.0
    R, t = np.array(transforms[name]["R"]), np.array(transforms[name]["t"])
    out = (local @ Rq.T + pos) @ R.T + t                      # -> original STL frame -> official print frame
    official = read_stl(f"{S}/print_official/{name}.stl")
    out[..., 2] += official[..., 2].min() - out[..., 2].min()  # rest on the official part's bed plane
    write_stl(f"{PACK}/2_duckling_shells/{name}_duckling.stl", out)
    d, _ = cKDTree(samples(official, 200000, 1)).query(samples(out, 20000, 2))
    ok, open_edges = closed(out)
    report.append((name, volume(official) / 1000, volume(out) / 1000, np.median(d), np.percentile(d, 99), ok, open_edges,
                   bed_contact(official), bed_contact(out)))

shutil.copy(f"{S}/designs/duck-bill.stl", f"{PACK}/3_duckling_bill/duck_bill.stl")
bill = read_stl(f"{PACK}/3_duckling_bill/duck_bill.stl")
print(f"{'part':22s} {'official':>8s} {'duckling':>8s}  {'shift med/99% mm':>17s}  closed  bed mm2 off/duck")
for r in report:
    print(f"{r[0]:22s} {r[1]:7.1f}  {r[2]:7.1f}   {r[3]:6.1f} / {r[4]:6.1f}     {'yes' if r[5] else 'NO (' + str(r[6]) + ')':5s}  {r[7]:6.0f} / {r[8]:6.0f}")
ok, n_open = closed(bill)
print(f"duck_bill: {volume(bill) / 1000:.1f} cm3, closed {ok}, bed contact {bed_contact(bill):.0f} mm2")
print("files:", {sub: len(os.listdir(f"{PACK}/{sub}")) for sub in sorted(os.listdir(PACK)) if os.path.isdir(f"{PACK}/{sub}")})
