"""Reshape the duck's cosmetic shells (head, body, thigh covers) into new designs.

Run: blender -b open-duck-mini.blend -P duck_reshape.py -- <out_dir> <mode> [concept ...]
mode: "check" warps and reports weight + clearance only; "test" also renders a quick front view;
"all" renders the showcase views, exports printable STLs and a web GLB with every variant.

Each group of shells (head, body, each thigh cover) sits in a free-form deformation cage: a
Bezier lattice whose control points are moved to round, dome, taper or wedge the shape. The
field is a smooth polynomial, so the 2 mm walls keep their thickness, there are no creases,
and parts that share a cage (the four body shells) keep meeting at their seams.
"""
import math
import sys
from math import comb

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]
OUT, MODE = args[0], args[1]
ONLY = set(args[2:])
scene = bpy.context.scene

prefs = bpy.context.preferences.addons["cycles"].preferences
for backend in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = backend
        prefs.get_devices()
        if any(dv.type == backend for dv in prefs.devices):
            for dv in prefs.devices:
                dv.use = dv.type == backend
            scene.cycles.device = "GPU"
            break
    except TypeError:
        continue

HEAD_SET = {"head", "head_bot_sheet", "left_antenna_holder", "right_antenna_holder"}
BODY_SET = {"body_front", "body_back", "body_middle_top", "body_middle_bottom", "battery_pack_lid"}
# Parts screwed onto the shells: they ride along with their wall instead of blocking it.
RIDERS = {"power_switch", "usb_c_charger", "sg90"}
THIGH_SET = {"left_cache", "right_cache"}
FEET = {"foot_top", "foot_side"}
HIP = {"left_roll_to_pitch", "right_roll_to_pitch"}
PLA = 1.24          # g/cm3
SHELL_FILL = 0.85   # thin shells print mostly as solid perimeters

# Control-cage edits per concept. Amounts are in millimetres at the cage, before the
# Bezier smoothing softens them a little on the actual surface.
CONCEPTS = {
    "pebble": {
        "title": "Pebble",
        "head": {"round": 3.0, "grow": 1.12},
        "body": {"round": 3.0, "grow": 1.08},
        "thigh": {"round": 5.5},
        "colours": {"head": "#efe6d6", "body": "#9db8a0", "thigh": "#7f9c84", "feet": "#e9785f", "hip": "#e9785f", "ears": "#e9785f"},
        "bill": None,
    },
    "duckling": {
        "title": "Duckling",
        "head": {"round": 2.2, "dome": 24.0, "grow": 1.14},
        "body": {"round": 2.8, "chub": 12.0, "grow": 1.10},
        "thigh": {"round": 4.5},
        "colours": {"head": "#f6dc5a", "body": "#f6dc5a", "thigh": "#f2c94c", "feet": "#f08a24", "hip": "#f08a24", "ears": "#f08a24"},
        "bill": "#f08a24",
    },
    "visor": {
        "title": "Visor",
        "head": {"round": 6.0, "wedge_rear": 14.0, "brow": 14.0, "rear_flare": 11.0, "grow": 1.03},
        "body": {"round": 6.0, "chest_flare": 14.0, "grow": 1.04},
        "thigh": {"round": 9.0, "taper": 5.0},
        "colours": {"head": "#2e3337", "body": "#2e3337", "thigh": "#3d444a", "feet": "#ff7a1a", "hip": "#ff7a1a", "ears": "#ff7a1a"},
        "bill": None,
    },
}


def hex_lin(h):
    rgb = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)


def material(name, hexcol, rough=0.5):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*hex_lin(hexcol), 1)
    bsdf.inputs["Roughness"].default_value = rough
    return mat


objects = [ob for ob in scene.objects if ob.type == "MESH" and not ob.is_shadow_catcher]
by_mesh = {}
for ob in objects:
    by_mesh.setdefault(ob.data.name, []).append(ob)
