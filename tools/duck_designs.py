"""Design variants for the assembled Open Duck Mini: colour schemes plus a printable bill and tail.

Run: blender -b open-duck-mini.blend -P duck_designs.py -- <out_dir> <mode> [design ...]
mode: "test" renders the named designs fast; "all" renders every design and exports the add-on STLs.
"""
import math
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
OUT, MODE = args[0], args[1]
ONLY = set(args[2:])
scene = bpy.context.scene

# The GPU choice is a user preference, not saved in the .blend, so set it again here.
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

# Which printed parts each colour group covers (by mesh name).
GROUPS = {
    "head": {"head"},
    "body": {"body_front", "body_back", "body_middle_top", "body_middle_bottom"},
    "thigh": {"left_cache", "right_cache"},
    "feet": {"foot_top", "foot_side"},
    "ears": {"left_antenna_holder", "right_antenna_holder"},
    "hip": {"left_roll_to_pitch", "right_roll_to_pitch"},
}

# name: (title, colours per group in sRGB, add-ons, add-on colour)
DESIGNS = {
    "classic": ("Classic", {}, [], None),
    "mallard": ("Mallard", {"head": (0.06, 0.33, 0.21), "body": (0.66, 0.64, 0.60), "thigh": (0.42, 0.24, 0.14),
                            "feet": (0.96, 0.50, 0.10), "ears": (0.90, 0.90, 0.88), "hip": (0.96, 0.50, 0.10)},
                ["bill", "tail"], {"bill": (0.93, 0.78, 0.18), "tail": (0.10, 0.10, 0.11)}),
    "rubber": ("Rubber Duck", {"head": (0.98, 0.76, 0.10), "body": (0.98, 0.76, 0.10), "thigh": (0.98, 0.76, 0.10),
                               "feet": (0.97, 0.43, 0.06), "ears": (0.97, 0.43, 0.06), "hip": (0.97, 0.43, 0.06)},
               ["bill"], (0.97, 0.43, 0.06)),
    "midnight": ("Midnight", {"head": (0.11, 0.12, 0.13), "body": (0.11, 0.12, 0.13), "thigh": (0.16, 0.17, 0.19),
                              "feet": (0.10, 0.74, 0.78), "ears": (0.10, 0.74, 0.78), "hip": (0.10, 0.74, 0.78)},
                 [], None),
    "arctic": ("Arctic", {"head": (0.90, 0.94, 0.97), "body": (0.90, 0.94, 0.97), "thigh": (0.56, 0.71, 0.86),
                          "feet": (0.13, 0.22, 0.42), "ears": (0.13, 0.22, 0.42), "hip": (0.13, 0.22, 0.42)},
               [], None),
    "toybox": ("Toy Box", {"head": (0.84, 0.13, 0.11), "body": (0.10, 0.30, 0.74), "thigh": (0.10, 0.30, 0.74),
                           "feet": (0.99, 0.78, 0.08), "ears": (0.99, 0.78, 0.08), "hip": (0.99, 0.78, 0.08)},
               ["bill"], (0.99, 0.78, 0.08)),
}

PLA_DENSITY = 1.24          # g/cm3
PRINT_FILL = 0.45           # walls + 15% infill, rough share of a solid part's mass


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def make_material(name, rgb, rough=0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*(srgb_to_linear(c) for c in rgb), 1)
    bsdf.inputs["Roughness"].default_value = rough
    return mat


meshes_by_name = {me.name: me for me in bpy.data.meshes}
original = {name: me.materials[0] for name, me in meshes_by_name.items() if me.materials}
objects = [ob for ob in scene.objects if ob.type == "MESH" and not ob.is_shadow_catcher]


