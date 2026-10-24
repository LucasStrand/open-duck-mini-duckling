"""Assemble the posed Open Duck Mini v2 in Blender, render it, and export a web GLB.

Run: blender -b --factory-startup -P duck_blender.py -- <duck_posed.json> <out_dir> <mode> [front_azimuth]
mode: "test" renders four low-sample views to find the front; "final" renders the hero
images and exports duck.glb.
"""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector

args = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, MODE = args[0], args[1], args[2]
FRONT_AZIMUTH = float(args[3]) if len(args) > 3 else 0.0  # degrees, picked from the test renders

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
data = json.load(open(SRC))


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# Printed parts in the CAD are a light grey; servos and electronics keep their CAD colours.
PRINTED = (0.84, 0.83, 0.80)
materials = {}


def material_for(rgba, mesh_name):
    key = (tuple(rgba), mesh_name.startswith("foot_bottom_tpu"))
    if key in materials:
        return materials[key]
    r, g, b, a = rgba
    mat = bpy.data.materials.new(f"mat_{len(materials)}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    if min(r, g, b) > 0.85:  # printed PLA
        r, g, b = PRINTED
        rough = 0.62
    elif key[1]:  # TPU sole
        r, g, b = 0.12, 0.12, 0.12
        rough = 0.8
    else:
        rough = 0.45
    bsdf.inputs["Base Color"].default_value = (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1)
    bsdf.inputs["Roughness"].default_value = rough
    materials[key] = mat
    return mat


meshes = {}
for name, m in data["meshes"].items():
    me = bpy.data.meshes.new(name)
    me.from_pydata(m["v"], [], m["f"])
    me.validate()
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(35))
    meshes[name] = me

robot = []
for i, gm in enumerate(data["geoms"]):
    ob = bpy.data.objects.new(f"{gm['mesh']}_{i}", meshes[gm["mesh"]])
    ob.matrix_world = Matrix(gm["matrix"])
    scene.collection.objects.link(ob)
    if not ob.data.materials:
        ob.data.materials.append(material_for(gm["rgba"], gm["mesh"]))
    robot.append(ob)

# Bounds of the whole robot
pts = [ob.matrix_world @ Vector(c) for ob in robot for c in ob.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (lo + hi) / 2
size = hi - lo
print(f"BOUNDS size x={size.x:.3f} y={size.y:.3f} z={size.z:.3f} m")

# Ground: shadow catcher so the PNG has a transparent background with a soft shadow
bpy.ops.mesh.primitive_plane_add(size=4, location=(center.x, center.y, 0))
ground = bpy.context.active_object
ground.is_shadow_catcher = True

az = math.radians(FRONT_AZIMUTH)


def around(azimuth_deg, dist, height):
    a = az + math.radians(azimuth_deg)
    return (center.x + dist * math.cos(a), center.y + dist * math.sin(a), height)


def area(name, loc, energy, size_, color=(1, 1, 1), shadow=True):
    light = bpy.data.lights.new(name, "AREA")
    light.energy = energy
    light.size = size_
    light.color = color
    light.use_shadow = shadow
    ob = bpy.data.objects.new(name, light)
    ob.location = loc
    scene.collection.objects.link(ob)
    ob.rotation_euler = (center - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


area("key", around(-40, 0.7, 1.5), 85, 1.0, (1.0, 0.97, 0.92))
area("fill", around(60, 1.2, 0.6), 25, 1.4, (0.9, 0.95, 1.0), shadow=False)
area("rim", around(170, 0.8, 1.2), 60, 0.6, shadow=False)

world = bpy.data.worlds.new("world")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.8, 0.82, 0.84, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 70
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def aim(azimuth_deg, elevation_deg, dist):
    a = az + math.radians(azimuth_deg)
    e = math.radians(elevation_deg)
    cam.location = (center.x + dist * math.cos(a) * math.cos(e),
                    center.y + dist * math.sin(a) * math.cos(e),
                    center.z + dist * math.sin(e))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()


scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for backend in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = backend
        prefs.get_devices()
        if any(dv.type == backend for dv in prefs.devices):
            for dv in prefs.devices:
                dv.use = dv.type == backend
            scene.cycles.device = "GPU"
            print("CYCLES DEVICE", backend)
            break
    except TypeError:
        continue
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
scene.view_settings.exposure = -0.75
scene.cycles.use_denoising = True

dist = size.z * 3.4
if MODE == "blend":
    scene.cycles.samples = 160
    scene.render.resolution_x, scene.render.resolution_y = 1400, 1400
    aim(-35, 14, size.z * 2.5)
    bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/open-duck-mini.blend", compress=True)
    sys.exit(0)
if MODE == "test":
    scene.cycles.samples = 16
    scene.render.resolution_x, scene.render.resolution_y = 480, 480
    for deg in (0, 90, 180, 270):
        aim(deg, 12, dist)
        scene.render.filepath = f"{OUT}/test_{deg:03d}.png"
        bpy.ops.render.render(write_still=True)
    sys.exit(0)

scene.cycles.samples = 160
dist = size.z * 2.5
for name, (azd, el, w, h) in {
    "duck-hero": (-35, 14, 1400, 1400),
    "duck-side": (-90, 6, 900, 900),
    "duck-back": (150, 18, 900, 900),
}.items():
    scene.render.resolution_x, scene.render.resolution_y = w, h
    aim(azd, el, dist)
    scene.render.filepath = f"{OUT}/{name}.png"
    bpy.ops.render.render(write_still=True)

# Web export: slim the heaviest meshes (servo cases are mostly hidden lettering), share mesh data.
HEAVY = {"wj-wk00-0124bottomcase_45": 0.03, "wj-wk00-0122topcabinetcase_95": 0.06,
         "raspberrypizerow": 0.25, "head": 0.6, "trunk_top": 0.5, "head_pitch_to_yaw": 0.5,
         "board": 0.4, "left_knee_to_ankle_right_sheet": 0.6, "left_knee_to_ankle_left_sheet": 0.6}
for name, ratio in HEAVY.items():
    if name not in meshes:
        continue
    tmp = bpy.data.objects.new("tmp_" + name, meshes[name].copy())
    scene.collection.objects.link(tmp)
    mod = tmp.modifiers.new("dec", "DECIMATE")
    mod.ratio = ratio
    bpy.context.view_layer.objects.active = tmp
    bpy.ops.object.select_all(action="DESELECT")
    tmp.select_set(True)
    bpy.ops.object.modifier_apply(modifier="dec")
    slim = tmp.data
    slim.set_sharp_from_angle(angle=math.radians(35))
    for ob in robot:
        if ob.data is meshes[name]:
            ob.data = slim
    bpy.data.objects.remove(tmp)

bpy.ops.object.select_all(action="DESELECT")
for ob in robot:
    ob.select_set(True)
print(f"WEB TRIS {sum(len(ob.data.polygons) for ob in robot)}")
bpy.ops.export_scene.gltf(filepath=f"{OUT}/duck.glb", export_format="GLB", use_selection=True,
                          export_yup=True, export_apply=True, export_cameras=False, export_lights=False)
print("EXPORTED", f"{OUT}/duck.glb")