originals_mat = {me.name: me.materials[0] for me in bpy.data.meshes if me.materials}


def world_verts(ob, me=None):
    me = me or ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(ob.matrix_world)
    return co @ M[:3, :3].T + M[:3, 3]


def set_world_verts(ob, me, P):
    Minv = np.array(ob.matrix_world.inverted())
    me.vertices.foreach_set("co", (P @ Minv[:3, :3].T + Minv[:3, 3]).ravel())
    me.update()


def bounds(obs):
    P = np.vstack([world_verts(o) for o in obs])
    return P.min(0), P.max(0)


def densified_copy(me, max_edge=0.004):
    """Copy a mesh and split long edges until it can bend smoothly (surface unchanged)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    for _ in range(9):
        long_edges = [e for e in bm.edges if e.calc_length() > max_edge]
        if not long_edges:
            break
        bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1, use_grid_fill=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    new = bpy.data.meshes.new(me.name + "_dense")
    bm.to_mesh(new)
    bm.free()
    return new


def bernstein(n, x):
    i = np.arange(n + 1)
    C = np.array([comb(n, k) for k in i], float)
    x = x[:, None]
    return C * x ** i * (1 - x) ** (n - i)


class Cage:
    """Bezier free-form deformation cage around a box. Untouched control points = identity."""

    def __init__(self, lo, hi, deg, pad=0.012):
        span = hi - lo
        self.lo, self.hi = lo - span * pad - 1e-4, hi + span * pad + 1e-4
        self.deg = deg
        L, M, N = deg
        unit = np.stack(np.meshgrid(np.arange(L + 1) / L, np.arange(M + 1) / M, np.arange(N + 1) / N, indexing="ij"), -1)
        self.Q = self.lo + unit * (self.hi - self.lo)
        self.c = (self.lo + self.hi) / 2
        self.h = (self.hi - self.lo) / 2
        self.q = (self.Q - self.c) / self.h  # control points in [-1, 1]

    def apply(self, P, q_new):
        Qn = self.c + q_new * self.h
        L, M, N = self.deg
        s = np.clip((P - self.lo) / (self.hi - self.lo), 0, 1)
        out = np.empty_like(P)
        for a in range(0, len(P), 20000):
            b = a + 20000
            out[a:b] = np.einsum("ni,nj,nk,ijkc->nc", bernstein(L, s[a:b, 0]), bernstein(M, s[a:b, 1]),
                                 bernstein(N, s[a:b, 2]), Qn, optimize=True)
        return out


def rounded(q, p, axes, z_one_sided=False, K=1.0):
    """Move cage points onto a superellipse of exponent p (2 = ellipse, large = box), scaled by K.
    K > 1 inflates the faces outward so the rounded shell still clears what's inside it."""
    a = np.abs(q[..., axes])
    if z_one_sided and 2 in axes:
        a[..., axes.index(2)] = np.maximum(q[..., 2], 0)  # keep the bottom rim's edges square
    m = a.max(-1)
    d = a / np.maximum(m, 1e-9)[..., None]
    s = np.where(m > 1e-6, 1.0 / np.power(np.maximum(np.power(d, p).sum(-1), 1e-12), 1.0 / p), 1.0)
    f = 1 + (K * s - 1) * m ** 2
    out = q.copy()
    for ax in axes:
        if z_one_sided and ax == 2:
            out[..., 2] = np.where(q[..., 2] > 0, q[..., 2] * f, q[..., 2])
        else:
            out[..., ax] = q[..., ax] * f
    return out


