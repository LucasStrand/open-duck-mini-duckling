"""Move reshaped shells into the official print files' orientation.

For each shell: the robot-model copy (metres) and the official print STL (mm) are the same part in
different frames. Find the rigid transform between them (PCA start + ICP), check the fit, then apply
that transform to the reshaped version and write it out as a binary STL in mm.
usage: align_to_print.py <robot_dir> <official_dir> <reshaped_dir> <out_dir> name [name ...]
"""
import os, struct, sys
import numpy as np
from scipy.spatial import cKDTree


def read_stl(path):
    data = open(path, "rb").read()
    n = struct.unpack("<I", data[80:84])[0]
    if len(data) == 84 + 50 * n:
        rec = np.frombuffer(data[84:], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]), count=n)
        return rec["v"].reshape(-1, 3, 3).astype(float)
    tris, cur = [], []
    for line in data.decode("ascii", "ignore").splitlines():
        p = line.split()
        if p and p[0] == "vertex":
            cur.append([float(x) for x in p[1:4]])
            if len(cur) == 3:
                tris.append(cur); cur = []
    return np.array(tris, float)


def write_stl(path, tris):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(tris), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    rec["n"], rec["v"] = n, tris.reshape(-1, 9)
    with open(path, "wb") as f:
        f.write(b"Open Duck Mini - Duckling shell, aligned to official print orientation".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        f.write(rec.tobytes())


def volume(t):
    return np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6


def samples(t, k=30000, seed=0):
    rng = np.random.default_rng(seed)
    area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) / 2
    idx = rng.choice(len(t), size=k, p=area / area.sum())
    u, v = rng.random(k), rng.random(k)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    a, b, c = t[idx, 0], t[idx, 1], t[idx, 2]
    return a + (b - a) * u[:, None] + (c - a) * v[:, None]


def kabsch(A, B):
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return R, cb - R @ ca


def align(src, dst, src_verts=None, dst_verts=None):
    """Try all 24 proper rotations of the principal frames, refine each with ICP, and keep the one
    whose original vertices land closest to the official vertices (near-symmetric parts need this)."""
    import itertools
    tree = cKDTree(dst)
    vtree = cKDTree(dst_verts) if dst_verts is not None else tree
    sv = src_verts if src_verts is not None else src
    cs, cd = src.mean(0), dst.mean(0)
    _, _, Vs = np.linalg.svd(src - cs, full_matrices=False)
    _, _, Vd = np.linalg.svd(dst - cd, full_matrices=False)
    best = None
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            P = np.zeros((3, 3))
            for i, (p, s) in enumerate(zip(perm, signs)):
                P[i, p] = s
            R = Vd.T @ P @ Vs
            if np.linalg.det(R) < 0:
                continue  # a reflection would print the part mirrored
            t = cd - R @ cs
            for _ in range(30):
                moved = src @ R.T + t
                dist, j = tree.query(moved)
                keep = dist < np.percentile(dist, 95)
                dR, dt = kabsch(moved[keep], dst[j[keep]])
                R, t = dR @ R, dR @ t + dt
            d, _ = vtree.query(sv @ R.T + t)
            score = float(np.median(d))
            if best is None or score < best[0]:
                best = (score, R, t, float(np.percentile(d, 99)))
    return best


def bed_contact(t):
    """Area (mm2) of downward faces lying on the lowest plane: how well the part sits on the bed."""
    z0 = t[..., 2].min()
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    area = np.linalg.norm(n, axis=1) / 2
    down = (n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)) < -0.98
    on_bed = np.all(t[..., 2] < z0 + 0.2, axis=1)
    return float(area[down & on_bed].sum())


if __name__ == "__main__":
    import json
    robot_dir, official_dir, reshaped_dir, out_dir, *names = sys.argv[1:]
    os.makedirs(out_dir, exist_ok=True)
    transforms = {}
    for name in names:
        robot = read_stl(f"{robot_dir}/{name}.stl") * 1000.0
        official = read_stl(f"{official_dir}/{name}.stl")
        reshaped = read_stl(f"{reshaped_dir}/{name}.stl")
        score, R, t, p99 = align(samples(robot), samples(official, seed=1), robot.reshape(-1, 3), official.reshape(-1, 3))
        transforms[name] = {"R": R.tolist(), "t": t.tolist()}
        out = reshaped @ R.T + t
        out[..., 2] += official[..., 2].min() - out[..., 2].min()  # rest on the same bed plane
        write_stl(f"{out_dir}/{name}.stl", out)
        vo, vr, vn = volume(official) / 1000, volume(robot) / 1000, volume(out) / 1000
        print(f"{name:22s} official {vo:6.1f} cm3 | robot copy {(vr / vo - 1) * 100:+5.1f}% | vertex fit median {score:.3f} mm, 99% {p99:6.3f} mm | "
              f"duckling {vn:6.1f} cm3 | bed contact official {bed_contact(official):6.0f} mm2, duckling {bed_contact(out):6.0f} mm2")
    json.dump(transforms, open(f"{out_dir}/../print_transforms.json", "w"))
