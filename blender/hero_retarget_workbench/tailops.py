"""Experimental tail-armature blending for imported hero clips.

The hero clip already contains the tail's animation.  A custom model can carry
that tail on a separate armature, so this section samples each imported hero
action and writes the mapped tail channels onto the selected tail armature.  It
is deliberately separate from the body action and from the Cloth page: a tail
chain can be simulated as cloth while its animation is copied here.

This is a local-space transfer.  It is exact when the tail bones share the
hero's rest orientation and is labelled experimental for every other rig.
"""
from __future__ import annotations

import bpy
from bpy.types import Operator
from mathutils import Matrix

from forge import tails as tailscan

from . import core


def _rigs(settings):
    hero = settings.target_armature
    tail = settings.tail_armature
    if hero is None:
        raise RuntimeError("tail-needs-hero: import the hero skeleton first")
    if tail is None:
        raise RuntimeError("tail-needs-armature: choose the custom tail armature first")
    if tail == hero:
        raise RuntimeError("tail-is-hero: choose the separate tail armature, not the hero skeleton")
    return hero, tail


def scan(settings) -> int:
    hero, tail = _rigs(settings)
    rows = tailscan.candidates(
        [bone.name for bone in hero.data.bones],
        [bone.name for bone in tail.data.bones],
    )
    old = {row.source: row.target for row in settings.tail_bones if row.source and row.target}
    settings.tail_bones.clear()
    for item in rows:
        row = settings.tail_bones.add()
        row.source = item.source
        row.target = old.get(item.source, item.target)
        row.state = "MATCHED" if row.target and tail.data.bones.get(row.target) else (
            "CHOOSE" if not row.target else "MISSING"
        )
    settings.tail_index = 0
    settings.tail_scanned = len(rows)
    settings.tail_note = (
        f"{len(rows)} tail channels on {hero.name}; {sum(1 for row in settings.tail_bones if row.target)} "
        f"are paired with {tail.name}"
    )
    return len(rows)


def _pairs(settings) -> list[tuple[str, str]]:
    hero, tail = _rigs(settings)
    rows = []
    for row in settings.tail_bones:
        if not row.source or not row.target:
            continue
        if hero.data.bones.get(row.source) is None or tail.data.bones.get(row.target) is None:
            row.state = "MISSING"
            continue
        rows.append((row.source, row.target))
    return rows


def _blend_matrix(matrix: Matrix, weight: float) -> Matrix:
    if weight >= 1.0:
        return matrix.copy()
    location, rotation, scale = matrix.decompose()
    location = location * weight
    rotation = rotation.__class__((1.0, 0.0, 0.0, 0.0)).slerp(rotation, weight)
    scale = (1.0 + (scale.x - 1.0) * weight, 1.0 + (scale.y - 1.0) * weight, 1.0 + (scale.z - 1.0) * weight)
    return Matrix.LocRotScale(location, rotation, scale)


def _clear_action(action) -> None:
    """Remove old tail curves from a layered Blender 5.4 action."""
    for layer in list(getattr(action, "layers", [])):
        for strip in list(getattr(layer, "strips", [])):
            for bag in list(getattr(strip, "channelbags", [])):
                for curve in list(getattr(bag, "fcurves", [])):
                    bag.fcurves.remove(curve)