def head_cage_edit(cage, spec, K=1.0):
    q = rounded(cage.q, spec["round"], [0, 1, 2], z_one_sided=True, K=K)
    hx, hy, hz = cage.h * 1000
    x, y, z = q[..., 0], q[..., 1], q[..., 2]
    top = ((cage.q[..., 2] + 1) / 2)
    front = ((cage.q[..., 0] + 1) / 2)
    r = np.clip(np.maximum(np.abs(cage.q[..., 0]), np.abs(cage.q[..., 1])), 0, 1)
    if spec.get("dome"):
        z = z + spec["dome"] / hz * (1 - r ** 2) * top ** 2
    if spec.get("wedge_rear"):  # raise the back of the top so it slopes down toward the eyes
        z = z + spec["wedge_rear"] / hz * (1 - front) ** 1.5 * top ** 1.5
    if spec.get("brow"):
        x = x + spec["brow"] / hx * front ** 4 * np.exp(-((cage.q[..., 2] - 0.35) / 0.45) ** 2) * (1 - np.abs(cage.q[..., 1]) ** 4)
    if spec.get("rear_flare"):  # widen the back so the front reads narrower
        y = y + spec["rear_flare"] / hy * cage.q[..., 1] * (1 - front) ** 2
    # The bottom plate and the head's rim must stay flat to print and to sit on each other:
    # no vertical movement in the two lowest cage layers (they carry nearly all of the plate's weight).
    z = np.where(cage.q[..., 2] < -0.3, cage.q[..., 2], z)
    return np.stack((x, y, z), -1)


def body_cage_edit(cage, spec, K=1.0):
    q = rounded(cage.q, spec["round"], [0, 1, 2], K=K)
    hx, hy, hz = cage.h * 1000
    y = q[..., 1]
    if spec.get("chub"):
        y = y + spec["chub"] / hy * cage.q[..., 1] * (1 - cage.q[..., 2] ** 2)
    if spec.get("chest_flare"):  # wider at the top: a V-shaped chest
        y = y + spec["chest_flare"] / hy * cage.q[..., 1] * ((1 + cage.q[..., 2]) / 2) ** 1.5
    q[..., 1] = y
    return q


def thigh_cage_edit(cage, spec):
    q = rounded(cage.q, spec["round"], [0, 2])
    if spec.get("taper"):
        hx = cage.h[0] * 1000
        q[..., 0] = q[..., 0] - spec["taper"] / hx * cage.q[..., 0] * ((1 - cage.q[..., 2]) / 2)
    return q


def volume_cm3(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    v = bm.calc_volume() * 1e6
    bm.free()
    return v


def cage_weights(cage, P):
    L, M, N = cage.deg
    s = np.clip((P - cage.lo) / (cage.hi - cage.lo), 0, 1)
    return np.einsum("ni,nj,nk->nijk", bernstein(L, s[:, 0]), bernstein(M, s[:, 1]), bernstein(N, s[:, 2]))


def wall_samples(shell_obs, inner_obs, cage):
    """For every part vertex near the shells (inside or outside them): the nearest wall point,
    the direction from that wall to the part, and the gap. Parts don't move; walls do."""
    verts, polys, off = [], [], 0
    for ob in shell_obs:
        P = world_verts(ob)
        verts.extend(map(tuple, P))
        polys.extend([[i + off for i in p.vertices] for p in ob.data.polygons])
        off += len(P)
    tree = BVHTree.FromPolygons(verts, polys)
    lo, hi = cage.lo + 0.003, cage.hi - 0.003
    pts, owner = [], []
    for ob in inner_obs:
        P = world_verts(ob)[::3]
        P = P[np.all((P > lo) & (P < hi), axis=1)]
        if len(P):
            pts.append(P)
            owner.extend([ob.name] * len(P))
    if not pts:
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0), []
    P = np.vstack(pts)
    walls, gaps, dirs, who = [], [], [], []
    for x, name in zip(P, owner):
        loc, n, _, dist = tree.find_nearest(Vector(x))
        if loc is None or dist > 0.03:
            continue
        v = Vector(x) - loc
        if v.dot(n) <= 0:
            continue  # already inside a wall in the original: not ours to judge
        walls.append(tuple(loc))
        gaps.append(dist)
        dirs.append(tuple(v.normalized()))
        who.append(name)
    if not walls:
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0), []
    return np.array(walls), np.array(dirs), np.array(gaps), who


