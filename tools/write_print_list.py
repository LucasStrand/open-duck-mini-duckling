"""Write PRINT-LIST.txt for the Duckling print pack, with sizes and rough filament from the actual files.

usage: write_print_list.py <workdir> <pack_dir>
"""
import os
import sys

import numpy as np

S, PACK = sys.argv[1], sys.argv[2]
ns = {}
exec(open(f"{S}/build/align_to_print.py").read().split('if __name__ == "__main__":')[0], ns)
read_stl, volume, bed_contact = ns["read_stl"], ns["volume"], ns["bed_contact"]

YELLOW, DEEP_YELLOW, ORANGE, GREY, LIGHT_GREY, BLACK_TPU, ANY = (
    "yellow (#f6dc5a)", "deep yellow (#f2c94c)", "orange (#f08a24)", "dark grey", "light grey", "black TPU", "any")

# folder, file, copies, material, colour, note
PARTS = [
    ("2_duckling_shells", "head_duckling.stl", 1, "PLA 15%", YELLOW, "NEW SHAPE. Print this first and test-fit it."),
    ("2_duckling_shells", "head_bot_sheet_duckling.stl", 1, "PLA 15%", GREY, "New outline to match the head."),
    ("2_duckling_shells", "left_antenna_holder_duckling.stl", 1, "PLA 15%", ORANGE, "Ear cap, new shape."),
    ("2_duckling_shells", "right_antenna_holder_duckling.stl", 1, "PLA 15%", ORANGE, "Ear cap, new shape."),
    ("2_duckling_shells", "body_front_duckling.stl", 1, "PLA 15%", YELLOW, "NEW SHAPE. No flat face left: needs supports."),
    ("2_duckling_shells", "body_back_duckling.stl", 1, "PLA 15%", YELLOW, "NEW SHAPE."),
    ("2_duckling_shells", "body_middle_top_duckling.stl", 1, "PLA 15%", YELLOW, "NEW SHAPE. Needs supports."),
    ("2_duckling_shells", "body_middle_bottom_duckling.stl", 1, "PLA 15%", YELLOW, "NEW SHAPE."),
    ("2_duckling_shells", "battery_pack_lid_duckling.stl", 1, "PLA 15%", YELLOW, "NEW SHAPE."),
    ("2_duckling_shells", "left_cache_duckling.stl", 1, "PLA 15%", DEEP_YELLOW, "Thigh cover, NEW SHAPE."),
    ("2_duckling_shells", "right_cache_duckling.stl", 1, "PLA 15%", DEEP_YELLOW, "Thigh cover, NEW SHAPE."),
    ("3_duckling_bill", "duck_bill.stl", 1, "PLA 15%", ORANGE, "Flat side down, no supports. Glued on the face below the eyes."),
    ("1_original_parts", "foot_top.stl", 2, "PLA 15%", ORANGE, ""),
    ("1_original_parts", "foot_side.stl", 2, "PLA 15%", ORANGE, ""),
    ("1_original_parts", "foot_bottom_pla.stl", 2, "PLA 15%", GREY, ""),
    ("1_original_parts", "foot_bottom_tpu.stl", 2, "TPU 40%", BLACK_TPU, "The grippy sole: must be TPU."),
    ("1_original_parts", "knee_to_ankle_left_sheet.stl", 4, "PLA 15%", GREY, ""),
    ("1_original_parts", "knee_to_ankle_right_sheet.stl", 4, "PLA 15%", GREY, ""),
    ("1_original_parts", "leg_spacer.stl", 4, "PLA 15%", GREY, ""),
    ("1_original_parts", "left_roll_to_pitch.stl", 1, "PLA 15%", ORANGE, "Hip."),
    ("1_original_parts", "right_roll_to_pitch.stl", 1, "PLA 15%", ORANGE, "Hip."),
    ("1_original_parts", "roll_motor_bottom.stl", 2, "PLA 15%", LIGHT_GREY, ""),
    ("1_original_parts", "roll_motor_top.stl", 2, "PLA 15%", LIGHT_GREY, ""),
    ("1_original_parts", "trunk_bottom.stl", 1, "PLA 15%", GREY, "Main frame."),
    ("1_original_parts", "trunk_top.stl", 1, "PLA 15%", GREY, "Main frame."),
    ("1_original_parts", "neck_left_sheet.stl", 1, "PLA 15%", GREY, ""),
    ("1_original_parts", "neck_right_sheet.stl", 1, "PLA 15%", GREY, ""),
    ("1_original_parts", "head_pitch_to_yaw.stl", 1, "PLA 15%", GREY, ""),
    ("1_original_parts", "head_yaw_to_roll.stl", 1, "PLA 15%", GREY, ""),
    ("1_original_parts", "head_roll_mount.stl", 1, "PLA 15%", GREY, ""),
    ("1_original_parts", "left_eye.stl", 1, "PLA 15%", ANY, "Optional: eye lights."),
    ("1_original_parts", "right_eye.stl", 1, "PLA 15%", ANY, "Optional: eye lights."),
    ("1_original_parts", "bulb.stl", 1, "PLA 15%", ANY, "Optional: projector."),
    ("1_original_parts", "flash_light_module.stl", 1, "PLA 15%", ANY, "Optional: projector."),
    ("1_original_parts", "flash_reflector_interface.stl", 1, "PLA 15%", ANY, "Optional: projector."),
    ("1_original_parts", "speaker_interface.stl", 1, "PLA 15%", ANY, "Optional: speaker."),
    ("1_original_parts", "speaker_stand.stl", 1, "PLA 15%", ANY, "Optional: speaker."),
]

