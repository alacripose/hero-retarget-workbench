"""Measure how far the tail reaches from its base, per frame, in a merged clip.

The visible question the tail comparison asks is "is the tail attached and where
does it go", which no channel diff answers: a folded tail and an extended tail
have identical channel counts.  This walks a clip's frames on the authoring rig
and reports, in world units, the tail base (tail_0 head), the tip (tail_end head
or the last tail bone's tail), their separation, and the base's distance from
pelvis -- a tail that has come off the body shows up as a base far from pelvis,
and a tail folded into the torso shows up as a small base-to-tip separation
against a large chain length.

  blender -b --python tools/tail_extent_probe.py -- --mesh <mesh.dmx> \
      --clip <merged.dmx> [--clip ...] --report <json>
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

REPO = Path(__file__).resolve().parents[1]
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")
TAIL = ["tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5"]


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--clip", action="append", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "tail-extent.json"))
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


def _rig(mesh: Path):
    bpy.ops.import_scene.kst_dmx(filepath=str(mesh), append="NEW_ARMATURE")
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not rigs:
        raise RuntimeError(f"no armature in {mesh}")
    return rigs[-1]


def _apply(path: Path, rig):
    rig.animation_data_create()
    rig.animation_data.action = None
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    before = {action.name for action in bpy.data.actions}
    objects = set(bpy.context.scene.objects)
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    for obj in [obj for obj in bpy.context.scene.objects if obj not in objects]:
        bpy.data.objects.remove(obj, do_unlink=True)
    if not created:
        raise RuntimeError(f"no action from {path}")
    action = created[-1]
    rig.animation_data.action = action
    if getattr(action, "slots", None):
        rig.animation_data.action_slot = action.slots[0]
    return action


def _world_head(rig, name: str) -> Vector | None:
    bone = rig.pose.bones.get(name)
    if bone is None:
        return None
    return rig.matrix_world @ bone.head


def main() -> int:
    args = _arguments()
    _enable_pulse()
    report: dict[str, object] = {"mesh": args.mesh, "clips": {}, "failed": []}
    target = Path(args.report)

    def write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for clip in args.clip:
        name = Path(clip).stem
        try:
            _clear()
            rig = _rig(Path(args.mesh))
            action = _apply(Path(clip), rig)
            start, end = (int(round(value)) for value in action.frame_range)
            scene = bpy.context.scene
            rows = []
            for frame in range(start, end + 1):
                scene.frame_set(frame)
                bpy.context.view_layer.update()
                base = _world_head(rig, "tail_0")
                tip = _world_head(rig, "tail_end") or _world_head(rig, "tail_5")
                pelvis = _world_head(rig, "pelvis")
                if base is None or tip is None:
                    raise RuntimeError("tail-bones-missing")
                reach = (tip - base).length
                anchor = (base - pelvis).length if pelvis is not None else None
                rows.append(
                    {
                        "frame": frame,
                        "reach": round(reach, 3),
                        "anchor": round(anchor, 3) if anchor is not None else None,
                        "base": [round(v, 2) for v in base],
                        "tip": [round(v, 2) for v in tip],
                    }
                )
            best = max(rows, key=lambda row: row["reach"])
            anchors = [row["anchor"] for row in rows if row["anchor"] is not None]
            report["clips"][name] = {
                "frames": len(rows),
                "best": best,
                "reach_min": min(row["reach"] for row in rows),
                "reach_max": best["reach"],
                "anchor_min": min(anchors) if anchors else None,
                "anchor_max": max(anchors) if anchors else None,
            }
            print(
                f"TAIL-EXTENT {name}: frames {len(rows)}, reach {min(r['reach'] for r in rows):.2f}"
                f"..{best['reach']:.2f} at frame {best['frame']}, anchor "
                f"{(min(anchors) if anchors else 0):.2f}..{(max(anchors) if anchors else 0):.2f}",
                flush=True,
            )
        except Exception as error:
            report["failed"].append({"clip": name, "why": f"{type(error).__name__}: {error}"})
            print(f"TAIL-EXTENT FAIL {name}: {error}", flush=True)
        write()
    return 0 if report["clips"] and not report["failed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
