"""Compare two DMX skeletons' rest pose, bone by bone.

If a clip is authored against one skeleton and the game resolves it against the
model's own skeleton, every bone whose rest orientation differs gets its
rotation applied in the wrong frame: the body can look right while one chain
(clavicles, arms, neck, head) is visibly twisted.  That is the shape of the
6:47 Shiv defect, so measure the rest difference instead of guessing which bone
is wrong.

  blender -b --python tools/skeleton_rest_diff_probe.py -- \
      --authored <shiv_tailbones.dmx> --model <shiv_body.dmx> --report <json>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Quaternion

REPO = Path(__file__).resolve().parents[1]
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--authored", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "skeleton-rest-diff.json"))
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


def _rest(path: str) -> dict[str, dict]:
    _clear()
    bpy.ops.import_scene.kst_dmx(filepath=path, append="NEW_ARMATURE")
    rig = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"][-1]
    out = {}
    for bone in rig.data.bones:
        local = bone.matrix_local
        out[bone.name] = {
            "quaternion": [round(value, 6) for value in local.to_quaternion()],
            "head": [round(value, 5) for value in local.translation],
            "parent": bone.parent.name if bone.parent is not None else None,
        }
    return out


def main() -> int:
    args = _arguments()
    _enable_pulse()
    authored = _rest(args.authored)
    model = _rest(args.model)
    shared = sorted(set(authored) & set(model))
    rows = []
    for name in shared:
        a, b = authored[name], model[name]
        # Quaternion difference between the two rest orientations.
        qa = Quaternion(a["quaternion"])
        qb = Quaternion(b["quaternion"])
        turn = math.degrees(qa.rotation_difference(qb).angle)
        head = math.dist(a["head"], b["head"])
        rows.append({"bone": name, "turn_deg": round(turn, 3), "head_delta": round(head, 4),
                     "parent_a": a["parent"], "parent_b": b["parent"]})
    rows.sort(key=lambda row: -row["turn_deg"])
    report = {
        "authored": {"path": args.authored, "bones": len(authored)},
        "model": {"path": args.model, "bones": len(model)},
        "only_authored": sorted(set(authored) - set(model)),
        "only_model": sorted(set(model) - set(authored)),
        "shared": len(shared),
        "worst_turns": rows[:25],
        "turn_over_1deg": [row["bone"] for row in rows if row["turn_deg"] > 1.0],
    }
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"REST shared={len(shared)} only_authored={len(report['only_authored'])} only_model={len(report['only_model'])}", flush=True)
    for row in rows[:15]:
        print(f"REST {row['bone']:24s} turn {row['turn_deg']:8.3f} deg  head {row['head_delta']:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
