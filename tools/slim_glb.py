"""Slim every mesh in a GLB to at most MAX_TRIS triangles, keeping object names, then re-export."""
import math, sys
import bpy
src, dst, max_tris = sys.argv[sys.argv.index("--") + 1:]
max_tris = int(max_tris)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
before = after = 0
for ob in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
    n = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    before += n
    if n > max_tris:
        if ob.data.users > 1:
            ob.data = ob.data.copy()
        mod = ob.modifiers.new("dec", "DECIMATE")
        mod.ratio = max_tris / n
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.ops.object.modifier_apply(modifier="dec")
        ob.data.set_sharp_from_angle(angle=math.radians(40))
    after += sum(len(p.vertices) - 2 for p in ob.data.polygons)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_yup=True,
                          export_apply=True, export_cameras=False, export_lights=False)
print(f"SLIM triangles {before} -> {after}")
