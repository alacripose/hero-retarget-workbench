"""Measure whether the accepted 6:47 body bake is faithful, bone by bone.

The owner's reading of the 6:47 Shiv build: the tail animations work and the body
is upright; the arms and the head are rotated wrong.  Before blaming the engine
or the graph, measure the bake itself.  ``tailops._bake_body_action`` reproduces
the stock clip's pose on the model rig by solved pose matrices, so if it is
faithful the target pose must equal the source pose (with the source root's
rotation divided out, which is what the bake does) at every frame, on every
shared bone.

  blender -b --python tools/shiv_bake_fidelity_probe.py -- \
      --skeleton <shiv_skel.dmx> --clip <stock clip dmx> --body <shiv_body.dmx> \
      --report artifacts/receipts/shiv-bake-fidelity.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
FOCUS = ("clavicle_L", "clavicle_R", "arm_upper_L", "arm_upper_R", "arm_lower_L", "arm_lower_R",
         "hand_L", "hand_R", "neck_0", "head", "pelvis", "spine_2")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-bake-fidelity.json"))
    parser.add_argument("--out", default=str(REPO / "artifacts" / "oldviper" / "shiv-fidelity"))
    return parser.parse_args(argv)


def _enable_pulse() -> str:
    if hasattr(bpy.types.Scene, "vs") and hasattr(bpy.ops.export_scene, "smd"):
        return "already enabled"
    for module in PULSE_MODULES:
        try:
            bpy.ops.preferences.addon_enable(module=module)
        except RuntimeError:
            continue
        if hasattr(bpy.types.Scene, "vs"):
            return module
    raise RuntimeError("pulse-src-ops-missing")


def _disable_installed_addon() -> list[str]:
    disabled = []
    for module in list(bpy.context.preferences.addons.keys()):
        if module == "dmf_fidelity_probe" or not module.endswith("hero_retarget_workbench"):
            continue
        try:
            bpy.ops.preferences.addon_disable(module=module)
            disabled.append(module)
        except RuntimeError:
            continue
    return disabled


def _unshadow_forge() -> None:
    for entry in list(sys.path):
        candidate = Path(str(entry))
        if candidate.name == "hero_retarget_workbench":
            sys.path.remove(entry)
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        path = str(getattr(sys.modules[name], "__file__", "") or "")
        if "hero_retarget_workbench" in path:
            del sys.modules[name]
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_fidelity_probe", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_fidelity_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _clear() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def main() -> int:
    args = _arguments()
    report: dict[str, object] = {"skeleton": args.skeleton, "clip": args.clip, "body": args.body}
    report["pulse"] = _enable_pulse()
    report["disabled_installed"] = _disable_installed_addon()
    _unshadow_forge()
    _load_addon()
    tailops = sys.modules["dmf_fidelity_probe.tailops"]

    _clear()
    scene = bpy.context.scene
    scene.render.fps = 30
    bpy.ops.import_scene.kst_dmx(filepath=args.skeleton, append="NEW_ARMATURE")
    source = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"][-1]
    before = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=args.clip, append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    if not created:
        raise RuntimeError("clip-import-no-action")
    action = created[0]
    bpy.ops.import_scene.kst_dmx(filepath=args.body, append="NEW_ARMATURE")
    body = [obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj != source][-1]

    start, end = (int(round(value)) for value in action.frame_range)
    frames = sorted({start, start + (end - start) // 2, end, start + (end - start) // 4})
    body_action = tailops._bake_body_action(body, source, action, "DMF fidelity")

    rows = []
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        root = source.pose.bones.get("root_motion")
        axes = root.matrix.to_quaternion().to_matrix().inverted().to_4x4() if root is not None else Matrix.Identity(4)
        for bone in body.pose.bones:
            sample = source.pose.bones.get(bone.name)
            if sample is None:
                continue
            solver_input = bone.name.endswith(("_IKTARGET", "_OFFSET")) or bone.name.startswith(("muzzle", "weaponHand"))
            expected = (
                sample.matrix.copy()
                if bone.name == "root_motion" or solver_input
                else axes @ sample.matrix
            )
            actual = bone.matrix
            turn = math.degrees(expected.to_quaternion().rotation_difference(actual.to_quaternion()).angle)
            move = (expected.translation - actual.translation).length
            rows.append({"frame": frame, "bone": bone.name, "turn_deg": round(turn, 3), "move": round(move, 4)})
    rows.sort(key=lambda row: -row["turn_deg"])
    # How much the root division used to move the solver inputs: for each IK/aim
    # bone, the angle between its authored pose and the same pose rotated by the
    # source root.  This is the rotation the arms and head were solved against.
    scene.frame_set(frames[0])
    bpy.context.view_layer.update()
    root = source.pose.bones.get("root_motion")
    axes = root.matrix.to_quaternion().to_matrix().inverted().to_4x4() if root is not None else Matrix.Identity(4)
    report["solver_input_root_offset"] = {
        bone.name: round(
            math.degrees(
                bone.matrix.to_quaternion().rotation_difference((axes @ bone.matrix).to_quaternion()).angle
            ),
            3,
        )
        for bone in body.pose.bones
        if bone.name.endswith(("_IKTARGET", "_OFFSET")) or bone.name.startswith(("muzzle", "weaponHand"))
    }
    report["frames"] = frames
    report["bones_checked"] = len({row["bone"] for row in rows})
    report["worst"] = rows[:20]
    report["focus"] = [row for row in rows if row["bone"] in FOCUS][:24]
    report["worst_turn_by_bone"] = {
        name: round(max(row["turn_deg"] for row in rows if row["bone"] == name), 3)
        for name in sorted({row["bone"] for row in rows})
    }

    # The bake can be exact in Blender and still lose the pose on the way out, so
    # write the action through the same exporter the workbench uses, import it
    # again, and compare.  This separates "the bake is wrong" from "the written
    # clip is wrong", which the engine cannot tell us.
    clipops = sys.modules["dmf_fidelity_probe.clipops"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    settings = scene.dmf
    settings.target_armature = body
    entry = settings.clips.add()
    entry.name = "fidelity.dmx"
    entry.label = "fidelity"
    entry.kind = "dmx"
    entry.action = body_action.name
    entry.state = "IMPORTED"
    entry.ag = "AG2"
    written = clipops.write_action(settings, entry, out, target=out / "fidelity.dmx")
    baked = {}
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        baked[frame] = {bone.name: bone.matrix.copy() for bone in body.pose.bones}

    before_round = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=str(written), append="NEW_ARMATURE")
    round_rig = [obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj not in (source, body)][-1]
    round_actions = [action2 for action2 in bpy.data.actions if action2.name not in before_round]
    round_action = round_actions[-1] if round_actions else None
    round_rows = []
    if round_action is not None:
        round_rig.animation_data_create()
        round_rig.animation_data.action = round_action
        if getattr(round_action, "slots", None):
            round_rig.animation_data.action_slot = round_action.slots[0]
        for frame in frames:
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            for bone in round_rig.pose.bones:
                want = baked[frame].get(bone.name)
                if want is None:
                    continue
                got = bone.matrix
                round_rows.append({
                    "frame": frame,
                    "bone": bone.name,
                    "turn_deg": round(math.degrees(want.to_quaternion().rotation_difference(got.to_quaternion()).angle), 3),
                    "move": round((want.translation - got.translation).length, 4),
                })
    round_rows.sort(key=lambda row: -row["turn_deg"])
    report["written"] = {
        "path": str(written),
        "bytes": written.stat().st_size,
        "action": round_action.name if round_action else None,
        "frames": frames,
    }
    report["round_trip_worst"] = round_rows[:20]
    report["round_trip_worst_by_bone"] = {
        name: round(max(row["turn_deg"] for row in round_rows if row["bone"] == name), 3)
        for name in sorted({row["bone"] for row in round_rows})
    }
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"FIDELITY bones={report['bones_checked']} frames={frames}", flush=True)
    print(f"FIDELITY solver inputs rotated by root: {report['solver_input_root_offset']}", flush=True)
    for row in rows[:12]:
        print(f"FIDELITY {row['bone']:22s} f{row['frame']:<4} turn {row['turn_deg']:8.3f}  move {row['move']:.4f}", flush=True)
    print(f"ROUNDTRIP written {written.stat().st_size} bytes; worst {round_rows[:6]}", flush=True)
    for row in round_rows[:12]:
        print(f"ROUNDTRIP {row['bone']:22s} f{row['frame']:<4} turn {row['turn_deg']:8.3f}  move {row['move']:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
