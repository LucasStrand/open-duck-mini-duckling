"""Write PRINT-LIST-<design>.txt for one design, with sizes, notes and rough filament from the files.

usage: write_print_list.py <workdir> <repo_dir> <design>
design: duckling, pebble or visor. Paths in the list are relative to the repo root.
"""
import os
import sys

import numpy as np

W, REPO, DESIGN = sys.argv[1], sys.argv[2], sys.argv[3]
ns = {}
exec(open(f"{W}/build/align_to_print.py").read().split('if __name__ == "__main__":')[0], ns)
read_stl, volume, bed_contact = ns["read_stl"], ns["volume"], ns["bed_contact"]

LOOKS = {
    "duckling": {"title": "DUCKLING", "blurb": "a domed head with a bill, a round chubby body",
                 "head": "yellow (#f6dc5a)", "body": "yellow (#f6dc5a)", "thigh": "deep yellow (#f2c94c)",
                 "accent": "orange (#f08a24)", "bill": True, "extra": []},
    "pebble": {"title": "PEBBLE", "blurb": "soft, pillowy curves on every shell",
               "head": "cream (#efe6d6)", "body": "sage (#9db8a0)", "thigh": "dark sage (#7f9c84)",
               "accent": "coral (#e9785f)", "bill": False,
               "extra": ["  The Pebble body comes out about 100 g lighter than the original, at the edge of",
                         "  what the walk was trained for. Tape 60-80 g of steel washers inside the body near",
                         "  the middle, or print the five body pieces at 30% infill."]},
    "visor": {"title": "VISOR", "blurb": "an angular head that rises at the back, a brow, a V-shaped chest",
              "head": "graphite (#2e3337)", "body": "graphite (#2e3337)", "thigh": "dark grey (#3d444a)",
              "accent": "orange (#ff7a1a)", "bill": False, "extra": []},
}
L = LOOKS[DESIGN]
GREY, LIGHT_GREY, BLACK_TPU, ANY = "dark grey", "light grey", "black TPU", "any"
d = f"stl/{DESIGN}"
SHELL_ROWS = [
    (f"{d}/head_{DESIGN}.stl", 1, L["head"], "NEW SHAPE. Print this first and test-fit it."),
    (f"{d}/head_bot_sheet_{DESIGN}.stl", 1, GREY, "New outline to match the head."),
    (f"{d}/left_antenna_holder_{DESIGN}.stl", 1, L["accent"], "Ear cap, new shape."),
    (f"{d}/right_antenna_holder_{DESIGN}.stl", 1, L["accent"], "Ear cap, new shape."),
    (f"{d}/body_front_{DESIGN}.stl", 1, L["body"], "NEW SHAPE."),
    (f"{d}/body_back_{DESIGN}.stl", 1, L["body"], "NEW SHAPE."),
    (f"{d}/body_middle_top_{DESIGN}.stl", 1, L["body"], "NEW SHAPE."),
    (f"{d}/body_middle_bottom_{DESIGN}.stl", 1, L["body"], "NEW SHAPE."),
    (f"{d}/battery_pack_lid_{DESIGN}.stl", 1, L["body"], "NEW SHAPE."),
    (f"{d}/left_cache_{DESIGN}.stl", 1, L["thigh"], "Thigh cover, NEW SHAPE."),
    (f"{d}/right_cache_{DESIGN}.stl", 1, L["thigh"], "Thigh cover, NEW SHAPE."),
]
if L["bill"]:
    SHELL_ROWS.append(("stl/addons/duck_bill.stl", 1, L["accent"], "Flat side down, no supports. Glued on the face below the eyes."))
