"""Re-pick each part's robot-export -> official-print transform by surface distance, not vertex matching.

Flat or near-symmetric parts (head plate, battery lid, ear caps) have several orientations that match
vertices about equally well, and the vertex score picked a flipped one. Here every one of the 24
proper rotations is refined with ICP and scored by the 99th-percentile distance from dense samples
of one surface to the other; identical parts should come out near zero.
usage: improve_alignment.py <workdir>   (rewrites <workdir>/print_transforms.json)
"""
import itertools
import json
import sys

import numpy as np
from scipy.spatial import cKDTree

W = sys.argv[1]
ns = {}
exec(open(f"{W}/build/align_to_print.py").read().split('if __name__ == "__main__":')[0], ns)
read_stl, samples, kabsch = ns["read_stl"], ns["samples"], ns["kabsch"]

path = f"{W}/print_transforms.json"
transforms = json.load(open(path))


def surface_score(R, t, src_dense, dst_tree):
    d, _ = dst_tree.query(src_dense @ R.T + t)
    return float(np.percentile(d, 99)), float(np.median(d))


for name in transforms:
    robot = read_stl(f"{W}/duck_full/{name}.stl") * 1000.0
    official = read_stl(f"{W}/print_official/{name}.stl")
    src, dst = samples(robot, 30000, 0), samples(official, 30000, 1)
    src_dense = samples(robot, 60000, 5)
    dst_tree = cKDTree(samples(official, 600000, 6))
    tree = cKDTree(dst)
    cs, cd = src.mean(0), dst.mean(0)
    _, _, Vs = np.linalg.svd(src - cs, full_matrices=False)
    _, _, Vd = np.linalg.svd(dst - cd, full_matrices=False)
    old = surface_score(np.array(transforms[name]["R"]), np.array(transforms[name]["t"]), src_dense, dst_tree)
    best = (old[0], old[1], np.array(transforms[name]["R"]), np.array(transforms[name]["t"]))
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            P = np.zeros((3, 3))
            for i, (p, s) in enumerate(zip(perm, signs)):
                P[i, p] = s
            R = Vd.T @ P @ Vs
            if np.linalg.det(R) < 0:
                continue
            t = cd - R @ cs
            for _ in range(40):
                moved = src @ R.T + t
                dist, j = tree.query(moved)
                keep = dist < np.percentile(dist, 90)
                dR, dt = kabsch(moved[keep], dst[j[keep]])
                R, t = dR @ R, dR @ t + dt
            p99, med = surface_score(R, t, src_dense, dst_tree)
            if p99 < best[0] - 1e-6:
                best = (p99, med, R, t)
    changed = not np.allclose(best[2], np.array(transforms[name]["R"]), atol=1e-6)
    transforms[name] = {"R": best[2].tolist(), "t": best[3].tolist()}
    print(f"{name:22s} before 99%/median {old[0]:7.3f}/{old[1]:.3f} mm  after {best[0]:7.3f}/{best[1]:.3f} mm  {'CHANGED' if changed else 'same'}")
json.dump(transforms, open(path, "w"))
