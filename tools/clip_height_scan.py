"""Scan every clip's pelvis height and compare an authored build with stock.

Owner report: with the added tail, the hero lifts off the ground for a few frames
when they start moving.  The lift is not in ``root_motion`` (measured 0.0 in every
sampled clip) and the sampled run/idle pelvis heights match stock exactly, so the
culprit is a specific clip, and the way to find it is to read every clip rather
than the two that happened to be open.

For each clip this samples the pelvis and both feet in world space per frame and
records the first-frame height, the min/max and the largest single-frame step, so
a clip that starts above the ground -- or pops up for a few frames -- is visible
next to its stock counterpart.

  blender -b --python tools/clip_height_scan.py -- \
      --skeleton <skel.dmx> --stock <dir of .dmx> [--authored <dir>] --report <json>
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
WATCH = ("pelvis", "ball_L", "ball_R", "ankle_L", "ankle_R")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--stock", required=True)
    parser.add_argument("--authored", default="")
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "clip-height-scan.json"))
    parser.add_argument("--limit", type=int, default=0)
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


def _load_skeleton(skeleton: str):
    """Import the skeleton once: re-importing it per clip costs minutes each."""
    _clear()
    scene = bpy.context.scene
    scene.render.fps = 30
    bpy.ops.import_scene.kst_dmx(filepath=skeleton, append="NEW_ARMATURE")
    return [obj for obj in bpy.data.objects if obj.type == "ARMATURE"][-1]


def _scan(path: Path, skeleton: str, rig=None) -> dict:
    scene = bpy.context.scene
    scene.render.fps = 30
    if rig is None:
        rig = _load_skeleton(skeleton)
    # A rig that keeps its previous action makes the next APPEND reuse it instead
    # of creating one, which silently turned every clip after the first into "no
    # action" in the first run of this scan.
    if rig.animation_data is not None:
        rig.animation_data.action = None
    before = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    if not created:
        return {"clip": path.name, "error": "no action"}
    action = created[-1]
    rig.animation_data_create()
    rig.animation_data.action = action
    if getattr(action, "slots", None):
        rig.animation_data.action_slot = action.slots[0]
    start, end = (int(round(value)) for value in action.frame_range)
    trace = {name: [] for name in WATCH if rig.pose.bones.get(name) is not None}
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for name in trace:
            trace[name].append(rig.pose.bones[name].matrix.translation.z)
    rig.animation_data.action = None
    bpy.data.actions.remove(action)
    out = {"clip": path.name, "frames": end - start + 1, "bones": {}}
    for name, heights in trace.items():
        steps = [abs(b - a) for a, b in zip(heights, heights[1:])]
        out["bones"][name] = {
            "first": round(heights[0], 3),
            "min": round(min(heights), 3),
            "max": round(max(heights), 3),
            "spread": round(max(heights) - min(heights), 3),
            "biggest_step": round(max(steps), 3) if steps else 0.0,
        }
    return out


def main() -> int:
    args = _arguments()
    _enable_pulse()
    stock_dir = Path(args.stock)
    authored_dir = Path(args.authored) if args.authored else None
    clips = sorted(stock_dir.glob("*.dmx"))
    if args.limit:
        clips = clips[: args.limit]
    report: dict[str, object] = {"skeleton": args.skeleton, "clips": [], "pairs": []}
    rig = _load_skeleton(args.skeleton)
    for path in clips:
        report["clips"].append(_scan(path, args.skeleton, rig))
    if authored_dir is not None and authored_dir.is_dir():
        authored = {path.name: path for path in authored_dir.glob("*.dmx")}
        for path in clips:
            other = authored.get(path.name)
            if other is None:
                continue
            report["pairs"].append({"clip": path.name, "stock": _scan(path, args.skeleton, rig),
                                    "authored": _scan(other, args.skeleton, rig)})
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def summary(entry, tag):
        pelvis = entry.get("bones", {}).get("pelvis")
        if not pelvis:
            return
        foot = [value for name, value in entry["bones"].items() if name.startswith(("ball", "ankle"))]
        foot_first = min((value["first"] for value in foot), default=0.0)
        print(
            f"SCAN {tag} {entry['clip']:34s} f={entry['frames']:<4} pelvis first {pelvis['first']:8.3f} "
            f"min {pelvis['min']:8.3f} max {pelvis['max']:8.3f} step {pelvis['biggest_step']:7.3f} "
            f"lowest_foot {foot_first:8.3f}",
            flush=True,
        )

    for entry in report["clips"]:
        summary(entry, "stock   ")
    for pair in report["pairs"]:
        summary(pair["stock"], "pair-stk")
        summary(pair["authored"], "pair-aut")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