def world_bounds(obs):
    pts = [ob.matrix_world @ Vector(c) for ob in obs for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def half_ellipsoid(name, ax, ay, az, up_tilt_deg=0.0, segments=48, rings=24):
    """Ellipsoid with semi-axes ax (forward), ay, az, its tip tilted up by up_tilt_deg, then cut flat
    on the x=0 plane. The flat face (facing -X) is the glue face, so it stays flush with the surface."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0)
    bmesh.ops.scale(bm, vec=(ax, ay, az), verts=bm.verts)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(-up_tilt_deg), 3, "Y"))
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0), plane_no=(1, 0, 0), clear_inner=True)
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    bmesh.ops.contextual_create(bm, geom=edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return me


def surface_hit(target_names, origin, direction):
    """First hit on any object whose mesh is in target_names, in world space."""
    best = None
    for ob in objects:
        if ob.data.name not in target_names:
            continue
        inv = ob.matrix_world.inverted()
        o = inv @ origin
        d = (inv.to_3x3() @ direction).normalized()
        ok, loc, normal, _ = ob.ray_cast(o, d)
        if ok:
            wloc = ob.matrix_world @ loc
            dist = (wloc - origin).length
            if best is None or dist < best[0]:
                wn = (ob.matrix_world.to_3x3().inverted().transposed() @ normal).normalized()
                best = (dist, wloc, wn)
    return best


def place_on(me, name, loc, normal, sink=0.0005):
    """Put the flat (-X) face of me flush against a surface at loc, pointing along normal."""
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    x_axis = normal.normalized()
    y_axis = Vector((0, 0, 1)).cross(x_axis).normalized()
    z_axis = x_axis.cross(y_axis).normalized()
    rot = Matrix((x_axis, y_axis, z_axis)).transposed().to_4x4()
    ob.matrix_world = Matrix.Translation(loc - x_axis * sink) @ rot
    return ob


# Add-ons: positions come from ray casts on the actual head and body shells.
head_obs = [ob for ob in objects if ob.data.name == "head"]
hlo, hhi = world_bounds(head_obs)
blo, bhi = world_bounds([ob for ob in objects if ob.data.name in GROUPS["body"]])
print(f"HEAD x {hlo.x:.3f}..{hhi.x:.3f} y {hlo.y:.3f}..{hhi.y:.3f} z {hlo.z:.3f}..{hhi.z:.3f}")
print(f"BODY x {blo.x:.3f}..{bhi.x:.3f} z {blo.z:.3f}..{bhi.z:.3f}")

addons = {}
hy = (hlo.y + hhi.y) / 2
bill_z = hlo.z + 0.24 * (hhi.z - hlo.z)
hit = surface_hit({"head"}, Vector((hhi.x + 0.2, hy, bill_z)), Vector((-1, 0, 0)))
if hit:
    bill_me = half_ellipsoid("duck_bill", 0.050, 0.032, 0.008, up_tilt_deg=8)
    addons["bill"] = place_on(bill_me, "duck_bill", hit[1], hit[2])
by = (blo.y + bhi.y) / 2
tail_z = blo.z + 0.62 * (bhi.z - blo.z)
hit = surface_hit(GROUPS["body"], Vector((blo.x - 0.2, by, tail_z)), Vector((1, 0, 0)))
if hit:
    tail_me = half_ellipsoid("duck_tail", 0.034, 0.020, 0.010, up_tilt_deg=35)
    addons["tail"] = place_on(tail_me, "duck_tail", hit[1], hit[2])

for key, ob in addons.items():
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    vol_cm3 = bm.calc_volume() * 1e6
    bm.free()
    grams = vol_cm3 * PLA_DENSITY * PRINT_FILL
    print(f"ADDON {key}: solid {vol_cm3:.1f} cm3, about {grams:.0f} g printed")
    ob.hide_render = True

rlo, rhi = world_bounds(objects)
center = (rlo + rhi) / 2
cam = scene.camera
dist = (cam.location - center).length  # the saved camera already frames the whole duck


def aim(az_deg, el_deg):
    az, el = math.radians(az_deg), math.radians(el_deg)
    cam.location = center + Vector((dist * math.cos(el) * math.cos(az), dist * math.cos(el) * math.sin(az), dist * math.sin(el)))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()


def apply_design(key):
    title, colours, wanted, addon_rgb = DESIGNS[key]
    for name, mat in original.items():
        meshes_by_name[name].materials[0] = mat
    for group, rgb in colours.items():
        mat = make_material(f"{key}_{group}", rgb, rough=0.5)
        for name in GROUPS[group]:
            if name in meshes_by_name:
                meshes_by_name[name].materials[0] = mat
    for a, ob in addons.items():
        ob.hide_render = a not in wanted
        if a in wanted:
            rgb = addon_rgb[a] if isinstance(addon_rgb, dict) else addon_rgb
            mat = make_material(f"{key}_{a}", rgb, rough=0.5)
            ob.data.materials.clear()
            ob.data.materials.append(mat)
    return title


if MODE in ("test", "all"):
    # Gallery camera: further round to the side than the hero, so a bill and a tail both read.
    aim(-58, 10)
    scene.cycles.samples = 24 if MODE == "test" else 110
    scene.render.resolution_x = scene.render.resolution_y = 600 if MODE == "test" else 1000
    for key in DESIGNS:
        if ONLY and key not in ONLY:
            continue
        title = apply_design(key)
        scene.render.filepath = f"{OUT}/design-{key}.png"
        bpy.ops.render.render(write_still=True)
        print("RENDERED", key, title)

if MODE == "views":
    # Same three framings as the hero showcase, for every design.
    VIEWS = {"front": (-35, 14, 1400), "side": (-90, 6, 900), "back": (150, 18, 900)}
    scene.cycles.samples = 110
    for key in DESIGNS:
        if ONLY and key not in ONLY:
            continue
        apply_design(key)
        for view, (azd, eld, res) in VIEWS.items():
            aim(azd, eld)
            scene.render.resolution_x = scene.render.resolution_y = res
            scene.render.filepath = f"{OUT}/view-{key}-{view}.png"
            bpy.ops.render.render(write_still=True)
        print("RENDERED VIEWS", key)

    # Web model with the add-ons included; the page recolours parts and toggles add-ons per design.
    apply_design("classic")
    HEAVY = {"wj-wk00-0124bottomcase_45": 0.03, "wj-wk00-0122topcabinetcase_95": 0.06,
             "raspberrypizerow": 0.25, "head": 0.6, "trunk_top": 0.5, "head_pitch_to_yaw": 0.5,
             "board": 0.4, "left_knee_to_ankle_right_sheet": 0.6, "left_knee_to_ankle_left_sheet": 0.6}
    for name, ratio in HEAVY.items():
        if name not in meshes_by_name:
            continue
        full = meshes_by_name[name]
        tmp = bpy.data.objects.new("tmp_" + name, full.copy())
        scene.collection.objects.link(tmp)
        mod = tmp.modifiers.new("dec", "DECIMATE")
        mod.ratio = ratio
        bpy.context.view_layer.objects.active = tmp
        bpy.ops.object.select_all(action="DESELECT")
        tmp.select_set(True)
        bpy.ops.object.modifier_apply(modifier="dec")
        slim = tmp.data
        slim.set_sharp_from_angle(angle=math.radians(35))
        for ob in objects:
            if ob.data is full:
                ob.data = slim
        bpy.data.objects.remove(tmp)
    neutral = make_material("addon_neutral", (0.9, 0.75, 0.2))
    for ob in addons.values():
        ob.data.materials.clear()
        ob.data.materials.append(neutral)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objects + list(addons.values()):
        ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/duck.glb", export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=True, export_cameras=False, export_lights=False)
    print("EXPORTED GLB with add-ons:", ", ".join(addons))

if MODE == "all":
    # Printable STLs in millimetres, flat face down on the bed.
    for key, ob in addons.items():
        flat = bpy.data.objects.new(f"print_{key}", ob.data.copy())
        scene.collection.objects.link(flat)
        flat.matrix_world = Matrix.Rotation(math.radians(-90), 4, "Y")  # flat -X face onto the bed, part above it
        bpy.ops.object.select_all(action="DESELECT")
        flat.select_set(True)
        bpy.context.view_layer.objects.active = flat
        bpy.ops.wm.stl_export(filepath=f"{OUT}/duck-{key}.stl", export_selected_objects=True,
                              global_scale=1000.0, apply_modifiers=True)
        print("STL", f"{OUT}/duck-{key}.stl")