def relax(cage, q_target, samples, margin=0.0003, iters=240):
    """Get as close to q_target as possible without any wall moving into a part: shrink the
    edit only at the cage points that drive colliding walls, and repeat."""
    W, dirs, gaps = samples[:3]
    alpha = np.ones(cage.q.shape[:3])
    q = q_target
    if not len(W):
        return q, alpha, 0, 0.0
    Bw = cage_weights(cage, W)
    for _ in range(iters):
        q = cage.q + alpha[..., None] * (q_target - cage.q)
        closing = ((cage.apply(W, q) - W) * dirs).sum(1) - gaps
        hit = closing > margin
        if not hit.any():
            break
        infl = np.tensordot(closing[hit], Bw[hit], axes=(0, 0))
        alpha = np.clip(alpha - 0.45 * (infl / infl.max()) ** 2, 0, 1)
    return q, alpha, int(hit.sum()), float(max(closing.max(), 0.0))


if MODE == "official_head":
    # The print repo's head.stl is a newer revision than the robot model's head. Put the official
    # file where the old head sits (args: official STL in mm, transforms JSON from align_to_print.py)
    # and reshape that instead, so the printed head keeps the newer features.
    import json
    import struct
    off_path = next(a for a in args[2:] if a.endswith(".stl"))
    frames_path = next(a for a in args[2:] if a.endswith(".json") and "mujoco" in a)
    tf_path = next(a for a in args[2:] if a.endswith(".json") and "mujoco" not in a)
    data = open(off_path, "rb").read()
    n = struct.unpack("<I", data[80:84])[0]
    rec = np.frombuffer(data[84:], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]), count=n)
    tris = rec["v"].reshape(-1, 3).astype(float)
    tf = json.load(open(tf_path))["head"]
    R, t = np.array(tf["R"]), np.array(tf["t"])
    fr = json.load(open(frames_path))["head"]
    Rq, pos = np.array(fr["R"]), np.array(fr["pos"])
    stl_frame = (tris - t) @ R / 1000.0      # official mm -> original head STL frame, metres
    part = (stl_frame - pos) @ Rq            # -> MuJoCo's centred mesh frame used in the .blend
    uniq, inv = np.unique(np.round(part, 7), axis=0, return_inverse=True)
    me = bpy.data.meshes.new("head_official")
    me.from_pydata(uniq.tolist(), [], inv.reshape(-1, 3).tolist())
    me.validate()
    me.materials.append(originals_mat["head"])
    old = by_mesh["head"][0]
    off_ob = bpy.data.objects.new("head_official", me)
    off_ob.matrix_world = old.matrix_world.copy()
    scene.collection.objects.link(off_ob)
    old.hide_render = True
    objects = [o for o in objects if o is not old] + [off_ob]
    by_mesh["head"] = [off_ob]
    originals_mat["head_official"] = originals_mat["head"]
    HEAD_SET = HEAD_SET | {"head_official"}
    print(f"OFFICIAL head placed: {len(uniq)} vertices, {n} triangles")

# Cages from the original shells
head_obs = [o for n in HEAD_SET for o in by_mesh.get(n, [])]
body_obs = [o for n in BODY_SET for o in by_mesh[n]]
head_cage = Cage(*bounds(head_obs), (7, 7, 5))
body_cage = Cage(*bounds(body_obs), (8, 5, 5))
thigh_cages = {o.name: Cage(*bounds([o]), (4, 1, 4)) for n in THIGH_SET for o in by_mesh[n]}

dense = {ob.name: densified_copy(ob.data) for ob in head_obs + body_obs + [o for n in THIGH_SET for o in by_mesh[n]]}
group_names = HEAD_SET | BODY_SET | THIGH_SET | {"antenna"}
riders = [o for o in objects if o.data.name in RIDERS]
inner = [o for o in objects if o.data.name not in group_names | RIDERS]

