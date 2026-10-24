"""Pose the full Open Duck Mini v2 model in its 'home' stance and dump every visual mesh in world space."""
import json, sys
import numpy as np
import mujoco

xml, out = sys.argv[1], sys.argv[2]
HOME = {  # 'home' keyframe from Open_Duck_Playground scene_flat_terrain.xml
    "left_hip_yaw": 0.002, "left_hip_roll": 0.053, "left_hip_pitch": -0.63, "left_knee": 1.368, "left_ankle": -0.784,
    "neck_pitch": 0, "head_pitch": 0, "head_yaw": 0, "head_roll": 0,
    "right_hip_yaw": -0.003, "right_hip_roll": -0.065, "right_hip_pitch": 0.635, "right_knee": 1.379, "right_ankle": -0.796,
}
m = mujoco.MjModel.from_xml_path(xml)
d = mujoco.MjData(m)
for name, q in HOME.items():
    d.qpos[m.jnt_qposadr[m.joint(name).id]] = q
mujoco.mj_kinematics(m, d)

meshes, geoms = {}, []
for g in range(m.ngeom):
    if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
        continue
    mid = int(m.geom_dataid[g])
    name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mid)
    if name not in meshes:
        v0, nv = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
        f0, nf = m.mesh_faceadr[mid], m.mesh_facenum[mid]
        meshes[name] = {"v": m.mesh_vert[v0:v0 + nv].round(6).tolist(), "f": m.mesh_face[f0:f0 + nf].tolist()}
    T = np.eye(4)
    T[:3, :3] = d.geom_xmat[g].reshape(3, 3)
    T[:3, 3] = d.geom_xpos[g]
    geoms.append({"mesh": name, "matrix": T.round(7).tolist(), "rgba": m.geom_rgba[g].round(4).tolist()})

# put the lowest point on the floor
lo = min((np.array(meshes[gm["mesh"]]["v"]) @ np.array(gm["matrix"])[:3, :3].T + np.array(gm["matrix"])[:3, 3])[:, 2].min() for gm in geoms)
for gm in geoms:
    gm["matrix"][2][3] -= lo
json.dump({"meshes": meshes, "geoms": geoms}, open(out, "w"))
tris = sum(len(meshes[g["mesh"]]["f"]) for g in geoms)
print(f"{len(geoms)} parts, {len(meshes)} unique meshes, {tris} triangles placed, floor offset {lo:.4f} m")