def blend(settings, row) -> dict:
    """Write one imported hero clip onto the tail armature as a new action."""
    hero, tail = _rigs(settings)
    pairs = _pairs(settings)
    if not pairs:
        raise RuntimeError("tail-no-pairs: pair at least one hero tail bone with a tail bone")
    source_action = None
    if row is not None:
        source_action = bpy.data.actions.get(row.action) if row.action else None
    if source_action is None:
        source_action = hero.animation_data.action if hero.animation_data else None
    if source_action is None:
        raise RuntimeError("tail-no-action: import a hero clip before blending it")
    start, end = (int(round(value)) for value in source_action.frame_range)
    if end <= start:
        raise RuntimeError("tail-empty-range: the hero action has no frame range")

    data = tail.animation_data or tail.animation_data_create()
    name = (row.label if row is not None else source_action.name) + "_tail"
    target_action = bpy.data.actions.get(name)
    if target_action is None:
        target_action = bpy.data.actions.new(name)
    else:
        _clear_action(target_action)
    data.action = target_action
    if hasattr(data, "action_slot") and getattr(target_action, "slots", None):
        data.action_slot = target_action.slots[0]

    scene = bpy.context.scene
    old_action = hero.animation_data.action if hero.animation_data else None
    old_frame = scene.frame_current
    try:
        if hero.animation_data is not None:
            hero.animation_data.action = source_action
            if hasattr(hero.animation_data, "action_slot") and getattr(source_action, "slots", None):
                hero.animation_data.action_slot = source_action.slots[0]
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            for source_name, target_name in pairs:
                source_bone = hero.pose.bones.get(source_name)
                target_bone = tail.pose.bones.get(target_name)
                if source_bone is None or target_bone is None:
                    continue
                target_bone.rotation_mode = source_bone.rotation_mode
                target_bone.matrix_basis = _blend_matrix(source_bone.matrix_basis.copy(), settings.tail_weight)
                target_bone.keyframe_insert("location", frame=frame, group=target_name)
                if target_bone.rotation_mode == "QUATERNION":
                    target_bone.keyframe_insert("rotation_quaternion", frame=frame, group=target_name)
                elif target_bone.rotation_mode == "AXIS_ANGLE":
                    target_bone.keyframe_insert("rotation_axis_angle", frame=frame, group=target_name)
                else:
                    target_bone.keyframe_insert("rotation_euler", frame=frame, group=target_name)
                target_bone.keyframe_insert("scale", frame=frame, group=target_name)
    finally:
        if hero.animation_data is not None:
            hero.animation_data.action = old_action
        scene.frame_set(old_frame)
    if row is not None:
        row.tail_action = target_action.name
    settings.tail_note = (
        f"{target_action.name}: {end - start + 1} frames from {source_action.name} onto "
        f"{tail.name} ({len(pairs)} bones, blend {settings.tail_weight:.2f})"
    )
    return {
        "action": target_action.name,
        "frames": end - start + 1,
        "bones": len(pairs),
        "tail": tail.name,
    }


class DMF_OT_scan_tail(Operator):
    bl_idname = "dmf.scan_tail"
    bl_label = "Find Tail Bones"
    bl_description = "Pair the hero's tail channels with bones on the selected tail armature (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = scan(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, settings.tail_note or f"{count} tail channels", "OK" if count else "WARN")
        return {"FINISHED"}


class DMF_OT_blend_tail(Operator):
    bl_idname = "dmf.blend_tail"
    bl_label = "Blend Tail"
    bl_description = "Write the selected hero clip's tail channels onto the tail armature (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        row = settings.clips[settings.clip_index] if settings.clips else None
        try:
            result = blend(settings, row)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, settings.tail_note, "OK")
        self.report({"INFO"}, f"Wrote {result['frames']} frames onto {result['tail']}")
        return {"FINISHED"}


class DMF_OT_blend_tail_all(Operator):
    bl_idname = "dmf.blend_tail_all"
    bl_label = "Blend All Tails"
    bl_description = "Write every imported hero clip's tail channels onto the tail armature (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        rows = [row for row in settings.clips if row.action and row.state in ("IMPORTED", "WRITTEN")]
        if not rows:
            core.set_status(settings, "Import a clip before blending tails", "WARN")
            return {"CANCELLED"}
        failed = 0
        written = 0
        for row in rows:
            try:
                blend(settings, row)
                written += 1
            except Exception as error:
                failed += 1
                settings.tail_note = f"{row.label}: {error}"
        core.set_status(
            settings,
            f"Wrote tail actions for {written} clips" + (f"; {failed} failed" if failed else ""),
            "OK" if not failed else "WARN",
        )
        return {"FINISHED"}


CLASSES = (DMF_OT_scan_tail, DMF_OT_blend_tail, DMF_OT_blend_tail_all)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)