on_disk = {f"{d}/{f}" for d in os.listdir(PACK) if os.path.isdir(f"{PACK}/{d}") for f in os.listdir(f"{PACK}/{d}") if f.endswith(".stl")}
listed = {f"{d}/{f}" for d, f, *_ in PARTS}
assert on_disk == listed, f"pack and list differ: missing {sorted(listed - on_disk)}, unlisted {sorted(on_disk - listed)}"

rows, grams, biggest = [], {}, (0, "")
for d, f, n, mat, col, note in PARTS:
    t = read_stl(f"{PACK}/{d}/{f}")
    size = np.sort(np.ptp(t.reshape(-1, 3), axis=0))[::-1]
    g = volume(t) / 1000 * (1.21 if "TPU" in mat else 1.24) * 0.6 * n  # rough: walls + 15-40% infill
    grams[col] = grams.get(col, 0) + g
    if size[0] > biggest[0]:
        biggest = (size[0], f"{f} ({size[0]:.0f} x {size[1]:.0f} x {size[2]:.0f} mm)")
    rows.append((f"{d}/{f}", n, mat, col, f"{size[0]:.0f}x{size[1]:.0f}x{size[2]:.0f}", note))

pieces = sum(r[1] for r in rows)
w = [max(len(str(r[i])) for r in rows) for i in range(5)]
lines = [
    "OPEN DUCK MINI v2 - \"DUCKLING\" PRINT PACK",
    "=" * 44,
    "",
    f"{len(rows)} files, {pieces} pieces in total. Everything is in millimetres.",
    "A walking robot duck (github.com/apirrone/Open_Duck_Mini). This pack is the official",
    "parts with the outer shells swapped for a rounder \"Duckling\" design, plus a bill.",
    "See duckling-preview.png for what the finished duck looks like.",
    "",
    "FOLDERS",
    "  1_original_parts   official parts, unchanged",
    "  2_duckling_shells  redesigned head, body and thigh covers (replace the official ones)",
    "  3_duckling_bill    the bill, glued on the face",
    "",
    "SETTINGS",
    "  - PLA at 15% infill for everything, except foot_bottom_tpu: TPU at 40% infill.",
    "  - Duckling shells: 3 walls/perimeters, supports where the slicer asks for them.",
    "    The files come in the official orientation; the curved ones may print better",
    "    turned onto a different face. Let the slicer's lay-flat/auto-orient decide.",
    f"  - Biggest part: {biggest[1]}. Needs a bed of at least 220 x 200 mm.",
    "",
    "FIRST",
    "  The Duckling shells are new and haven't been test-printed. Print head_duckling.stl",
    "  first and check it fits head_bot_sheet_duckling.stl and the head mount before",
    "  printing the body. Holes near strongly curved areas may need drilling out.",
    "",
    "PARTS",
    f"  {'file':<{w[0]}}  {'qty':>3}  {'material':<{w[2]}}  {'colour':<{w[3]}}  {'size mm':<{w[4]}}  notes",
]
for r in rows:
    lines.append(f"  {r[0]:<{w[0]}}  {r[1]:>3}  {r[2]:<{w[2]}}  {r[3]:<{w[3]}}  {r[4]:<{w[4]}}  {r[5]}")
lines += ["", "ROUGH FILAMENT (estimate; the slicer gives the real number)"]
for col, g in sorted(grams.items(), key=lambda x: -x[1]):
    lines.append(f"  {col:<24} about {round(g, -1):.0f} g")
lines += [
    "",
    "NOT INCLUDED",
    "  Servos, electronics, screws, heat-set inserts and bearings. Parts list and build",
    "  steps: the Open Duck Mini build guide.",
    "",
    "LICENCE",
    "  Original parts: Open Duck Mini by Antoine Pirrone and contributors, Apache License 2.0",
    "  (see LICENSE). Modified files: everything in 2_duckling_shells (reshaped from the",
    "  official parts) and 3_duckling_bill (new).",
]
open(f"{PACK}/PRINT-LIST.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