samples_cache = {}


def fit(edit, cage, spec, shells, label):
    """The target shape, eased back wherever a wall would run into a part (inside or outside)."""
    key = id(cage)
    if key not in samples_cache:
        samples_cache[key] = wall_samples(shells, inner, cage)
    q_t = edit(cage, spec, spec.get("grow", 1.0))
    W, dirs, gaps, who = samples_cache[key]
    if len(W):
        closing = ((cage.apply(W, q_t) - W) * dirs).sum(1) - gaps
        from collections import Counter
        offenders = Counter(w for w, c in zip(who, closing) if c > 0.0003)
        worst_by = {}
        for w, c in zip(who, closing):
            worst_by[w] = max(worst_by.get(w, 0), c)
        print(f"BLOCKERS {label}: " + ", ".join(f"{n} {k} pts/{worst_by[n] * 1000:.0f}mm" for n, k in offenders.most_common(12)))
    q, alpha, hits, worst = relax(cage, q_t, samples_cache[key])
    print(f"FIT {label}: {len(samples_cache[key][0])} part points checked, edit kept {alpha.mean() * 100:.0f}% on average "
          f"(min {alpha.min() * 100:.0f}%), {hits} still touching (worst {worst * 1000:.1f} mm)")
    return q, alpha


head_shells = [o for o in head_obs if o.data.name in ("head", "head_bot_sheet", "head_official")]
variants, antenna_moves = {}, {}
for key, spec in CONCEPTS.items():
    if ONLY and key not in ONLY:
        continue
    q_head, _ = fit(head_cage_edit, head_cage, spec["head"], head_shells, f"{key} head")
    q_body, _ = fit(body_cage_edit, body_cage, spec["body"], body_obs, f"{key} body")
    made, report = [], []
    for group, obs in (("head", head_obs), ("body", body_obs), ("thigh", [o for n in THIGH_SET for o in by_mesh[n]])):
        for ob in obs:
            me = dense[ob.name].copy()
            me.name = f"rd-{key}-{ob.name}"
            P0 = world_verts(ob, me)
            if group == "head":
                P1 = head_cage.apply(P0, q_head)
            elif group == "body":
                P1 = body_cage.apply(P0, q_body)
            else:
                cage = thigh_cages[ob.name]
                P1 = cage.apply(P0, thigh_cage_edit(cage, spec["thigh"]))
            new = bpy.data.objects.new(f"rd-{key}-{ob.name}", me)
            new.matrix_world = ob.matrix_world.copy()
            scene.collection.objects.link(new)
            set_world_verts(new, me, P1)
            me.shade_smooth()
            me.set_sharp_from_angle(angle=math.radians(40))
            me.materials.clear()
            if ob.data.name == "head_bot_sheet":
                me.materials.append(originals_mat["head_bot_sheet"])
            else:
                col = spec["colours"]["ears" if "antenna_holder" in ob.data.name else group]
                me.materials.append(material(f"rd-{key}-{group}-{ob.data.name}", col))
            new.hide_render = True
            made.append((ob, new))
            report.append((group, volume_cm3(me) - volume_cm3(ob.data), (P1 - P0)))
            if "antenna_holder" in ob.data.name:
                antenna_moves[(key, ob.name)] = (P0.mean(0), (P1 - P0).mean(0))
    # parts screwed to a shell move with the cage at their centre
    for rider in riders:
        centre = world_verts(rider).mean(0)[None, :]
        cage, qn = (head_cage, q_head) if np.all((centre > head_cage.lo) & (centre < head_cage.hi)) else (body_cage, q_body)
        shift = (cage.apply(centre, qn) - centre)[0]
        new = bpy.data.objects.new(f"rd-{key}-{rider.name}", rider.data)
        new.matrix_world = Matrix.Translation(Vector(shift)) @ rider.matrix_world
        scene.collection.objects.link(new)
        new.hide_render = True
        made.append((rider, new))
    # antennas: move each wire with the holder it sits in
    for ant in by_mesh.get("antenna", []):
        base = np.array(ant.matrix_world.translation)
        best = min((k for k in antenna_moves if k[0] == key), key=lambda k: np.linalg.norm(antenna_moves[k][0] - base))
        me = ant.data
        new = bpy.data.objects.new(f"rd-{key}-{ant.name}", me)
        new.matrix_world = Matrix.Translation(Vector(antenna_moves[best][1])) @ ant.matrix_world
        scene.collection.objects.link(new)
        new.hide_render = True
        made.append((ant, new))
    variants[key] = made
    for group in ("head", "body", "thigh"):
        rows = [r for r in report if r[0] == group]
        dv = sum(r[1] for r in rows)
        moves = np.concatenate([np.linalg.norm(r[2], axis=1) for r in rows]) * 1000
        print(f"WEIGHT {key} {group}: volume {dv:+.1f} cm3, about {dv * PLA * SHELL_FILL:+.0f} g; surface moved median {np.median(moves):.1f} mm, max {moves.max():.1f} mm")

