"""Re-parent the clip rig's pelvis under root_motion, then write the clip back.

The stock clips declare ``pelvis`` as a child of ``root_motion``; our merged
clips declare it as a root bone, because the model rig the merge authors on has
no such parent.  A compiled clip therefore puts every pelvis-relative channel in
a different space than the skeleton the game plays it on -- measured as a rigid
(x,y,z)->(y,z,-x) rotation of the whole pose, which is the lift, the tilt when he
looks up, the horizontal slides and the wrong tail angle the owner reports.

This probe takes an already merged clip, restores the parent link without moving
the pelvis rest position, writes the clip back through the workbench exporter,
and reports the rest heads so the change can be shown to be a parent link and
nothing else.

  blender -b --python tools/shiv_pelvis_parent_probe.py -- \
      --skeleton <shiv_tailbones.dmx> --clip <merged.dmx> --out <dir> --report <json>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
PULSE_MODULES = ("bl_ext.user_default.pulse_src_ops", "pulse_src_ops")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--parent", default="root_motion")
    parser.add_argument("--child", default="pelvis")
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-pelvis-parent.json"))
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
        if module == "dmf_pelvis_probe" or not module.endswith("hero_retarget_workbench"):
            continue
        try:
            bpy.ops.preferences.addon_disable(module=module)
            disabled.append(module)
        except RuntimeError:
            continue
    return disabled


def _unshadow_forge() -> None:
    for entry in list(sys.path):
        if Path(str(entry)).name == "hero_retarget_workbench":
            sys.path.remove(entry)
    for name in [name for name in sys.modules if name == "forge" or name.startswith("forge.")]:
        if "hero_retarget_workbench" in str(getattr(sys.modules[name], "__file__", "") or ""):
            del sys.modules[name]
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_pelvis_probe", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_pelvis_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def _rest_heads(rig) -> dict[str, list[float]]:
    return {
        bone.name: [round(value, 3) for value in bone.matrix_local.translation]
        for bone in rig.data.bones
        if bone.name in ("pelvis", "root_motion", "spine_0", "head", "tail_0", "tail_end")
    }


def _reparent(rig, child: str, parent: str) -> dict[str, object]:
    before = _rest_heads(rig)
    bone = rig.data.bones.get(child)
    ancestor = rig.data.bones.get(parent)
    if bone is None or ancestor is None:
        raise RuntimeError(f"pelvis-parent-missing: {child} or {parent} not on this rig")
    was = bone.parent.name if bone.parent else None
    want = ancestor if not ancestor.parent else ancestor
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        edit_child = rig.data.edit_bones[child]
        matrix = edit_child.matrix.copy()
        edit_child.parent = rig.data.edit_bones[parent]
        edit_child.use_connect = False
        edit_child.matrix = matrix
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    after = _rest_heads(rig)
    return {
        "child": child,
        "parent": parent,
        "was": was,
        "now": rig.data.bones[child].parent.name if rig.data.bones[child].parent else None,
        "rest_before": before,
        "rest_after": after,
        "rest_moved": [name for name in before if before[name] != after.get(name)],
    }


def main() -> int:
    args = _arguments()
    report: dict[str, object] = {"pulse": _enable_pulse(), "disabled_installed": _disable_installed_addon()}
    _unshadow_forge()
    _load_addon()
    tailops = sys.modules["dmf_pelvis_probe.clipops"]

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)

    scene = bpy.context.scene
    scene.render.fps = 30
    bpy.ops.import_scene.kst_dmx(filepath=args.skeleton, append="NEW_ARMATURE")
    rig = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"][-1]

    before = {action.name for action in bpy.data.actions}
    bpy.ops.import_scene.kst_dmx(filepath=args.clip, append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    for obj in [obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj is not rig]:
        bpy.data.objects.remove(obj, do_unlink=True)
    if not created:
        raise RuntimeError("clip-no-action")
    action = created[-1]
    rig.animation_data_create()
    rig.animation_data.action = action
    if getattr(action, "slots", None):
        rig.animation_data.action_slot = action.slots[0]

    report["reparent"] = _reparent(rig, args.child, args.parent)
    report["clip"] = {"path": args.clip, "action": action.name, "frames": list(action.frame_range)}

    settings = scene.dmf
    settings.target_armature = rig
    row = settings.clips.add()
    row.name = "reparented.dmx"
    row.label = "reparented"
    row.kind = "dmx"
    row.action = action.name
    row.state = "IMPORTED"
    row.ag = "AG2"

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = tailops.write_action(settings, row, out, target=out / Path(args.clip).name)
    report["written"] = {"path": str(target), "bytes": target.stat().st_size}

    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"PELVIS-PARENT {args.child}: {report['reparent']['was']} -> {report['reparent']['now']}, "
        f"rest moved {report['reparent']['rest_moved']}, wrote {target.stat().st_size} b",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
