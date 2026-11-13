"""Headless probe for the bone hierarchy list and the built LOD meshes.

Developer probe, not addon runtime. It builds a small rig and two meshes,
exercises the hierarchy reader and the LOD builder twice, and fails if either
one duplicates objects or drifts from the rig.

Run:
  blender -b --python tools/blender_skeleton_lods_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import addon_utils
import bpy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "blender"))
import hero_retarget_workbench as dmf  # noqa: E402


def _rig() -> bpy.types.Object:
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.object
    armature.name = "probe_hero"
    edit = armature.data.edit_bones
    root = edit[0]
    root.name = "root_motion"
    spine = edit.new("spine_0")
    spine.parent = root
    spine.head = (0.0, 0.0, 10.0)
    head = edit.new("head")
    head.parent = spine
    head.head = (0.0, 0.0, 18.0)
    twist = edit.new("neck_0_TWIST")
    twist.parent = spine
    twist.head = (0.0, 0.0, 16.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _cube(name: str, x: float, collection, armature) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=(x, 0.0, 10.0))
    obj = bpy.context.object
    obj.name = name
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = armature
    obj.parent = armature
    return obj


def _purge_probe(settings) -> None:
    """The export cleanup must remove what an export created and nothing else."""
    from hero_retarget_workbench import operators

    scene = bpy.context.scene
    objects_before = {obj.name for obj in bpy.data.objects}
    collections_before = {collection.name for collection in bpy.data.collections}
    scope = bpy.data.collections.new("DMF Export")
    scene.collection.children.link(scope)
    lod_collection = bpy.data.collections.new("DMF Export_lod1")
    scene.collection.children.link(lod_collection)
    duplicate = settings.target_armature.copy()
    duplicate.name = "probe_hero.001"
    scope.objects.link(duplicate)
    lod_collection.objects.link(duplicate)

    removed = operators._purge_export_leftovers(
        scene.name, "DMF Export", objects_before, collections_before
    )
    assert bpy.data.collections.get("DMF Export") is None, removed
    assert bpy.data.collections.get("DMF Export_lod1") is None, removed
    assert bpy.data.objects.get("probe_hero.001") is None, removed
    assert bpy.data.objects.get("probe_hero") is not None, "cleanup removed the user rig"
    assert len([obj for obj in bpy.data.objects if obj.type == "ARMATURE"]) == 1
    print(f"PURGE removed {len(removed)} datablocks; the user rig survived")


def main() -> int:
    addon_utils.enable("bl_ext.user_default.pulse_src_ops", default_set=False)
    dmf.register()

    armature = _rig()
    collection = bpy.data.collections.new("probe_parts")
    bpy.context.scene.collection.children.link(collection)
    _cube("part_a", 0.0, collection, armature)
    _cube("part_b", 3.0, collection, armature)

    settings = bpy.context.scene.dmf
    settings.target_armature = armature
    settings.custom_collection = collection
    settings.addon_name = "probe_addon"
    settings.lod_count = 3
    settings.lod_decimate = 25.0

    result = bpy.ops.dmf.refresh_hierarchy()
    assert "FINISHED" in result, result
    rows = list(settings.hierarchy)
    assert len(rows) == len(armature.data.bones), (len(rows), len(armature.data.bones))
    by_name = {row.name: row for row in rows}
    assert by_name["root_motion"].depth == 0, by_name["root_motion"].depth
    assert by_name["spine_0"].parent == "root_motion"
    assert by_name["spine_0"].depth == 1
    assert by_name["head"].parent == "spine_0"
    assert by_name["head"].depth == 2
    assert by_name["spine_0"].children == 2, by_name["spine_0"].children
    assert by_name["head"].children == 0
    print(f"HIERARCHY rows={len(rows)} head_depth={by_name['head'].depth} spine_children={by_name['spine_0'].children}")

    settings.hierarchy_index = [row.name for row in rows].index("head")
    result = bpy.ops.dmf.select_hierarchy_bone()
    assert "FINISHED" in result, result
    assert armature.data.bones.active.name == "head", armature.data.bones.active
    bpy.ops.object.mode_set(mode="EDIT")
    result = bpy.ops.dmf.select_hierarchy_bone()
    assert "FINISHED" in result, result
    chosen = [bone.name for bone in armature.data.edit_bones if bone.select]
    assert chosen == ["head"], chosen
    bpy.ops.object.mode_set(mode="OBJECT")
    print("HIERARCHY active bone and edit selection follow the row")

    result = bpy.ops.dmf.build_lods()
    assert "FINISHED" in result, result
    first = [(row.level, row.object.name, row.vertices) for row in settings.lod_levels]
    assert len(first) == 3, first
    assert settings.live_lods is True
    assert settings.lod_tick == settings.axis_tick, (settings.lod_tick, settings.axis_tick)
    for level, name, vertices in first:
        assert vertices > 0, (name, vertices)
        assert bpy.data.objects.get(name) is not None, name
    assert first[0][2] > first[2][2], first

    result = bpy.ops.dmf.build_lods()
    assert "FINISHED" in result, result
    second = {row.object.name for row in settings.lod_levels}
    assert len(second) == 3, second
    assert len(settings.lod_levels) == 3, len(settings.lod_levels)
    assert all(row.object is not None for row in settings.lod_levels)
    lod_meshes = [obj.name for obj in bpy.data.objects if obj.type == "MESH" and obj.name.startswith("DMF LOD")]
    assert len(lod_meshes) == 3, lod_meshes
    armatures = [obj.name for obj in bpy.data.objects if obj.type == "ARMATURE"]
    assert armatures == ["probe_hero"], armatures
    print(f"LODS rebuilt levels={sorted(second)} armatures={armatures}")

    result = bpy.ops.dmf.clear_lods()
    assert "FINISHED" in result, result
    assert len(settings.lod_levels) == 0
    assert not [obj for obj in bpy.data.objects if obj.name.startswith("DMF LOD")]
    print("LODS cleared")

    _purge_probe(settings)

    assert hasattr(bpy.types, "DMF_UL_hierarchy")
    assert hasattr(bpy.types, "DMF_OT_build_lods")
    assert hasattr(bpy.types, "DMF_OT_clear_lods")
    print("REGISTERED hierarchy list, build and clear operators")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
