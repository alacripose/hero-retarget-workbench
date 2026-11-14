"""Headless probe for custom-rig cloth chains and experimental tail blending.

Builds a hero armature, a differently scaled/placed custom armature and a custom
mesh, then exercises the same operators the Cloth and Animations pages call.
It does not need PulseSrcOps and it never parses a vmdl.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "blender"))
import hero_retarget_workbench as addon  # noqa: E402
from hero_retarget_workbench import clipops  # noqa: E402


def _check(report, name, ok, observed):
    report["checks"][name] = {"pass": bool(ok), "observed": observed}
    if not ok:
        report["failed"].append(name)
    print(f"CUSTOMPROBE {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)


def _armature(name, location, scale):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    obj.scale = scale
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _bone(armature, name, head, tail, parent=""):
    bpy.context.view_layer.objects.active = armature
    if armature.mode != "EDIT":
        bpy.ops.object.mode_set(mode="EDIT")
    item = armature.data.edit_bones.get(name) or armature.data.edit_bones.new(name)
    item.head = head
    item.tail = tail
    if parent:
        item.parent = armature.data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")


def _curves(action) -> int:
    if action is None:
        return 0
    total = 0
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                total += len(getattr(bag, "fcurves", []))
    return total


def main() -> int:
    addon.register()
    settings = bpy.context.scene.dmf
    report = {"checks": {}, "failed": []}

    hero = _armature("Hero", (2.0, 0.0, 0.0), (2.0, 2.0, 2.0))
    _bone(hero, "pelvis", (0.0, 0.0, 0.9), (0.0, 0.0, 1.1))
    _bone(hero, "tail_01", (0.0, 0.2, 0.9), (0.0, 0.4, 0.9), "pelvis")
    _bone(hero, "tail_02", (0.0, 0.4, 0.9), (0.0, 0.6, 0.9), "tail_01")

    custom = _armature("CustomRig", (5.0, 0.0, 3.0), (0.5, 0.5, 0.5))
    custom.rotation_euler = (0.0, 0.0, 0.4)
    _bone(custom, "pelvis", (0.0, 0.0, 0.9), (0.0, 0.0, 1.1))
    _bone(custom, "custom_tail_01", (0.0, 0.2, 0.9), (0.0, 0.4, 0.9), "pelvis")
    _bone(custom, "custom_tail_02", (0.0, 0.4, 0.9), (0.0, 0.6, 0.9), "custom_tail_01")

    mesh_data = bpy.data.meshes.new("CustomTailMesh")
    mesh = bpy.data.objects.new("CustomTailMesh", mesh_data)
    bpy.context.scene.collection.objects.link(mesh)
    mesh_data.from_pydata([(0, 0, 0), (0, 1, 0), (1, 1, 0)], [], [(0, 1, 2)])
    mesh_data.update()
    for name in ("custom_tail_01", "custom_tail_02"):
        group = mesh.vertex_groups.new(name=name)
        group.add([0, 1], 1.0, "REPLACE")

    settings.target_armature = hero
    settings.custom_armature = custom
    settings.custom_mesh = mesh
    settings.cloth_source = "CUSTOM"

    scanned = bpy.ops.dmf.scan_cloth()
    row = next((item for item in settings.cloth_chains if item.name == "custom_tail"), None)
    _check(report, "scan-custom-chain", scanned == {"FINISHED"} and row is not None and row.count == 2, {"result": str(scanned), "chain": row.name if row else ""})

    joined = bpy.ops.dmf.join_cloth_chain()
    hero_world = hero.matrix_world @ hero.data.bones["custom_tail_01"].head_local
    custom_world = custom.matrix_world @ custom.data.bones["custom_tail_01"].head_local
    difference = (hero_world - custom_world).length
    parent_ok = hero.data.bones["custom_tail_01"].parent is not None and hero.data.bones["custom_tail_01"].parent.name == "pelvis"
    child_ok = hero.data.bones["custom_tail_02"].parent is not None and hero.data.bones["custom_tail_02"].parent.name == "custom_tail_01"
    source_axis = (custom.matrix_world.to_3x3() @ custom.data.bones["custom_tail_01"].matrix_local.to_3x3()).col[0].normalized()
    joined_axis = (hero.matrix_world.to_3x3() @ hero.data.bones["custom_tail_01"].matrix_local.to_3x3()).col[0].normalized()
    roll_dot = source_axis.dot(joined_axis)
    _check(
        report,
        "join-preserves-world-position-and-parent",
        joined == {"FINISHED"} and difference < 1e-4 and parent_ok and child_ok and roll_dot > 0.999,
        {"result": str(joined), "difference": difference, "parent": parent_ok, "child": child_ok, "roll_dot": roll_dot},
    )

    built = bpy.ops.dmf.build_chain_cloth()
    modifier = next((item for item in mesh.modifiers if item.type == "CLOTH"), None)
    armature_modifier = next((item for item in mesh.modifiers if item.type == "ARMATURE" and item.object is hero), None)
    _check(
        report,
        "build-cloth-on-custom-mesh",
        built == {"FINISHED"} and modifier is not None and armature_modifier is not None and row.target_mesh == mesh,
        {"result": str(built), "cloth": modifier.name if modifier else "", "bound": armature_modifier is not None},
    )

    tail = _armature("CustomTailRig", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    _bone(tail, "tail_01", (0.0, 0.2, 0.9), (0.0, 0.4, 0.9))
    _bone(tail, "tail_02", (0.0, 0.4, 0.9), (0.0, 0.6, 0.9), "tail_01")
    settings.tail_armature = tail
    hero.animation_data_create()
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 5
    pose = hero.pose.bones["tail_01"]
    pose.rotation_mode = "QUATERNION"
    pose.rotation_quaternion = (1, 0, 0, 0)
    pose.keyframe_insert("rotation_quaternion", frame=1)
    pose.rotation_quaternion = (0.9, 0.1, 0.0, 0.0)
    pose.keyframe_insert("rotation_quaternion", frame=5)
    action = hero.animation_data.action
    action.name = "tail_walk"
    clip = settings.clips.add()
    clip.label = "tail_walk"
    clip.action = action.name
    baked = clipops.bake_action(settings, clip)
    _check(
        report,
        "bake-action",
        baked["frames"] == 5 and _curves(action) > 0,
        {"frames": baked["frames"], "curves": _curves(action)},
    )
    tail_scan = bpy.ops.dmf.scan_tail()
    blended = bpy.ops.dmf.blend_tail()
    tail_action = bpy.data.actions.get("tail_walk_tail")
    curves = _curves(tail_action)
    _check(
        report,
        "tail-blend-writes-action",
        tail_scan == {"FINISHED"} and blended == {"FINISHED"} and tail_action is not None and curves > 0,
        {"scan": str(tail_scan), "blend": str(blended), "action": tail_action.name if tail_action else "", "curves": curves},
    )

    Path(REPO / "artifacts" / "receipts").mkdir(parents=True, exist_ok=True)
    (REPO / "artifacts" / "receipts" / "custom-chain-tail.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2), flush=True)
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())