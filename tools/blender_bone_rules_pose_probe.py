"""Headless probe for rule-based mapping, the ref-pose preview and part naming.

  blender -b --factory-startup --python tools/blender_bone_rules_pose_probe.py -- \
    --report artifacts/receipts/bone-rules-pose.json

The probe builds a T-posed source rig and an A-posed hero rig, maps one row,
and checks the four claims the panels make: typing one target answers its
mirror, rules fill the rest, the preview puts the source bones on the hero's
rest orientation without editing the rest pose, and an import does not inherit
the previous rig's names. It does not import an animation clip: PulseSrcOps is
not enabled under --factory-startup, so that path is checked by the sidebar
rebuild in the zip probe, not here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
_spec = importlib.util.spec_from_file_location(
    "dmf_rules_probe",
    PACKAGE / "__init__.py",
    submodule_search_locations=[str(PACKAGE)],
)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"could not load checkout addon: {PACKAGE}")
dmf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dmf
_spec.loader.exec_module(dmf)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="artifacts/receipts/bone-rules-pose.json")
    return parser.parse_args(argv)


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def armature(name: str, bones: list[tuple[str, tuple[float, float, float], tuple[float, float, float], str | None]]):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, head, tail, parent in bones:
        edit = data.edit_bones.new(bone_name)
        edit.head = head
        edit.tail = tail
        if parent:
            edit.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def rotation_error(a, b) -> float:
    """Largest per-element difference between two 3x3 matrices."""
    return max(abs(a[r][c] - b[r][c]) for r in range(3) for c in range(3))


def main() -> int:
    args = parse_args()
    dmf.register()
    clear_scene()
    settings = bpy.context.scene.dmf

    # A source rig in a T-pose: every arm segment points straight out on X.
    source = armature(
        "gold_ship_rig",
        [
            ("pelvis", (0.0, 0.0, 1.0), (0.0, 0.0, 1.2), None),
            ("elbow_L", (0.4, 0.0, 1.4), (0.8, 0.0, 1.4), "pelvis"),
            ("elbow_R", (-0.4, 0.0, 1.4), (-0.8, 0.0, 1.4), "pelvis"),
            ("shoulder_L", (0.1, 0.0, 1.45), (0.4, 0.0, 1.45), "pelvis"),
            ("shoulder_R", (-0.1, 0.0, 1.45), (-0.4, 0.0, 1.45), "pelvis"),
            ("Sp_Hi_Mskirt0_B_00", (0.0, 0.05, 1.1), (0.0, 0.1, 1.0), "pelvis"),
            ("Sp_Hi_Mskirt0_B_01", (0.0, -0.05, 1.1), (0.0, -0.1, 1.0), "pelvis"),
        ],
    )
    # The hero rig rests in an A-pose: its arms are already lowered.
    hero = armature(
        "shiv_body",
        [
            ("pelvis", (0.0, 0.0, 1.0), (0.0, 0.0, 1.2), None),
            ("arm_lower_L", (0.4, 0.0, 1.2), (0.6, 0.0, 0.9), "pelvis"),
            ("arm_lower_R", (-0.4, 0.0, 1.2), (-0.6, 0.0, 0.9), "pelvis"),
            ("arm_upper_L", (0.1, 0.0, 1.5), (0.3, 0.0, 1.35), "pelvis"),
            ("arm_upper_R", (-0.1, 0.0, 1.5), (-0.3, 0.0, 1.35), "pelvis"),
        ],
    )

    settings.target_armature = hero
    settings.custom_armature = source
    settings.target_body = None
    settings.bone_filter = "ALL"

    checks: dict[str, object] = {}

    # --- the map itself -------------------------------------------------
    count = dmf.workbench.scan_bone_map(settings)
    checks["scan_rows"] = count
    rows = {entry.source: entry for entry in settings.bone_map}
    assert set(rows) == {
        "pelvis",
        "elbow_L",
        "elbow_R",
        "shoulder_L",
        "shoulder_R",
        "Sp_Hi_Mskirt0_B_00",
        "Sp_Hi_Mskirt0_B_01",
    }, rows

    # --- typing one target answers its mirror ---------------------------
    rows["elbow_L"].state = "MAPPED"
    rows["elbow_L"].target = "arm_lower_L"
    checks["mirror_target"] = rows["elbow_R"].target
    checks["mirror_note"] = rows["elbow_R"].note
    checks["mirror_state"] = rows["elbow_R"].state
    assert rows["elbow_R"].target == "arm_lower_R", checks["mirror_target"]
    assert rows["elbow_R"].state == "MAPPED"
    checks["rules_learned"] = [f"{row.source}->{row.target}" for row in settings.bone_rules]
    assert any(row.source == "elbow" for row in settings.bone_rules), checks["rules_learned"]

    # --- rules the user writes by hand, applied by the button -----------
    shoulder_rule = settings.bone_rules.add()
    shoulder_rule.source = "shoulder"
    shoulder_rule.target = "arm_upper_L"
    shoulder_rule.side_aware = True
    shoulder_rule.state = "MAPPED"
    shoulder_rule.origin = "user"
    skirt_rule = settings.bone_rules.add()
    skirt_rule.source = "Sp_Hi_Mskirt*"
    skirt_rule.target = ""
    skirt_rule.state = "EXTRA"
    skirt_rule.side_aware = False
    skirt_rule.origin = "user"

    filled = dmf.rules.fill(settings)
    checks["filled"] = filled
    checks["shoulder_L"] = rows["shoulder_L"].target
    checks["shoulder_R"] = rows["shoulder_R"].target
    checks["skirt_states"] = {name: rows[name].state for name in ("Sp_Hi_Mskirt0_B_00", "Sp_Hi_Mskirt0_B_01")}
    checks["rule_kinds"] = [dmf.rules.rule_of(row).kind for row in settings.bone_rules]
    assert rows["shoulder_L"].target == "arm_upper_L", checks["shoulder_L"]
    assert rows["shoulder_R"].target == "arm_upper_R", checks["shoulder_R"]
    assert checks["skirt_states"] == {
        "Sp_Hi_Mskirt0_B_00": "EXTRA",
        "Sp_Hi_Mskirt0_B_01": "EXTRA",
    }, checks["skirt_states"]

    # --- scan applies the rules, and keeps what the user chose ----------
    rows["Sp_Hi_Mskirt0_B_00"].state = "IGNORED"
    rows["Sp_Hi_Mskirt0_B_00"].target = ""
    rows["elbow_L"].target = "arm_lower_L"
    scanned_again = dmf.workbench.scan_bone_map(settings)
    again = {entry.source: entry for entry in settings.bone_map}
    checks["rescan_rows"] = scanned_again
    checks["rescan_shoulder"] = (again["shoulder_L"].state, again["shoulder_L"].target)
    checks["rescan_skirt_01"] = (again["Sp_Hi_Mskirt0_B_01"].state, again["Sp_Hi_Mskirt0_B_01"].note)
    checks["rescan_skirt_00"] = (again["Sp_Hi_Mskirt0_B_00"].state, again["Sp_Hi_Mskirt0_B_00"].target)
    checks["rescan_mirror"] = (again["elbow_R"].state, again["elbow_R"].target)
    checks["rescan_pelvis"] = (again["pelvis"].state, again["pelvis"].target)
    assert checks["rescan_shoulder"] == ("MAPPED", "arm_upper_L"), checks["rescan_shoulder"]
    assert checks["rescan_skirt_01"][0] == "EXTRA", checks["rescan_skirt_01"]
    assert checks["rescan_skirt_00"] == ("IGNORED", ""), checks["rescan_skirt_00"]
    assert checks["rescan_mirror"] == ("MAPPED", "arm_lower_R"), checks["rescan_mirror"]
    assert checks["rescan_pelvis"] == ("MAPPED", "pelvis"), checks["rescan_pelvis"]
    rows = again

    # --- stance: the source is level, the hero is lowered ---------------
    checks["source_stance"] = dmf.poseview.stance(settings)
    saved = settings.custom_armature
    settings.custom_armature = hero
    hero_stance = dmf.poseview.stance(settings)
    settings.custom_armature = saved
    checks["hero_stance"] = hero_stance
    assert checks["source_stance"][0] == "T", checks["source_stance"]
    assert hero_stance[0] == "A", hero_stance

    # --- the preview puts the source on the hero's rest orientation -----
    settings.pose_preview = True
    assert not settings.pose_preview_error, settings.pose_preview_error
    errors = {}
    for entry in settings.bone_map:
        if not entry.target:
            continue
        pose_bone = source.pose.bones.get(entry.source)
        hero_bone = hero.data.bones.get(entry.target)
        if pose_bone is None or hero_bone is None:
            continue
        errors[entry.source] = round(rotation_error(pose_bone.matrix.to_3x3(), hero_bone.matrix_local.to_3x3()), 6)
    checks["pose_rotation_errors"] = errors
    worst = max(errors.values()) if errors else 0.0
    checks["pose_worst_error"] = worst
    assert worst < 1e-4, errors

    rest_heads = {bone.name: tuple(bone.head_local) for bone in source.data.bones}
    moved_heads = {
        bone.name: tuple(round(value, 6) for value in source.pose.bones[bone.name].matrix.translation)
        for bone in source.data.bones
    }
    checks["heads_kept"] = all(
        all(abs(a - b) < 1e-5 for a, b in zip(rest_heads[name], moved_heads[name]))
        for name in rest_heads
    )
    assert checks["heads_kept"]

    cleared = dmf.poseview.clear(settings)
    checks["cleared_bones"] = cleared
    identity = max(
        abs(source.pose.bones[bone.name].matrix_basis[r][c] - (1.0 if r == c else 0.0))
        for bone in source.data.bones
        for r in range(3)
        for c in range(3)
    )
    checks["clear_worst_error"] = round(identity, 6)
    assert identity < 1e-6, identity
    settings.pose_preview = False

    # --- an import does not inherit the previous rig's names ------------
    for index, name in enumerate(("shiv_body", "shiv_head", "shiv_hair")):
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
    imported = [bpy.data.objects[name] for name in ("shiv_body", "shiv_head", "shiv_hair")]
    collection = dmf.parts.capture_import(
        bpy.context,
        Path("C:/models/Gold_Ship.glb"),
        imported,
        dmf.parts.stale_prefixes(settings),
    )
    checks["import_collection"] = collection.name
    checks["import_parts"] = sorted(obj.name for obj in imported)
    assert collection.name == "DMF Gold_Ship", collection.name
    assert checks["import_parts"] == ["body", "hair", "head"], checks["import_parts"]

    settings.custom_collection = collection
    settings.custom_name = ""
    settings.custom_name = "Gold_Ship"
    named = dmf.parts.name_model(settings)
    checks["name_model"] = named
    assert collection.name == "DMF Gold_Ship"

    report = {
        "result": "pass",
        "checks": checks,
        "version": ".".join(str(part) for part in dmf.bl_info["version"]),
        "panels": len([name for name in dir(bpy.types) if name.startswith("DMF_PT_")]),
        "not_covered": "no animation clip import: PulseSrcOps is disabled under --factory-startup",
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print("BONE-RULES-POSE", json.dumps({k: report[k] for k in ("result", "checks")}, sort_keys=True))
    dmf.unregister()
    return 0


if __name__ == "__main__":
    # Blender exits 0 when a --python script raises, unless the script says
    # otherwise: a failed assertion has to fail the probe, not look like a pass.
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
