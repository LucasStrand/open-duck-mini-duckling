# Tools

The scripts that built the Duckling, in the order they ran. They work in one working
directory (`<workdir>` below) that holds the downloads and intermediate files.

| Step | Script | What it does |
|---|---|---|
| 1 | `pose_duck.py` | Loads the upstream robot export (`mini_bdx/robots/open_duck_mini_v2/robot.xml`) in MuJoCo, poses it in the "home" standing stance and writes every visual mesh in world space to JSON. |
| 2 | `duck_blender.py` | Builds that in Blender, renders it and exports a web GLB. Its `blend` mode saves the assembled scene (`blender/open-duck-mini.blend`). |
| 3 | `duck_designs.py` | Colour schemes plus the separate bill and tail add-ons. |
| 4 | `duck_reshape.py` | The shell redesigns (Pebble, Duckling, Visor): free-form deformation cages, the clearance check against inside parts, weight estimates, renders, STLs and a GLB. Its `official_head` mode rebuilds the head from the current official `head.stl`. |
| 5 | `align_to_print.py` | Finds the rigid transform from each robot-export part to its official print STL (and checks they're the same part). |
| 6 | `make_print_pack.py` | Moves the reshaped shells into the official print orientation and checks them. |
| 7 | `clean_stl.py`, `fix_fin.py` | Merge duplicate vertices, dissolve sliver triangles, close the gaps they leave. |
| 8 | `write_print_list.py` | Writes `PRINT-LIST.txt` from the actual files. |
| – | `slim_glb.py` | Caps triangles per mesh in a GLB for the web. |

`data/mujoco_mesh_frames.json` holds the transform MuJoCo applies to each mesh when it loads
(it recentres meshes on their centre of mass), and `data/print_transforms.json` the transform
from each robot-export part to its official print file. Both are needed to go from the Blender
scene back to printable files.

Blender scripts run as `blender -b <file.blend> -P <script> -- <args>`; the others need Python
with `numpy`, `scipy`, `mujoco` and `pillow`.
