"""Sample the root and pelvis height of a clip, frame by frame.

Owner report: with the added tail, the hero lifts off the ground for a few frames
when they start moving.  A vertical lift lives in one of three places -- the
clip's own ``root_motion`` translation, the pelvis translation, or a bone whose
rest height the bake moved -- so read those numbers instead of guessing.

Prints, per clip: the frame count, and for ``root_motion`` and ``pelvis`` the
local translation at the first frames and across the whole clip (min/max/mean of
the vertical component), so a clip that starts above the ground is visible.

  blender -b --python tools/root_height_probe.py -- \
      --skeleton <skel.dmx> --clip <clip.dmx> [--clip <other.dmx>] --report <json>
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
WATCH = ("root_motion", "pelvis")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--clip", action="append", default=[])
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "root-height.json"))
    return parser.parse_args(argv)


def _enable_pulse() -> None:
    if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.export_scene, "smd"):
        return
    for module in PULSE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError:
            continue
        if hasattr(bpy.types.Scene, "vs"):
            return
    raise RuntimeError("pulse-src-ops-missing")


def _clear() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def _sample(path: str, skeleton: str) -> dict:
    _clear()
    scene = bpy.context.scene
    scene.render.fps = 30
    bpy.ops.import_scene.kst_dmx(filepath=skeleton, append="NEW_ARMATURE")
    rig = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"][-1]
    before = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=path, append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    if not created:
        return {"path": path, "error": "no action"}
    action = created[-1]
    rig.animation_data_create()
    rig.animation_data.action = action
    if getattr(action, "slots", None):
        rig.animation_data.action_slot = action.slots[0]
    start, end = (int(round(value)) for value in action.frame_range)
    out = {"path": path, "start": start, "end": end, "frames": end - start + 1, "watch": {}}
    for name in WATCH:
        bone = rig.pose.bones.get(name)
        if bone is None:
            continue
        samples = []
        for frame in range(start, min(end, start + 6) + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            samples.append(
                {"frame": frame,
                 "local": [round(v, 4) for v in bone.location],
                 "world": [round(v, 4) for v in bone.matrix.translation]}
            )
        heights = []
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            heights.append(bone.matrix.translation.z)
        out["watch"][name] = {
            "first": samples,
            "vertical_world_min": round(min(heights), 4),
            "vertical_world_max": round(max(heights), 4),
            "spread": round(max(heights) - min(heights), 4),
        }
    return out


def main() -> int:
    args = _arguments()
    _enable_pulse()
    report = {"skeleton": args.skeleton, "clips": []}
    for clip in args.clip:
        report["clips"].append(_sample(clip, args.skeleton))
        entry = report["clips"][-1]
        root = entry.get("watch", {}).get("root_motion", {})
        pelvis = entry.get("watch", {}).get("pelvis", {})
        print(
            f"HEIGHT {Path(clip).name:32s} frames={entry.get('frames')} "
            f"root[min {root.get('vertical_world_min')} max {root.get('vertical_world_max')} spread {root.get('spread')}] "
            f"pelvis[min {pelvis.get('vertical_world_min')} max {pelvis.get('vertical_world_max')} spread {pelvis.get('spread')}]",
            flush=True,
        )
        for row in (root.get("first") or [])[:4]:
            print(f"HEIGHT   {Path(clip).name} root f{row['frame']} local {row['local']} world {row['world']}", flush=True)
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
