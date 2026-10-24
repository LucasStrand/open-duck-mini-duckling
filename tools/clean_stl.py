"""Merge duplicate vertices and dissolve zero-area slivers in STL files (mm), in place."""
import sys
import bmesh, bpy
paths = sys.argv[sys.argv.index("--") + 1:]
for path in paths:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.stl_import(filepath=path, global_scale=1.0)
    ob = bpy.context.selected_objects[0]
    bm = bmesh.new(); bm.from_mesh(ob.data)
    before = len(bm.faces)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.0005)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    vol = bm.calc_volume()
    bm.to_mesh(ob.data); bm.free()
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0, ascii_format=False)
    print(f"CLEAN {path.split('/')[-1]}: {before} -> {len(ob.data.polygons)} triangles, volume {vol / 1000:.1f} cm3")
