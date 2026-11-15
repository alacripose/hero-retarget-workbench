"""Report the skeleton a clip DMX carries: bone names, parents, rest transforms.

Two clips whose channel values match can still pose a rig differently if the
skeletons they declare differ (a bone parented under root_motion in one file and
left at the root in the other, say), and the value-level sweep cannot see that.
This prints what the DMX importer ends up with, per file, so those structural
differences can be compared directly.

  blender -b --python tools/clip_rig_shape_probe.py -- --a <ours.dmx> --b <game.dmx> [--report <json>]
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy

PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--report", default="")
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


def _shape(path: Path) -> dict:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not rigs:
        raise RuntimeError(f"no armature in {path}")
    rig = rigs[-1]
    bones = {}
    for bone in rig.data.bones:
        rest = bone.matrix_local
        bones[bone.name] = {
            "parent": bone.parent.name if bone.parent else None,
            "head": [round(v, 3) for v in rest.translation],
            "z": [round(v, 3) for v in rest.col[2][:3]],
        }
    return {"file": str(path), "bones": bones, "count": len(bones)}


def main() -> int:
    args = _arguments()
    _enable_pulse()
    a = _shape(Path(args.a))
    b = _shape(Path(args.b))
    report = {"a": a, "b": b}

    only_a = sorted(set(a["bones"]) - set(b["bones"]))
    only_b = sorted(set(b["bones"]) - set(a["bones"]))
    parent_diff = sorted(
        name
        for name in set(a["bones"]) & set(b["bones"])
        if a["bones"][name]["parent"] != b["bones"][name]["parent"]
    )
    rest_diff = sorted(
        name
        for name in set(a["bones"]) & set(b["bones"])
        if a["bones"][name]["head"] != b["bones"][name]["head"] or a["bones"][name]["z"] != b["bones"][name]["z"]
    )
    report["diff"] = {"only_a": only_a, "only_b": only_b, "parent": parent_diff, "rest": rest_diff}

    print(f"SHAPE a {a['count']} bones, b {b['count']} bones")
    print(f"SHAPE only in a: {only_a}")
    print(f"SHAPE only in b: {only_b}")
    print(f"SHAPE parent differs ({len(parent_diff)}): {parent_diff[:20]}")
    for name in parent_diff[:10]:
        print(f"  {name}: a parent {a['bones'][name]['parent']} / b parent {b['bones'][name]['parent']}")
    print(f"SHAPE rest differs ({len(rest_diff)}): {rest_diff[:20]}")
    for name in rest_diff[:6]:
        print(f"  {name}: a head {a['bones'][name]['head']} z {a['bones'][name]['z']}")
        print(f"  {' ' * len(name)}  b head {b['bones'][name]['head']} z {b['bones'][name]['z']}")

    if args.report:
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