o = "stl/original"
ORIGINAL_ROWS = [
    (f"{o}/foot_top.stl", 2, L["accent"], ""), (f"{o}/foot_side.stl", 2, L["accent"], ""),
    (f"{o}/foot_bottom_pla.stl", 2, GREY, ""), (f"{o}/foot_bottom_tpu.stl", 2, BLACK_TPU, "The grippy sole: must be TPU."),
    (f"{o}/knee_to_ankle_left_sheet.stl", 4, GREY, ""), (f"{o}/knee_to_ankle_right_sheet.stl", 4, GREY, ""),
    (f"{o}/leg_spacer.stl", 4, GREY, ""),
    (f"{o}/left_roll_to_pitch.stl", 1, L["accent"], "Hip."), (f"{o}/right_roll_to_pitch.stl", 1, L["accent"], "Hip."),
    (f"{o}/roll_motor_bottom.stl", 2, LIGHT_GREY, ""), (f"{o}/roll_motor_top.stl", 2, LIGHT_GREY, ""),
    (f"{o}/trunk_bottom.stl", 1, GREY, "Main frame."), (f"{o}/trunk_top.stl", 1, GREY, "Main frame."),
    (f"{o}/neck_left_sheet.stl", 1, GREY, ""), (f"{o}/neck_right_sheet.stl", 1, GREY, ""),
    (f"{o}/head_pitch_to_yaw.stl", 1, GREY, ""), (f"{o}/head_yaw_to_roll.stl", 1, GREY, ""),
    (f"{o}/head_roll_mount.stl", 1, GREY, ""),
    (f"{o}/left_eye.stl", 1, ANY, "Optional: eye lights."), (f"{o}/right_eye.stl", 1, ANY, "Optional: eye lights."),
    (f"{o}/bulb.stl", 1, ANY, "Optional: projector."), (f"{o}/flash_light_module.stl", 1, ANY, "Optional: projector."),
    (f"{o}/flash_reflector_interface.stl", 1, ANY, "Optional: projector."),
    (f"{o}/speaker_interface.stl", 1, ANY, "Optional: speaker."), (f"{o}/speaker_stand.stl", 1, ANY, "Optional: speaker."),
]

rows, grams, biggest = [], {}, (0, "")
for path, n, col, note in SHELL_ROWS + ORIGINAL_ROWS:
    t = read_stl(f"{REPO}/{path}")
    size = np.sort(np.ptp(t.reshape(-1, 3), axis=0))[::-1]
    mat = "TPU 40%" if "tpu" in path else "PLA 15%"
    if "NEW SHAPE" in note and bed_contact(t) < 100:
        note += " No flat face: needs supports or another orientation."
    g = volume(t) / 1000 * (1.21 if "TPU" in mat else 1.24) * 0.6 * n  # rough: walls + 15-40% infill
    grams[col] = grams.get(col, 0) + g
    if size[0] > biggest[0]:
        biggest = (size[0], f"{os.path.basename(path)} ({size[0]:.0f} x {size[1]:.0f} x {size[2]:.0f} mm)")
    rows.append((path, n, mat, col, f"{size[0]:.0f}x{size[1]:.0f}x{size[2]:.0f}", note))

pieces = sum(r[1] for r in rows)
w = [max(len(str(r[i])) for r in rows) for i in range(5)]
title = f"OPEN DUCK MINI v2 - \"{L['title']}\" PRINT LIST"
lines = [
    title, "=" * len(title), "",
    f"{len(rows)} files, {pieces} pieces in total. Everything is in millimetres.",
    f"The official parts with the outer shells swapped for the {L['title'].title()} design: {L['blurb']}.",
    f"See images/{DESIGN}-views.png for what the finished duck looks like.", "",
    "SETTINGS",
    "  - PLA at 15% infill for everything, except foot_bottom_tpu: TPU at 40% infill.",
    "  - New shells: 3 walls/perimeters, supports where the slicer asks for them.",
    "    The files come in the official orientation; the curved ones may print better",
    "    turned onto a different face. Let the slicer's lay-flat/auto-orient decide.",
    f"  - Biggest part: {biggest[1]}. Needs a bed of at least 220 x 200 mm.", "",
    "FIRST",
    "  The new shells haven't been test-printed. Print the head and the head bottom plate",
    "  first and check the head sits flush and the screw holes line up before printing",
    "  the body. Holes near strongly curved areas may need drilling out.",
]
if L["extra"]:
    lines += ["", "WEIGHT"] + L["extra"]
lines += ["", "PARTS", f"  {'file':<{w[0]}}  {'qty':>3}  {'material':<{w[2]}}  {'colour':<{w[3]}}  {'size mm':<{w[4]}}  notes"]
for r in rows:
    lines.append(f"  {r[0]:<{w[0]}}  {r[1]:>3}  {r[2]:<{w[2]}}  {r[3]:<{w[3]}}  {r[4]:<{w[4]}}  {r[5]}".rstrip())
lines += ["", "ROUGH FILAMENT (estimate; the slicer gives the real number)"]
for col, g in sorted(grams.items(), key=lambda x: -x[1]):
    lines.append(f"  {col:<24} about {round(g, -1):.0f} g")
lines += ["", "NOT INCLUDED",
          "  Servos, electronics, screws, heat-set inserts and bearings.", "",
          "LICENCE",
          "  Original parts: Open Duck Mini by Antoine Pirrone and contributors, Apache License 2.0",
          "  (see LICENSE and NOTICE)."]
open(f"{REPO}/PRINT-LIST-{DESIGN}.txt", "w").write("\n".join(lines) + "\n")
print(f"wrote PRINT-LIST-{DESIGN}.txt: {len(rows)} files, {pieces} pieces, biggest {biggest[1]}")
