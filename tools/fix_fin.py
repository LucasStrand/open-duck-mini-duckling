"""Remove the smallest face on each 3-way edge, then close the gaps it leaves (STL in mm, in place)."""
import sys
import bmesh, bpy
path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.stl_import(filepath=path, global_scale=1.0)
ob = bpy.context.selected_objects[0]
bm = bmesh.new(); bm.from_mesh(ob.data)
for e in [e for e in bm.edges if len(e.link_faces) > 2]:
    areas = sorted((f.calc_area(), i) for i, f in enumerate(e.link_faces))
    print("FIN edge length %.4f mm, face areas %s mm2" % (e.calc_length(), [round(a, 4) for a, _ in areas]))
    bmesh.ops.delete(bm, geom=[list(e.link_faces)[areas[0][1]]], context="FACES")
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
bnd = [e for e in bm.edges if len(e.link_faces) == 1]
print("FIN boundary edges after delete:", len(bnd), [round(e.calc_length(), 4) for e in bnd][:10])
bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
print("FIN now holes %d, non-manifold %d, volume %.1f cm3" % (sum(1 for e in bm.edges if len(e.link_faces) == 1), sum(1 for e in bm.edges if len(e.link_faces) > 2), bm.calc_volume() / 1000))
bm.to_mesh(ob.data); bm.free()
bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0)