if MODE == "check":
    sys.exit(0)

if MODE == "official_head":
    import os
    for key, made in variants.items():
        os.makedirs(f"{OUT}/stl_official/{key}", exist_ok=True)
        for orig, new in made:
            name = "head" if orig.data.name == "head_official" else orig.data.name
            if name not in HEAD_SET:
                continue
            tmp = bpy.data.objects.new("stl_tmp", new.data)
            scene.collection.objects.link(tmp)
            bpy.ops.object.select_all(action="DESELECT")
            tmp.select_set(True)
            bpy.context.view_layer.objects.active = tmp
            bpy.ops.wm.stl_export(filepath=f"{OUT}/stl_official/{key}/{name}.stl", export_selected_objects=True, global_scale=1000.0)
            bpy.data.objects.remove(tmp)
            print("STL official-head group", key, name)
    sys.exit(0)


# --- the bill for concepts that want one, placed on the reshaped head ---
def half_ellipsoid(name, ax, ay, az, up_tilt_deg=0.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    bmesh.ops.scale(bm, vec=(ax, ay, az), verts=bm.verts)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(-up_tilt_deg), 3, "Y"))
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(1, 0, 0), clear_inner=True)
    bmesh.ops.contextual_create(bm, geom=[e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


bills = {}
for key, made in variants.items():
    colour = CONCEPTS[key]["bill"]
    if not colour:
        continue
    head_new = next(n for o, n in made if o.data.name == "head")
    P = world_verts(head_new)
    lo, hi = P.min(0), P.max(0)
    origin = Vector((hi[0] + 0.2, (lo[1] + hi[1]) / 2, lo[2] + 0.24 * (hi[2] - lo[2])))
    inv = head_new.matrix_world.inverted()
    ok, loc, normal, _ = head_new.ray_cast(inv @ origin, (inv.to_3x3() @ Vector((-1, 0, 0))).normalized())
    if not ok:
        continue
    wloc = head_new.matrix_world @ loc
    wn = (head_new.matrix_world.to_3x3().inverted().transposed() @ normal).normalized()
    me = half_ellipsoid(f"rd-{key}-bill", 0.050, 0.032, 0.008, up_tilt_deg=8)
    me.materials.append(material(f"rd-{key}-bill", colour))
    ob = bpy.data.objects.new(f"rd-{key}-bill", me)
    x = wn
    y = Vector((0, 0, 1)).cross(x).normalized()
    z = x.cross(y).normalized()
    ob.matrix_world = Matrix.Translation(wloc - x * 0.0005) @ Matrix((x, y, z)).transposed().to_4x4()
    scene.collection.objects.link(ob)
    ob.hide_render = True
    bills[key] = ob

# --- renders ---
rlo, rhi = bounds(objects)
center = Vector((rlo + rhi) / 2)
cam = scene.camera
dist = (cam.location - center).length


def aim(az_deg, el_deg):
    az, el = math.radians(az_deg), math.radians(el_deg)
    cam.location = center + Vector((dist * math.cos(el) * math.cos(az), dist * math.cos(el) * math.sin(az), dist * math.sin(el)))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()


def show(key):
    for name, mat in originals_mat.items():
        if name in bpy.data.meshes:
            bpy.data.meshes[name].materials[0] = mat
    for k, made in variants.items():
        for orig, new in made:
            new.hide_render = k != key
            orig.hide_render = False
    for k, ob in bills.items():
        ob.hide_render = k != key
    for orig, new in variants[key]:
        orig.hide_render = True
    cols = CONCEPTS[key]["colours"]
    for names, group in ((FEET, "feet"), (HIP, "hip")):
        mat = material(f"rd-{key}-{group}", cols[group])
        for n in names:
            if n in bpy.data.meshes:
                bpy.data.meshes[n].materials[0] = mat


VIEWS = {"front": (-35, 14, 1400), "side": (-90, 6, 900), "back": (150, 18, 900), "gallery": (-58, 10, 1000)}
if MODE == "test":
    VIEWS = {"front": (-35, 14, 700), "side": (-90, 6, 600)}
scene.cycles.samples = 110 if MODE == "all" else 32
if MODE in ("test", "all"):
    for key in variants:
        show(key)
        for view, (azd, eld, res) in VIEWS.items():
            aim(azd, eld)
            scene.render.resolution_x = scene.render.resolution_y = res
            scene.render.filepath = f"{OUT}/shape-{key}-{view}.png"
            bpy.ops.render.render(write_still=True)
        print("RENDERED", key)

if MODE not in ("all", "export"):
    sys.exit(0)

# --- printable STLs: each reshaped shell in its own part frame, millimetres ---
import os
for key, made in variants.items():
    os.makedirs(f"{OUT}/stl/{key}", exist_ok=True)
    for orig, new in made:
        if orig.data.name not in HEAD_SET | BODY_SET | THIGH_SET:
            continue  # wires and screwed-on parts are unchanged off-the-shelf parts
        tmp = bpy.data.objects.new("stl_tmp", new.data)
        scene.collection.objects.link(tmp)
        bpy.ops.object.select_all(action="DESELECT")
        tmp.select_set(True)
        bpy.context.view_layer.objects.active = tmp
        bpy.ops.wm.stl_export(filepath=f"{OUT}/stl/{key}/{orig.data.name}.stl", export_selected_objects=True, global_scale=1000.0)
        bpy.data.objects.remove(tmp)
    print("STL", key)


# --- web GLB: only the variant parts (rd-<concept>-<original object>); the page already has the rest ---
def slim(ob, ratio):
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.ratio = ratio
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="dec")
    ob.data.set_sharp_from_angle(angle=math.radians(40))


for made in variants.values():
    for orig, new in made:
        if orig.data.name in HEAD_SET | BODY_SET | THIGH_SET and len(new.data.polygons) > 4000:
            slim(new, 0.2)
        if orig.data.name in RIDERS and len(new.data.polygons) > 4000:
            new.data = new.data.copy()  # riders share data with the originals: slim a private copy
            slim(new, 0.06)
export = [n for made in variants.values() for o, n in made] + list(bills.values())
bpy.ops.object.select_all(action="DESELECT")
for ob in export:
    ob.hide_set(False)
    ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=f"{OUT}/duck-shapes.glb", export_format="GLB", use_selection=True,
                          export_yup=True, export_apply=True, export_cameras=False, export_lights=False)
print("EXPORTED GLB", len(export), "objects")
