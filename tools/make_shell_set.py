"""Put one reshaped design's 11 shells into the official print orientation and check them.

usage: make_shell_set.py <workdir> <concept> <out_dir>
Head-group parts come from <workdir>/reshape/stl_official/<concept>/ (rebuilt from the current
official head.stl); the rest from <workdir>/reshape/stl/<concept>/. Output: <name>_<concept>.stl
"""
import json
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

W, CONCEPT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
ns = {}
exec(open(f"{W}/build/align_to_print.py").read().split('if __name__ == "__main__":')[0], ns)
read_stl, write_stl, volume, samples, bed_contact = ns["read_stl"], ns["write_stl"], ns["volume"], ns["samples"], ns["bed_contact"]

frames = json.load(open(f"{W}/mujoco_mesh_frames.json"))
transforms = json.load(open(f"{W}/print_transforms.json"))
HEAD_GROUP = {"head", "head_bot_sheet", "left_antenna_holder", "right_antenna_holder"}
SHELLS = ["head", "head_bot_sheet", "left_antenna_holder", "right_antenna_holder", "body_front", "body_back",
          "body_middle_top", "body_middle_bottom", "battery_pack_lid", "left_cache", "right_cache"]

os.makedirs(OUT, exist_ok=True)
print(f"{CONCEPT}: {'part':22s} {'official':>8s} {'new':>7s}  {'shift med/99% mm':>17s}  bed mm2 off/new")
for name in SHELLS:
    src = f"{W}/reshape/stl_official/{CONCEPT}/{name}.stl" if name in HEAD_GROUP else f"{W}/reshape/stl/{CONCEPT}/{name}.stl"
    local = read_stl(src)                                     # MuJoCo-centred frame, mm
    Rq, pos = np.array(frames[name]["R"]), np.array(frames[name]["pos"]) * 1000.0
    R, t = np.array(transforms[name]["R"]), np.array(transforms[name]["t"])
    out = (local @ Rq.T + pos) @ R.T + t                      # -> original STL frame -> official print frame
    official = read_stl(f"{W}/print_official/{name}.stl")
    out[..., 2] += official[..., 2].min() - out[..., 2].min()  # rest on the official part's bed plane
    write_stl(f"{OUT}/{name}_{CONCEPT}.stl", out)
    d, _ = cKDTree(samples(official, 200000, 1)).query(samples(out, 20000, 2))
    print(f"{CONCEPT}: {name:22s} {volume(official) / 1000:7.1f}  {volume(out) / 1000:7.1f}   {np.median(d):6.1f} / {np.percentile(d, 99):6.1f}"
          f"      {bed_contact(official):6.0f} / {bed_contact(out):6.0f}")
