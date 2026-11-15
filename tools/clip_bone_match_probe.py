"""Compare the bones a clip keys with the bones a model skeleton owns.

The Viper slide port proved the shape of the failure: a clip built from the
game's own source DMX for that model plays correctly, while a clip built on a
foreign rig (the old model's glTF joints, or an appended-tail skeleton) puts the
whole body on the floor.  The difference is the bone set the clip resolves
against, so measure it instead of guessing at the pose.

For each clip this reports

  * how many bones the clip keys and how many the skeleton has,
  * clip bones the skeleton does not own (these cannot resolve),
  * skeleton bones the clip never touches (fine: they stay at rest),
  * the clip's bone order against the skeleton's, and the first index where the
    two lists diverge -- the smallest, cheapest signal of an index drift.

  blender -b --python tools/clip_bone_match_probe.py -- \
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
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_curves import action_fcurves  # noqa: E402
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--clip", action="append", default=[])
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "clip-bone-match.json"))
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


def _import(path: Path):
    before_actions = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
    rigs = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    rig = rigs[-1]
    created = [action for action in bpy.data.actions if action.name not in before_actions]
    return rig, (created[-1] if created else None)


def _clip_bones(action) -> list[str]:
    """Bone names the action keys, in the order its curves first mention them."""
    order: list[str] = []
    for curve in action_fcurves(action):
        name = curve.data_path
        if 'pose.bones["' in name:
            bone = name.split('pose.bones["', 1)[1].split('"]', 1)[0]
        elif curve.group is not None:
            bone = curve.group.name
        else:
            continue
        if bone not in order:
            order.append(bone)
    return order


def _compare(skeleton: list[str], clip: list[str]) -> dict:
    bones = set(skeleton)
    keyed = set(clip)
    first = None
    for index, name in enumerate(clip):
        if index >= len(skeleton) or skeleton[index] != name:
            first = {"index": index, "clip": name, "skeleton": skeleton[index] if index < len(skeleton) else None}
            break
    return {
        "skeleton_bones": len(skeleton),
        "clip_bones": len(clip),
        "clip_not_in_skeleton": sorted(keyed - bones),
        "skeleton_not_keyed": len(bones - keyed),
        "first_order_divergence": first,
        "identical_order": first is None and len(clip) == len(skeleton),
    }


def main() -> int:
    args = _arguments()
    _enable_pulse()
    _clear()
    rig, _ = _import(Path(args.skeleton))
    skeleton = [bone.name for bone in rig.data.bones]
    report: dict[str, object] = {
        "skeleton": {"path": args.skeleton, "bones": len(skeleton), "names": skeleton},
        "clips": [],
    }
    for clip in args.clip:
        _clear()
        rig, action = _import(Path(clip))
        if action is None:
            report["clips"].append({"path": clip, "error": "no action imported"})
            continue
        bones = _clip_bones(action)
        report["clips"].append({"path": clip, **_compare(skeleton, bones)})
        print(f"MATCH {Path(clip).name}: keys {len(bones)} of {len(skeleton)} skeleton bones", flush=True)
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "skeleton"}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
