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

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import bpy
from bpy.types import Operator
from mathutils import Matrix

from forge import animgraph, live, tails as tailscan
from forge import tailimage

from . import clipops, core, jobs, source2

_AUTO_QUEUE: list[int] = []
_AUTO_TIMER = None
_AUTO_SOURCE = ""
_AUTO_SETTINGS = None
_AUTO_CLIPS: dict[str, object] = {}
_AUTO_SOURCE_ACTIONS: dict[str, object] = {}
_AUTO_UPDATED = 0
_AUTO_SKIPPED = 0
_AUTO_FAILED = 0
_AUTO_TAIL_NAMES: list[str] = []
_AUTO_PUBLISH = False
_SCAN_TIMER = None


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


def _chains(armature) -> list[tailscan.TailChain]:
    return tailscan.chains([bone.name for bone in armature.data.bones])


def _tail_names(armature) -> list[str]:
    names: list[str] = []
    for chain in _chains(armature):
        names.extend(chain.bones)
    return list(dict.fromkeys(names))


def _copy_tail_bones(settings, source) -> dict:
    """Append the source tail's rest bones to the hero skeleton.

    A model without a tail has no hero channel to sample into.  The selected
    tail source contributes its rest chain, parented to the nearest hero bone
    (or the source's own parent when that bone exists on the hero).  Existing
    hero bones are never moved or renamed, so re-running this is idempotent.
    """
    from . import cloth_ops

    hero = settings.target_armature
    if hero is None:
        raise RuntimeError("tail-needs-hero: import the hero skeleton first")
    if source == hero:
        return {"copied": 0, "existing": len(_tail_names(hero)), "parent": ""}
    chains = _chains(source)
    if not chains:
        raise RuntimeError(f"tail-source-no-tail: {source.name} has no tail bones")
    copied: list[str] = []
    existing: list[str] = []
    parents: list[str] = []
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    old_mode = hero.mode
    try:
        core.select_only(bpy.context, [hero])
        bpy.context.view_layer.objects.active = hero
        if hero.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = hero.data.edit_bones
        origin = hero.matrix_world.inverted()
        for chain in chains:
            names = list(chain.bones)
            source_bones = {name: source.data.bones.get(name) for name in names}
            missing_source = [name for name, bone in source_bones.items() if bone is None]
            if missing_source:
                raise RuntimeError(f"tail-source-bone-missing: {missing_source[0]} is not on {source.name}")
            parent = ""
            root = source_bones[names[0]]
            if root.parent is not None and hero.data.bones.get(root.parent.name) is not None:
                if root.parent.name not in chain.bones:
                    parent = root.parent.name
            if not parent:
                parent = cloth_ops._nearest_parent(hero, source, names[0], set(names))
            if parent:
                parents.append(parent)
            previous = None
            for index, name in enumerate(names):
                source_bone = source_bones[name]
                edit = edit_bones.get(name)
                if edit is None:
                    edit = edit_bones.new(name)
                    edit.head = origin @ (source.matrix_world @ source_bone.head_local)
                    edit.tail = origin @ (source.matrix_world @ source_bone.tail_local)
                    try:
                        rest = origin @ source.matrix_world @ source_bone.matrix_local
                        edit.roll = bpy.types.Bone.AxisRollFromMatrix(rest.to_3x3())[1]
                    except (AttributeError, TypeError, ValueError):
                        pass
                    edit.use_deform = True
                    copied.append(name)
                else:
                    existing.append(name)
                if index == 0 and name in copied and parent and edit_bones.get(parent) is not None:
                    edit.parent = edit_bones.get(parent)
                    edit.use_connect = False
                elif index > 0 and name in copied and previous is not None:
                    edit.parent = edit_bones.get(previous)
                    edit.use_connect = bool(
                        edit.parent is not None and (edit.parent.tail - edit.head).length < 1e-4
                    )
                previous = name
    finally:
        current = bpy.data.objects.get(hero.name) or hero
        if current.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        core.select_only(bpy.context, selected)
        if active is not None:
            bpy.context.view_layer.objects.active = active
        elif old_mode == "OBJECT":
            bpy.context.view_layer.objects.active = None
    bpy.context.view_layer.update()
    settings.tail_note = (
        f"Added {len(copied)} {source.name} tail bones to {hero.name}"
        + (f" under {parents[0]}" if parents else "")
        + (f"; {len(existing)} already existed" if existing else "")
    )
    return {"copied": len(copied), "existing": len(existing), "parent": parents[0] if parents else ""}


def _action_curves(action):
    """Every fcurve in a legacy or layered Blender action."""
    seen = set()
    for curve in getattr(action, "fcurves", ()):
        key = (getattr(curve, "data_path", ""), getattr(curve, "array_index", -1))
        if key not in seen:
            seen.add(key)
            yield curve
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for bag in getattr(strip, "channelbags", ()):
                for curve in getattr(bag, "fcurves", ()):
                    key = (getattr(curve, "data_path", ""), getattr(curve, "array_index", -1))
                    if key not in seen:
                        seen.add(key)
                        yield curve


def _action_bones(action) -> set[str]:
    names: set[str] = set()
    for curve in _action_curves(action):
        match = re.match(r'pose\.bones\["([^"]+)"\]', getattr(curve, "data_path", ""))
        if match:
            names.add(match.group(1))
    return names


def _clear_tail_curves(action, names: set[str]) -> None:
    """Remove old curves for just these tail bones, leaving the body intact."""
    paths = {f'pose.bones["{name}"]' for name in names}
    for curve in list(_action_curves(action)):
        if not any(getattr(curve, "data_path", "").startswith(path) for path in paths):
            continue
        owner = getattr(curve, "id_data", None)
        collection = getattr(owner, "fcurves", None)
        try:
            collection.remove(curve)
            continue
        except (AttributeError, ReferenceError, RuntimeError):
            pass
        for layer in getattr(action, "layers", ()):
            for strip in getattr(layer, "strips", ()):
                for bag in getattr(strip, "channelbags", ()):
                    try:
                        bag.fcurves.remove(curve)
                        break
                    except (AttributeError, ReferenceError, RuntimeError):
                        continue


def _set_action(armature, action) -> None:
    data = armature.animation_data or armature.animation_data_create()
    data.action = action
    if hasattr(data, "action_slot") and getattr(action, "slots", None):
        data.action_slot = action.slots[0]


def _source_clips(settings, option) -> dict[str, object]:
    """Editable source clips beside the chosen tail's skeleton."""
    from forge import clips as clipscan

    path = Path(bpy.path.abspath(option.path)) if option.path else None
    if path is None or not path.is_file():
        return {}
    # Stay inside this source hero's own extraction.  Scanning the sibling
    # extractions with the same roots selected Atlas's aim_weapon_idle for a
    # Werewolf tail and silently keyed a tail that never moved.
    roots = clipscan.clip_roots(path.parent)
    for relative in ("dmx/animation", "dmx", "anims", "anims2"):
        candidate = path.parent / relative
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    rows = clipscan.discover(roots)
    found: dict[str, object] = {}
    for row in rows:
        if row.editable:
            found.setdefault(row.label.lower(), row)
    return found


def _import_source_clip(source, path: Path, label: str):
    """Import one tail-source clip onto the source rig and return its action."""
    before_actions = {action.name for action in bpy.data.actions}
    before_objects = {obj.name for obj in bpy.context.scene.objects}
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    try:
        core.select_only(bpy.context, [source])
        bpy.context.view_layer.objects.active = source
        if source.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        # Pulse 5.4 adds a slot to the active action; detach the previous
        # source clip so this file gets its own action.
        if source.animation_data is not None:
            source.animation_data.action = None
        source2.import_dmx(path, append="APPEND")
    finally:
        for obj in [obj for obj in bpy.context.scene.objects if obj.name not in before_objects]:
            if obj != source and obj.type in ("MESH", "ARMATURE"):
                bpy.data.objects.remove(obj, do_unlink=True)
        core.select_only(bpy.context, selected)
        if active is not None:
            bpy.context.view_layer.objects.active = active
    created = [action for action in bpy.data.actions if action.name not in before_actions]
    if not created:
        raise RuntimeError(f"tail-source-clip-no-action: {label} created no action")
    action = created[0]
    base = f"DMF tail source {label}"
    name = base
    index = 1
    while bpy.data.actions.get(name) not in (None, action):
        name = f"{base} {index:02d}"
        index += 1
    action.name = name
    return action


def _source_frame(frame: int, target_start: int, target_end: int, source_start: int, source_end: int) -> int:
    if target_end <= target_start or source_end <= source_start:
        return source_start
    fraction = (frame - target_start) / float(target_end - target_start)
    return source_start + int(round(fraction * (source_end - source_start)))


from forge.solver import is_solver_input as _is_solver_input


def _bake_body_action(target, source, source_action, label: str):
    """Copy a stock animation action onto the target rig by solved pose matrices.

    This is the path that produced the working 06:47 build.  It reproduces the
    stock clip's pose in Blender for every bone, including the root motion.  The
    root rotation is divided out of the FK bones so the engine's own root does not
    double it; solver inputs (``*_IKTARGET``, ``*_OFFSET``, muzzle, weapon hands)
    are copied as authored, because those are what the IK/aim nodes read and
    rotating them is how the 06:47 build ended up with the arms and head turned.
    """
    scene = bpy.context.scene
    target.animation_data_create()
    action = bpy.data.actions.new(label)
    action.use_fake_user = True
    target.animation_data.action = action
    if hasattr(target.animation_data, "action_slot") and action.slots:
        target.animation_data.action_slot = action.slots[0]
    start, end = (int(round(value)) for value in source_action.frame_range)
    source.animation_data_create()
    old_source_action = source.animation_data.action
    source.animation_data.action = source_action
    if hasattr(source.animation_data, "action_slot") and source_action.slots:
        source.animation_data.action_slot = source_action.slots[0]
    # A quaternion and its negation are the same rotation, but a keyed sign flip
    # makes the exported clip interpolate the long way round: one flipped frame
    # turns a hand or finger chain by 180 degrees while every other bone stays
    # correct.  Keep the sign continuous per bone across the whole clip.
    previous: dict[str, object] = {}
    for bone in target.pose.bones:
        bone.rotation_mode = "QUATERNION"
    try:
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            root = source.pose.bones.get("root_motion")
            axes = root.matrix.to_quaternion().to_matrix().inverted().to_4x4() if root is not None else Matrix.Identity(4)
            desired = {}
            for bone in target.pose.bones:
                sample = source.pose.bones.get(bone.name)
                if sample is not None:
                    if bone.name == "root_motion" or _is_solver_input(bone.name):
                        desired[bone.name] = sample.matrix.copy()
                    else:
                        desired[bone.name] = axes @ sample.matrix
            for bone in target.pose.bones:
                rest = bone.bone.matrix_local
                if bone.name not in desired:
                    bone.matrix_basis = Matrix.Identity(4)
                elif bone.parent is None:
                    bone.matrix_basis = rest.inverted() @ desired[bone.name]
                elif bone.parent.name in desired:
                    parent_pose = desired[bone.parent.name]
                    parent_rest = bone.parent.bone.matrix_local
                    bone.matrix_basis = (parent_pose @ parent_rest.inverted() @ rest).inverted() @ desired[bone.name]
                else:
                    bone.matrix_basis = (
                        bone.parent.matrix @ bone.parent.bone.matrix_local.inverted() @ rest
                    ).inverted() @ desired[bone.name]
            bpy.context.view_layer.update()
            for bone in target.pose.bones:
                quaternion = bone.matrix_basis.to_quaternion()
                last = previous.get(bone.name)
                if last is not None and quaternion.dot(last) < 0.0:
                    quaternion = quaternion.copy()
                    quaternion.negate()
                previous[bone.name] = quaternion.copy()
                bone.rotation_quaternion = quaternion
                bone.keyframe_insert("location", frame=frame)
                bone.keyframe_insert("rotation_quaternion", frame=frame)
                bone.keyframe_insert("scale", frame=frame)
    finally:
        source.animation_data.action = old_source_action
        scene.frame_set(scene.frame_current)
    return action


def _transfer_body_action(target, source, source_action, label: str):
    """Copy a stock clip's local animation onto the target rig, bone for bone.

    **Measured, not assumed:** the two rigs share a rest basis bone for bone
    (``root_motion``, ``pelvis``, ``head``, ``clavicle_*``, ``arm_upper_*``,
    ``hand_*``, ``leg_upper_*`` all 0.0000 deg; 115 of 138 bit-exact, worst
    0.14 deg on a gun joint), yet copying the local values verbatim lands the
    whole pose 120 deg off in Blender, because the animation DMX and the skeleton
    DMX get different root_motion axis fixups on import.  This transfer is
    therefore **not a fix** and must not be published as one until the offset is
    resolved against the convention the engine reads.
    """
    scene = bpy.context.scene
    target.animation_data_create()
    action = bpy.data.actions.new(label)
    action.use_fake_user = True
    target.animation_data.action = action
    if hasattr(target.animation_data, "action_slot") and action.slots:
        target.animation_data.action_slot = action.slots[0]
    start, end = (int(round(value)) for value in source_action.frame_range)
    source.animation_data_create()
    old_source_action = source.animation_data.action
    source.animation_data.action = source_action
    if hasattr(source.animation_data, "action_slot") and source_action.slots:
        source.animation_data.action_slot = source_action.slots[0]
    shared = [bone.name for bone in target.pose.bones if source.pose.bones.get(bone.name) is not None]
    for bone in target.pose.bones:
        bone.rotation_mode = "QUATERNION"
    previous: dict[str, object] = {}
    try:
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            samples = {}
            for name in shared:
                samples[name] = source.pose.bones[name].matrix_basis.decompose()
            for bone in target.pose.bones:
                sample = samples.get(bone.name)
                if sample is None:
                    # A bone the animation skeleton does not have (tail and the
                    # model's extra leaves) stays at rest.
                    bone.location = (0.0, 0.0, 0.0)
                    bone.scale = (1.0, 1.0, 1.0)
                    quaternion = bone.matrix_basis.to_quaternion()
                else:
                    location, quaternion, scale = sample
                    bone.location = location
                    bone.scale = scale
                last = previous.get(bone.name)
                if last is not None and quaternion.dot(last) < 0.0:
                    quaternion = quaternion.copy()
                    quaternion.negate()
                previous[bone.name] = quaternion.copy()
                bone.rotation_quaternion = quaternion
                bone.keyframe_insert("location", frame=frame, group=bone.name)
                bone.keyframe_insert("rotation_quaternion", frame=frame, group=bone.name)
                bone.keyframe_insert("scale", frame=frame, group=bone.name)
    finally:
        source.animation_data.action = old_source_action
        scene.frame_set(scene.frame_current)
    return action


def _write_tail_action(settings, row, target_action, source, source_action, tail_names: list[str]) -> dict:
    """Key the source tail's motion into the target hero action, in one pass."""
    hero = settings.target_armature
    if hero is None:
        raise RuntimeError("tail-needs-hero: import the hero skeleton first")
    names = [name for name in tail_names if hero.pose.bones.get(name) is not None]
    if not names:
        raise RuntimeError(f"tail-target-no-bones: {target_action.name} has no source tail bones")
    source_names = _action_bones(source_action)
    if not any(name in source_names for name in names):
        raise RuntimeError(f"tail-source-no-keys: {source_action.name} does not animate a tail")
    source_start, source_end = (int(round(value)) for value in source_action.frame_range)
    target_start, target_end = (int(round(value)) for value in target_action.frame_range)
    if target_end <= target_start:
        raise RuntimeError(f"tail-target-empty-range: {target_action.name} has no frame range")
    scene = bpy.context.scene
    old_frame = scene.frame_current
    old_hero_action = hero.animation_data.action if hero.animation_data else None
    old_source_action = source.animation_data.action if source.animation_data else None
    samples: list[list[tuple[str, object, str]]] = []
    try:
        _set_action(source, source_action)
        for frame in range(target_start, target_end + 1):
            scene.frame_set(_source_frame(frame, target_start, target_end, source_start, source_end))
            bpy.context.view_layer.update()
            current = []
            for name in names:
                bone = source.pose.bones.get(name)
                if bone is not None:
                    current.append((name, bone.matrix_basis.copy(), bone.rotation_mode))
            samples.append(current)
        _clear_tail_curves(target_action, set(names))
        _set_action(hero, target_action)
        for offset, current in enumerate(samples):
            frame = target_start + offset
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            for name, matrix, rotation_mode in current:
                bone = hero.pose.bones.get(name)
                if bone is None:
                    continue
                bone.rotation_mode = rotation_mode
                bone.matrix_basis = _blend_matrix(matrix, settings.tail_weight)
                bone.keyframe_insert("location", frame=frame, group=name)
                if bone.rotation_mode == "QUATERNION":
                    bone.keyframe_insert("rotation_quaternion", frame=frame, group=name)
                elif bone.rotation_mode == "AXIS_ANGLE":
                    bone.keyframe_insert("rotation_axis_angle", frame=frame, group=name)
                else:
                    bone.keyframe_insert("rotation_euler", frame=frame, group=name)
                bone.keyframe_insert("scale", frame=frame, group=name)
    finally:
        if hero.animation_data is not None:
            hero.animation_data.action = old_hero_action
        if source.animation_data is not None:
            source.animation_data.action = old_source_action
        scene.frame_set(old_frame)
    return {"frames": target_end - target_start + 1, "bones": len(names)}


def attach_tail(settings, option=None) -> dict:
    """Load the selected tail and append its rest tail bones to the hero."""
    option = option or _selected_option(settings)
    if option is None:
        raise RuntimeError("tail-option-missing: scan and select a tail source first")
    if option.rig is None or settings.tail_armature != option.rig:
        load_option(settings, settings.tail_option_index)
    if settings.tail_armature is None:
        raise RuntimeError("tail-no-rig: the chosen tail has no armature")
    return _copy_tail_bones(settings, settings.tail_armature)


def _selected_option(settings):
    if not settings.tail_options:
        return None
    return settings.tail_options[max(0, min(settings.tail_option_index, len(settings.tail_options) - 1))]


def _ensure_gameplay_rows(settings, docs) -> list[int]:
    """Add rows for gameplay clips that have not been imported yet.

    The Tails page must not require the owner to visit the Animations page and
    import hundreds of clips first.  Rows start in ``NEW``; the same timer that
    keys tail motion imports one row per tick when it reaches it.
    """
    known = {(row.label or "").lower() for row in settings.clips}
    hero = settings.target_armature
    created: list[int] = []
    for doc in docs:
        if doc.label.lower() in known:
            continue
        row = settings.clips.add()
        row.label = doc.label
        row.path = str(doc.preview or doc.source)
        row.ag = "AG2"
        row.source_hero = hero.name if hero is not None else ""
        row.state = "NEW"
        created.append(len(settings.clips) - 1)
    return created


def start_auto(settings, *, schedule: bool = True, publish: bool = False) -> int:
    """Queue every imported hero clip for one automatic tail pass."""
    global _AUTO_QUEUE, _AUTO_TIMER, _AUTO_SOURCE, _AUTO_SETTINGS, _AUTO_CLIPS, _AUTO_SOURCE_ACTIONS
    global _AUTO_UPDATED, _AUTO_SKIPPED, _AUTO_FAILED, _AUTO_TAIL_NAMES, _AUTO_PUBLISH
    if _AUTO_TIMER is not None or _SCAN_TIMER is not None or jobs.is_running() or clipops.is_running():
        raise RuntimeError("tail-auto-busy: another job is already running")
    option = _selected_option(settings)
    if option is None:
        raise RuntimeError("tail-option-missing: scan and select a tail source first")
    hero = settings.target_armature
    if hero is None:
        raise RuntimeError("tail-needs-hero: import the hero skeleton first")
    attach_tail(settings, option)
    clips = _source_clips(settings, option)
    if not clips:
        raise RuntimeError(f"tail-source-clips-empty: {option.label} has no source clips")
    if publish:
        try:
            extraction, hero_root = _hero_roots(settings)
            _ensure_gameplay_rows(settings, animgraph.documents(hero_root, extraction))
        except Exception:
            # A model without a paired clips folder can still use the old
            # imported-action path; the queue below reports the missing rows.
            pass
    _AUTO_SOURCE = settings.tail_armature.name
    _AUTO_SETTINGS = settings
    _AUTO_CLIPS = clips
    _AUTO_SOURCE_ACTIONS = {}
    _AUTO_TAIL_NAMES = _tail_names(settings.tail_armature)
    _AUTO_PUBLISH = bool(publish)
    _AUTO_UPDATED = 0
    _AUTO_SKIPPED = 0
    _AUTO_FAILED = 0
    _AUTO_QUEUE = [
        index for index, row in enumerate(settings.clips)
        if (row.action and row.state in ("IMPORTED", "WRITTEN")) or row.state == "NEW"
    ]
    if not _AUTO_QUEUE:
        raise RuntimeError("tail-auto-no-clips: import this hero's clips first")
    settings.tail_note = (
        f"Adding {option.label} tail to {len(_AUTO_QUEUE)} {hero.name} clips"
    )
    if schedule and _AUTO_TIMER is None:
        _AUTO_TIMER = bpy.app.timers.register(_auto_tick, first_interval=0.0, persistent=True)
    return len(_AUTO_QUEUE)


def _auto_tick():
    global _AUTO_TIMER, _AUTO_SETTINGS, _AUTO_UPDATED, _AUTO_SKIPPED, _AUTO_FAILED
    settings = _AUTO_SETTINGS
    if settings is None:
        settings = getattr(getattr(bpy.context, "scene", None), "dmf", None)
        _AUTO_SETTINGS = settings
    if settings is None or not _AUTO_QUEUE:
        _auto_finish(settings)
        return None
    index = _AUTO_QUEUE.pop(0)
    if index >= len(settings.clips):
        return 0.05
    row = settings.clips[index]
    option = _selected_option(settings)
    source = settings.tail_armature
    try:
        if option is None or source is None:
            raise RuntimeError("tail-option-missing: the selected tail source went away")
        if not row.action:
            clipops._import_one(settings, row)
        clip = _AUTO_CLIPS.get((row.label or "").lower())
        if clip is None:
            _AUTO_SKIPPED += 1
            return 0.05
        action = _AUTO_SOURCE_ACTIONS.get(str(clip.path))
        if action is None or getattr(action, "name", "") not in bpy.data.actions:
            action = _import_source_clip(source, Path(clip.path), row.label or clip.label)
            _AUTO_SOURCE_ACTIONS[str(clip.path)] = action
        target = bpy.data.actions.get(row.action)
        if target is None:
            raise RuntimeError(f"tail-target-missing: {row.label} has no action")
        target_start, target_end = (int(round(value)) for value in target.frame_range)
        if target_end <= target_start:
            _AUTO_SKIPPED += 1
            settings.tail_note = f"{row.label}: no keyed frame range, tail skipped"
            core.set_status(settings, settings.tail_note, "OK")
            return 0.05
        result = _write_tail_action(settings, row, target, source, action, _AUTO_TAIL_NAMES)
        _AUTO_UPDATED += 1
        settings.tail_note = (
            f"{row.label}: {result['frames']} frames on {result['bones']} tail bones; "
            f"{len(_AUTO_QUEUE)} left"
        )
        core.set_status(settings, settings.tail_note, "BUSY")
    except Exception as error:
        _AUTO_FAILED += 1
        settings.tail_note = f"{row.label}: {error}"
        core.set_status(settings, settings.tail_note, "WARN")
    if not _AUTO_QUEUE:
        _auto_finish(settings)
        return None
    return 0.05


def _hero_roots(settings):
    body = Path(bpy.path.abspath(settings.body_dmx)) if settings.body_dmx else None
    if body is None or not body.is_file():
        raise RuntimeError("tail-needs-body: choose the hero body DMX first")
    hero = body.parent
    extraction = Path(bpy.path.abspath(settings.extraction_dir)) if settings.extraction_dir else None
    if extraction is None or extraction not in hero.parents:
        extraction = next(
            (parent for parent in hero.parents if (parent / "models").is_dir() and hero.is_relative_to(parent / "models")),
            None,
        )
    if extraction is None:
        raise RuntimeError("tail-needs-extraction: the hero body is not inside an S2V extraction")
    return extraction, hero


def _doc_for_row(docs, row):
    label = (row.label or "").strip().lower()
    return next((doc for doc in docs if doc.label.strip().lower() == label), None)


def _tail_artifact_root(settings, hero: Path) -> Path:
    return core.project_root(settings) / "artifacts" / "tail-animgraph" / hero.name


def _compiler_skeleton_source(settings, hero: Path, extraction: Path) -> Path:
    """The hero's animation skeleton, never a body mesh with extra joints.

    A body DMX can carry render-only joints between the animated bones.  Using
    it as the clip skeleton changes the track order and offsets the pose in game.
    S2V's live skeleton cache has the exact ``*_skel.dmx`` the original vnmclips
    were compiled against, with the tail appended by the caller.
    """
    roots = [extraction, core.project_root(settings) / "artifacts" / "tail-skeletons"]
    for root in roots:
        if not root.is_dir():
            continue
        matches = [
            path for path in root.rglob(f"{hero.name}_skel.dmx")
            if path.is_file() and hero.name.lower() in {part.lower() for part in path.parts}
        ]
        if matches:
            return sorted(matches)[0]
    env = core.env(settings)
    cache = core.project_root(settings) / "artifacts" / "tail-skeletons"
    files = live.extract_tail_skeletons(env, cache)
    matches = [path for path in files if hero.name.lower() in {part.lower() for part in path.parts}]
    if not matches:
        raise RuntimeError(f"tail-no-skeleton: no {hero.name}_skel.dmx in the live skeleton cache")
    return sorted(matches)[0]


def _tail_names_in(armature) -> list[str]:
    names = [bone.name for bone in armature.data.bones if bone.name.lower().startswith("tail_")]
    names.sort(key=lambda name: int(name.rsplit("_", 1)[-1]) if name.rsplit("_", 1)[-1].isdigit() else 0)
    return names


def seat_tail_chain(settings) -> dict:
    """Move the appended tail chain onto the hero's own body and hang it downward.

    `_copy_tail_bones` copies the source rig's rest values, which are expressed in the source model's
    space.  The inferno tail therefore arrived lying along the source's -X axis, metres from Seven's
    pelvis (the 2026-11-16 screenshot shows it stretched out to the left).  The chain is rotated so
    its root-to-second direction points down and back from `pelvis`, with every bone keeping its own
    length, and the edit-mode rest is re-seated.
    """
    from mathutils import Vector

    hero = settings.target_armature
    if hero is None or hero.type != "ARMATURE":
        raise RuntimeError("tail-seat-needs-hero: import the hero first")
    names = _tail_names_in(hero)
    if len(names) < 2:
        raise RuntimeError("tail-seat-needs-chain: attach the tail first")
    pelvis = hero.data.bones.get("pelvis")
    if pelvis is None:
        raise RuntimeError("tail-seat-needs-pelvis: the hero rig has no pelvis")
    root = hero.data.bones[names[0]].head_local.copy()
    second = hero.data.bones[names[1]].head_local.copy()
    source_direction = (second - root).normalized()
    target_direction = Vector((0.0, 0.42, -0.91)).normalized()
    rotation = source_direction.rotation_difference(target_direction)
    anchor = pelvis.head_local + Vector((0.0, 7.0, 1.0))
    matrix = (
        __import__("mathutils").Matrix.Translation(anchor)
        @ rotation.to_matrix().to_4x4()
        @ __import__("mathutils").Matrix.Translation(-root)
    )
    bpy.context.view_layer.objects.active = hero
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for name in names:
            bone = hero.data.edit_bones.get(name)
            if bone is None:
                continue
            bone.head = matrix @ bone.head
            bone.tail = matrix @ bone.tail
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return {"bones": len(names), "anchor": [round(value, 3) for value in anchor]}


def lift_tail_mesh(settings, source_dmx: Path, *, name: str = "") -> object:
    """Take the tail geometry out of a live model's own mesh, weighted to its own tail joints.

    The Inferno bartender is the only model in the game whose mesh carries an inferno tail, and it
    carries the whole body with it.  Importing it and keeping only the faces whose vertices are
    weighted to the tail chain gives the port real geometry -- no invented tube, no banned hero --
    and the vertex groups already name `tail_0..tail_9`, so the same object binds to the chain that
    `tailops` attached.  A source with no tail-weighted vertices refuses.
    """
    hero = settings.target_armature
    if hero is None:
        raise RuntimeError("tail-lift-needs-hero: import the hero first")
    before = {obj.name for obj in bpy.context.scene.objects}
    source2.import_dmx(Path(source_dmx), append="NEW_ARMATURE")
    imported = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"tail-lift-no-mesh: {source_dmx} produced no mesh")
    mesh = max(meshes, key=lambda obj: len(obj.data.vertices))
    tail_groups = {group.index for group in mesh.vertex_groups if group.name.lower().startswith("tail_")}
    if not tail_groups:
        raise RuntimeError(f"tail-lift-no-tail-groups: {source_dmx} names no tail vertex group")
    keep = {
        vertex.index
        for vertex in mesh.data.vertices
        if any(group.group in tail_groups and group.weight > 0 for group in vertex.groups)
    }
    if not keep:
        raise RuntimeError(f"tail-lift-no-weighted-vertices: {source_dmx} weights nothing to the tail")
    faces = [tuple(poly.vertices) for poly in mesh.data.polygons if set(poly.vertices) <= keep]
    if not faces:
        raise RuntimeError(f"tail-lift-no-faces: {source_dmx} has no face fully on the tail chain")
    used = sorted({index for face in faces for index in face})
    remap = {old: new for new, old in enumerate(used)}
    # The source is legacy content: it imports at its own scale and rotation (the 2024 bartender
    # against the modern Seven rig).  The tail is one rigid chain, so the whole mesh takes one
    # rigid transform: rotate root-to-second onto the hero's direction and scale by the ratio of
    # the two chains' total lengths.  Per-bone frames were tried and made it worse -- legacy bone
    # rolls differ, and the mesh smeared 30 units sideways.
    from mathutils import Matrix

    source_armature = next((obj for obj in imported if obj.type == "ARMATURE"), None)
    if source_armature is None:
        raise RuntimeError(f"tail-lift-no-rig: {source_dmx} produced no armature")
    source_names = _tail_names_in(source_armature)
    hero_names = _tail_names_in(hero)
    matrix = Matrix.Identity(4)
    if len(source_names) >= 2 and len(hero_names) >= 2:
        source_root = source_armature.data.bones[source_names[0]].head_local.copy()
        source_second = source_armature.data.bones[source_names[1]].head_local.copy()
        hero_root = hero.data.bones[hero_names[0]].head_local.copy()
        hero_second = hero.data.bones[hero_names[1]].head_local.copy()
        source_length = sum(source_armature.data.bones[name].length for name in source_names)
        hero_length = sum(hero.data.bones[name].length for name in hero_names)
        scale = hero_length / source_length if source_length else 1.0
        rotation = (source_second - source_root).normalized().rotation_difference(
            (hero_second - hero_root).normalized()
        )
        matrix = (
            Matrix.Translation(hero_root)
            @ rotation.to_matrix().to_4x4()
            @ Matrix.Diagonal((scale, scale, scale, 1.0))
            @ Matrix.Translation(-source_root)
        )
    placed = [tuple(matrix @ mesh.data.vertices[old].co) for old in used]
    label = name or f"{hero.name}"
    lifted = bpy.data.meshes.new(label)
    lifted.clear_geometry()
    lifted.from_pydata(placed, [], [tuple(remap[index] for index in face) for face in faces])
    obj = bpy.data.objects.new(label, lifted)
    bpy.context.scene.collection.objects.link(obj)
    # The lifted mesh arrives with PulseSrcOps' `no_material`, which the client draws as nothing.
    # Give it the hero body's own material so it renders with the model it belongs to.
    body = settings.target_body
    if body is not None and getattr(body, "material_slots", None):
        for slot in body.material_slots:
            if slot.material is not None:
                obj.data.materials.append(slot.material)
                break
    by_name = {group.index: group.name for group in mesh.vertex_groups}
    for old in used:
        source = mesh.data.vertices[old]
        for element in source.groups:
            if element.group not in tail_groups or element.weight <= 0:
                continue
            group_name = by_name[element.group]
            group = obj.vertex_groups.get(group_name) or obj.vertex_groups.new(name=group_name)
            group.add([remap[old]], element.weight, "REPLACE")
    obj.parent = hero
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = hero
    for other in imported:
        bpy.data.objects.remove(other, do_unlink=True)
    return obj


def export_tail_skeleton(settings, destination: Path, *, base_path: Path | None = None, mesh=None) -> Path:
    """Export the hero armature with its appended tail as a compiler skeleton."""
    hero = settings.target_armature
    temporary_base = None
    if base_path is not None:
        before = {obj.name for obj in bpy.context.scene.objects}
        source2.import_dmx(Path(base_path), append="NEW_ARMATURE")
        new = [obj for obj in bpy.context.scene.objects if obj.name not in before and obj.type == "ARMATURE"]
        if not new:
            raise RuntimeError(f"tail-skeleton-import-failed: {base_path}")
        temporary_base = max(new, key=lambda obj: len(obj.data.bones))
        old_target = settings.target_armature
        settings.target_armature = temporary_base
        try:
            _copy_tail_bones(settings, settings.tail_armature)
        finally:
            settings.target_armature = old_target
        hero = temporary_base
    if hero is None or hero.type != "ARMATURE":
        raise RuntimeError("tail-needs-hero: import the hero skeleton first")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    old = {
        "path": scene.vs.export_path,
        "format": scene.vs.export_format,
        "engine": scene.vs.engine,
        "dmx": scene.vs.dmx_format,
        "encoding": scene.vs.dmx_encoding,
        "list": [(row.name, row.ob_type, getattr(row, "icon", ""), row.obj) for row in scene.vs.export_list],
    }
    old_collections = [collection for collection in hero.users_collection]
    skinned = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and (
            obj.parent == hero
            or any(modifier.type == "ARMATURE" and modifier.object == hero for modifier in obj.modifiers)
        )
    ]
    if mesh is not None and mesh not in skinned:
        skinned.append(mesh)
    temporary = bpy.data.collections.new("DMF Skeleton Export")
    scene.collection.children.link(temporary)
    data = hero.animation_data
    old_action = data.action if data is not None else None
    old_nla = data.use_nla if data is not None else False
    old_frame = scene.frame_current
    old_pose = [(bone.name, bone.matrix_basis.copy()) for bone in hero.pose.bones]
    old_pose_position = hero.data.pose_position
    try:
        # A skeleton DMX is a rest reference.  Exporting it with the last edited
        # clip still active writes a 30-frame animation into the skeleton and
        # offsets every clip that uses it (the guide's flipped/offset symptom).
        if data is not None:
            data.action = None
            data.use_nla = False
        for bone in hero.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        hero.data.pose_position = "REST"
        scene.frame_set(0)
        bpy.context.view_layer.update()
        for collection in old_collections:
            collection.objects.unlink(hero)
        temporary.objects.link(hero)
        temporary.vs.export = True
        hero.vs.export = True
        # A skeleton exported with its skinned mesh follows the same PulseSrcOps
        # bone-transform path as the body DMX.  An armature-only export applies
        # a different axis to newly added unconnected bones, which is what put
        # the tail sideways while leaving the original body bones correct.
        for mesh in skinned:
            temporary.objects.link(mesh)
            if hasattr(mesh, "vs"):
                mesh.vs.export = True
                if hasattr(mesh.vs, "generate_lods"):
                    mesh.vs.generate_lods = False
        scene.vs.export_path = str(destination.parent) + os.sep
        scene.vs.export_format = "DMX"
        scene.vs.engine = "SOURCE"
        scene.vs.dmx_format = "22_modeldoc"
        scene.vs.dmx_encoding = "3"
        scene.vs.export_list.clear()
        row = scene.vs.export_list.add()
        row.name = temporary.name
        row.ob_type = "COLLECTION"
        row.icon = "GROUP"
        row.collection = temporary
        old_debug = bpy.app.debug_value
        bpy.app.debug_value = max(2, old_debug)
        try:
            result = bpy.ops.export_scene.smd(collection=temporary.name)
        finally:
            bpy.app.debug_value = old_debug
        if "FINISHED" not in result:
            raise RuntimeError("tail-skeleton-export-refused: PulseSrcOps did not finish")
        made = sorted(destination.parent.glob("*.dmx"), key=lambda path: path.stat().st_mtime)
        if not made:
            raise RuntimeError("tail-skeleton-export-empty: PulseSrcOps wrote no DMX")
        if made[-1] != destination:
            if destination.exists():
                destination.unlink()
            made[-1].replace(destination)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError("tail-skeleton-export-empty: the skeleton DMX is empty")
        return destination
    finally:
        scene.vs.export_path = old["path"]
        scene.vs.export_format = old["format"]
        scene.vs.engine = old["engine"]
        scene.vs.dmx_format = old["dmx"]
        scene.vs.dmx_encoding = old["encoding"]
        scene.vs.export_list.clear()
        for name, ob_type, icon, obj in old["list"]:
            item = scene.vs.export_list.add()
            item.name = name
            item.ob_type = ob_type
            item.icon = icon
            item.obj = obj
        if data is not None:
            data.action = old_action
            data.use_nla = old_nla
        for name, basis in old_pose:
            bone = hero.pose.bones.get(name)
            if bone is not None:
                bone.matrix_basis = basis
        hero.data.pose_position = old_pose_position
        scene.frame_set(old_frame)
        if hero.name in temporary.objects:
            temporary.objects.unlink(hero)
        for mesh in skinned:
            if mesh.name in temporary.objects:
                temporary.objects.unlink(mesh)
        for collection in old_collections:
            if collection.name in bpy.data.collections and hero.name not in collection.objects:
                collection.objects.link(hero)
        bpy.data.collections.remove(temporary, do_unlink=True)
        if temporary_base is not None:
            armature_data = temporary_base.data
            bpy.data.objects.remove(temporary_base, do_unlink=True)
            if armature_data is not None and getattr(armature_data, "users", 0) == 0:
                bpy.data.armatures.remove(armature_data)


def write_tail_sources(settings, docs=None) -> dict:
    """Write every tailed action over the DMX its gameplay vnmclip names.

    The extraction is never edited.  The edited DMX and the original vnmclip
    are mirrored under ``artifacts/tail-animgraph/<hero>`` for the compiler
    handoff, which also makes the result reproducible after a Blender restart.
    """
    extraction, hero = _hero_roots(settings)
    docs = docs if docs is not None else animgraph.documents(hero, extraction)
    if not docs:
        raise RuntimeError("tail-no-gameplay-clips: no clips/*.vnmclip points at an existing source DMX")
    root = _tail_artifact_root(settings, hero)
    written = []
    used = []
    for row in settings.clips:
        doc = _doc_for_row(docs, row)
        if doc is None or not row.action:
            continue
        relative = doc.source.relative_to(extraction)
        target = root / relative
        clipops.write_action(settings, row, target.parent.parent, target=target)
        written.append({"label": row.label, "source": str(target)})
        used.append(doc)
    if not written:
        labels = ", ".join(doc.label for doc in docs[:4])
        raise RuntimeError(f"tail-no-imported-gameplay-clips: import the clips folder first ({labels} ...)")
    return {"root": str(root), "written": written, "docs": used}


def _extract_vnmskel(settings, hero_relative: Path, hero_name: str, root: Path) -> Path:
    """Ask Source 2 Viewer for the hero's skeleton document when it was not extracted."""
    env = core.env(settings)
    if env.s2v is None or env.vpk is None:
        raise RuntimeError("tail-no-vnmskel: set the AG2 skeleton field; S2V and the live VPK are unavailable")
    relative = (hero_relative / f"{hero_name}.vnmskel_c").as_posix()
    root.mkdir(parents=True, exist_ok=True)
    command = [
        str(env.s2v),
        "-i",
        str(env.vpk),
        "-f",
        relative,
        "-o",
        str(root),
        "-d",
        "-q",
    ]
    result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=120)
    if result.returncode:
        raise RuntimeError(f"tail-vnmskel-extract-failed: {result.stderr.strip() or result.stdout.strip()}")
    found = sorted(root.rglob(f"{hero_name}.vnmskel"))
    if not found:
        raise RuntimeError(f"tail-vnmskel-extract-empty: {relative} produced no .vnmskel")
    return found[0]


def publish_tail_anims(settings) -> dict:
    """Mirror the edited clips, prepare the compiler skeleton, and compile them.

    The vnmskel is a compile input only.  Its compiled form stays beside the
    CSDK clips for ModelDoc preview but is excluded from the packed VPK; the
    model's own skeleton already has the appended tail bones.
    """
    extraction, hero = _hero_roots(settings)
    if getattr(settings, "tail_bare_only", False):
        # The haze_noskel shape: the tail's bones attached to the hero and its mesh, nothing else.
        # No clips are authored, no .vnmskel is written or compiled, and nothing is blended -- the
        # owner's sentence is "it has to literally just be the tail it's bones attached to the hero".
        body = settings.target_armature
        if body is None or body.type != "ARMATURE":
            raise RuntimeError("tail-bare-needs-hero: import the hero first")
        body_mesh = max(
            (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
            key=lambda obj: len(obj.data.vertices),
            default=None,
        )
        root = _tail_artifact_root(settings, hero)
        hero_relative = hero.relative_to(extraction)
        skeleton = root / hero_relative / "dmx" / "mesh" / f"{hero.name}_tailbones.dmx"
        export_tail_skeleton(settings, skeleton, mesh=body_mesh)
        content_addon = core.csdk_addon_folder(settings)
        if content_addon is None:
            raise RuntimeError("tail-bare-needs-stage: stage the addon in Setup before exporting")
        target = content_addon / skeleton.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(skeleton, target)
        return {
            "mode": "tail-only",
            "bundle": str(root),
            "written": 0,
            "compiled": 0,
            "failed": 0,
            "game_addon": str(content_addon),
            "skeleton": str(target),
            "outcomes": [],
            "gate": {"gate": "SKIPPED tail-only: no clips and no .vnmskel to gate"},
        }
    docs = animgraph.documents(hero, extraction)
    body = settings.target_armature
    body_mesh = max(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
        key=lambda obj: len(obj.data.vertices),
        default=None,
    )
    # Gameplay clips ship against the model's own skeleton, not the 140-bone
    # animation skeleton.  The shipped model has 168 bones and the engine does
    # not retarget the last 28; a 147-track clip resolves against the 168-bone
    # skeleton as a mismatched pose (the body lies flat).  Authoring on the body
    # rig writes the same 168 bone names the model owns, and the compiled 168
    # skeleton is shipped beside the clips so the engine resolves those tracks.
    clip_rig = body
    original_target = settings.target_armature
    base = _compiler_skeleton_source(settings, hero, extraction)
    before = {obj.name for obj in bpy.context.scene.objects}
    source2.import_dmx(base, append="NEW_ARMATURE")
    source_rig = max(
        (obj for obj in bpy.context.scene.objects if obj.name not in before and obj.type == "ARMATURE"),
        key=lambda obj: len(obj.data.bones),
    )
    settings.target_armature = clip_rig
    try:
        _copy_tail_bones(settings, settings.tail_armature)
        option = _selected_option(settings)
        source_clips = _source_clips(settings, option) if option is not None else {}
        reauthor_failed: list[str] = []
        for row in settings.clips:
            doc = _doc_for_row(docs, row)
            if doc is None:
                continue
            try:
                # Merge the tail onto the stock clip instead of re-authoring the
                # body.  The bake re-does bones the stock clip already owns, and
                # that is measurable: it turns the IK/aim targets by 120-240 deg
                # (arms and head rotated wrong) and writes the sampled absolute
                # pelvis height, so authored movement clips sit ~54 units above
                # stock and the hero lifts off the ground as they start moving.
                # Importing the stock clip onto the model rig and keying only the
                # tail keeps every stock track; measured pelvis height then equals
                # stock exactly.
                settings.target_armature = body
                clipops._import_one(settings, row)
                target_action = bpy.data.actions.get(row.action)
                if target_action is None:
                    continue
                clip = source_clips.get((row.label or "").lower())
                if clip is None:
                    continue
                tail_action = _import_source_clip(settings.tail_armature, Path(clip.path), row.label or clip.label)
                _write_tail_action(settings, row, target_action, settings.tail_armature, tail_action, _tail_names(settings.tail_armature))
            except Exception:
                # One unmatched/odd source clip must not discard the clips that
                # did author cleanly; write_tail_sources skips rows without an
                # action and reports the rest.
                reauthor_failed.append(row.label or "?")
        bundle = write_tail_sources(settings, docs)
        bundle["reauthor_failed"] = reauthor_failed
    finally:
        settings.target_armature = body
    root = Path(bundle["root"])
    hero_relative = hero.relative_to(extraction)
    candidates = sorted(hero.glob("*.vnmskel"))
    if settings.clip_vnmskel and Path(bpy.path.abspath(settings.clip_vnmskel)).is_file():
        candidates.insert(0, Path(bpy.path.abspath(settings.clip_vnmskel)))
    if not candidates:
        candidates.append(_extract_vnmskel(settings, hero_relative, hero.name, root))
    original = candidates[0]
    skeleton = root / hero_relative / "dmx" / "mesh" / f"{hero.name}_tailbones.dmx"
    # The compiler skeleton must be the animation skeleton plus the tail (147
    # bones), the same skeleton the actions above were authored on.  The body
    # mesh is only included so PulseSrcOps resolves the new tail rest basis the
    # same way it did for shiv_body_tailbones.dmx.
    settings.target_armature = clip_rig
    try:
        export_tail_skeleton(settings, skeleton, mesh=body_mesh)
    finally:
        settings.target_armature = body
    tail_names = _tail_names(clip_rig)
    skeleton_relative = skeleton.relative_to(root).as_posix()
    prepared = animgraph.prepare_skeleton(
        original.read_text(encoding="utf-8", errors="replace"),
        skeleton_relative,
        tail_names,
    )
    skeleton_doc = root / hero_relative / original.name
    skeleton_doc.parent.mkdir(parents=True, exist_ok=True)
    skeleton_doc.write_text(prepared, encoding="utf-8")

    content_addon = core.csdk_addon_folder(settings)
    if content_addon is None:
        raise RuntimeError("tail-needs-stage: stage the addon in Setup before compiling clips")
    docs = bundle["docs"]
    for doc in docs:
        for source, relative in (
            (doc.vnmclip, doc.vnmclip.relative_to(extraction)),
            (root / doc.source.relative_to(extraction), doc.source.relative_to(extraction)),
        ):
            target = content_addon / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for source, relative in (
        (skeleton_doc, skeleton_doc.relative_to(root)),
        (skeleton, skeleton.relative_to(root)),
    ):
        target = content_addon / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    wanted = {doc.label.lower() for doc in docs}
    staged_docs = [
        doc for doc in animgraph.documents(content_addon / hero_relative, content_addon)
        if doc.label.lower() in wanted
    ]
    outcomes = animgraph.compile_documents(
        core.env(settings),
        content_addon,
        staged_docs,
        log_dir=core.project_root(settings) / "logs" / "tail-animgraph",
    )
    root_addon = core.csdk_addon_root(settings)
    game_addon = root_addon / "game" / "citadel_addons" / (settings.addon_name or "")
    # Keep the compiled vnmskel beside the clips in the CSDK addon.  ModelDoc's
    # clip preview resolves the clip's external skeleton reference from this
    # addon; without it the preview loads the stock 140-bone skeleton against a
    # 168-track clip, so the tail is missing and the pose is mapped wrong.  It is
    # a compile/preview input only and is deliberately excluded from the packed
    # VPK (the model's own skeleton already carries the tail bones).
    skeleton_compiled = game_addon / hero_relative / original.name.replace(".vnmskel", ".vnmskel_c")
    if not skeleton_compiled.is_file():
        raise RuntimeError(
            "tail-vnmskel-not-compiled: the clips reference a skeleton that the "
            f"compiler did not produce at {skeleton_compiled}"
        )
    failed = [row for row in outcomes if row.returncode]
    # The refusals run here, on the addon's own paths, so a build that would pose the head, arms or
    # tail from the wrong bone cannot be produced by pressing the button; it stops with the code.
    gate = release_gate(settings, clips_root=root)
    return {
        "bundle": str(root),
        "written": len(bundle["written"]),
        "compiled": len(outcomes) - len(failed),
        "failed": len(failed),
        "game_addon": str(game_addon),
        "skeleton": str(skeleton_compiled),
        "outcomes": outcomes,
        "gate": gate,
    }


def release_gate(settings, *, clips_root: Path) -> dict:
    """Run the release gate from the addon, so the automatic path cannot skip a refusal.

    The blend → compile chain used to end at the compiled clips: every refusal lived in
    `tools/tail_release_gate.py`, which only a command line ran.  This calls that same gate with the
    addon's own paths (the mirrored clip documents, the extraction's clip bodies, the compiler
    skeleton and the staged addon) through Blender's own binary, and raises the refusal line so the
    Operate surface shows the code instead of a comment in a log.
    """
    root = core.project_root(settings)
    gate = root / "tools" / "tail_release_gate.py"
    extraction, hero = _hero_roots(settings)
    content_addon = core.csdk_addon_folder(settings)
    if content_addon is None:
        raise RuntimeError("tail-gate-needs-stage: stage the addon in Setup before the gate can read it")
    game_skeleton = _compiler_skeleton_source(settings, hero, extraction)
    hero_relative = hero.relative_to(extraction)
    report = root / "logs" / "tail-gate" / f"{hero.name}-gate.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    command = [
        bpy.app.binary_path,
        "-b",
        "--factory-startup",
        "--python",
        str(gate),
        "--",
        "--addon-content",
        str(content_addon),
        "--clips",
        str(Path(clips_root) / hero_relative / "dmx" / "animation"),
        "--bodies",
        str(extraction / hero_relative / "dmx" / "animation"),
        "--game-skeleton",
        str(game_skeleton),
        "--report",
        str(report),
    ]
    result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=900)
    output = f"{result.stdout}\n{result.stderr}"
    line = next((row for row in output.splitlines() if row.startswith("GATE ")), "")
    if not line.startswith("GATE ADMIT"):
        raise RuntimeError(f"tail-gate-refused: {line or output.strip()[-500:]}")
    return {"gate": line, "report": str(report)}


def _auto_finish(settings) -> None:
    global _AUTO_TIMER, _AUTO_QUEUE, _AUTO_SETTINGS, _AUTO_PUBLISH
    _AUTO_QUEUE = []
    _AUTO_SETTINGS = None
    if _AUTO_TIMER is not None:
        try:
            bpy.app.timers.unregister(_AUTO_TIMER)
        except ValueError:
            pass
        _AUTO_TIMER = None
    if settings is not None:
        settings.tail_note = (
            f"{_AUTO_SOURCE}: added tail to {_AUTO_UPDATED} clips"
            + (f", {_AUTO_SKIPPED} had no matching source clip" if _AUTO_SKIPPED else "")
            + (f", {_AUTO_FAILED} failed" if _AUTO_FAILED else "")
        )
        if _AUTO_PUBLISH and _AUTO_UPDATED > 0:
            try:
                result = publish_tail_anims(settings)
                settings.tail_note += (
                    f"; wrote {result['written']} source DMXs and compiled "
                    f"{result['compiled']} vnmclips into {result['game_addon']}"
                )
            except Exception as error:
                settings.tail_note += f"; clip publish failed: {error}"
                core.set_status(settings, settings.tail_note, "WARN")
                _AUTO_PUBLISH = False
                return
        core.set_status(settings, settings.tail_note, "OK" if not _AUTO_FAILED else "WARN")
    _AUTO_PUBLISH = False


def auto_running() -> bool:
    return _AUTO_TIMER is not None


def _points(armature, chain: tailscan.TailChain) -> list[tuple[float, float, float]]:
    points = []
    for name in chain.bones:
        bone = armature.data.bones.get(name)
        if bone is None:
            continue
        points.append(tuple(bone.head_local))
    if chain.bones:
        last = armature.data.bones.get(chain.bones[-1])
        if last is not None:
            points.append(tuple(last.tail_local))
    return points


def _points_text(points) -> str:
    return ";".join(",".join(f"{value:.5f}" for value in point) for point in points)


def _add_option(settings, *, label, source, path, chain, points, armature=None) -> None:
    if not points:
        return
    bones = ",".join(chain.bones)
    source_path = str(path or "")
    for existing in settings.tail_options:
        same_chain = existing.chain == chain.name and existing.bones == bones
        same_label = existing.label.strip().lower() == label.strip().lower()
        if same_chain and same_label:
            return
        if (
            same_chain
            and existing.path
            and source_path
            and Path(bpy.path.abspath(existing.path)).resolve() == Path(bpy.path.abspath(source_path)).resolve()
        ):
            return
    safe = "".join(character if character.isalnum() else "_" for character in label)[:48]
    digest = hashlib.sha1(f"{label}|{source}|{chain.name}|{path}".encode("utf-8")).hexdigest()[:10]
    preview = core.project_root(settings) / "artifacts" / "tail-previews" / f"{safe}-{digest}.png"
    tailimage.write_tail_png(preview, [points])
    option = settings.tail_options.add()
    option.label = label
    option.source = source
    option.path = str(path or "")
    option.chain = chain.name
    option.bones = bones
    option.points = _points_text(points)
    option.preview = str(preview) if preview.is_file() else ""
    option.count = len(chain.bones)
    option.rig = armature


def _hero_key(root: Path, path: Path) -> str:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    for index, part in enumerate(parts):
        if part.lower() in ("heroes_wip", "heroes_staging") and index + 1 < len(parts):
            return parts[index + 1]
    return path.parent.name


def _candidate_roots(settings) -> list[Path]:
    roots: list[Path] = []
    extraction = Path(bpy.path.abspath(settings.extraction_dir)) if settings.extraction_dir else None
    if extraction and extraction.is_dir():
        roots.append(extraction)
        # Every sibling with a models/ tree is another hero extraction.  Do not
        # require the parent folder to be literally named "extractions"; the
        # owner's Source page can point anywhere, and the first scanner missed
        # every sibling in a differently named workspace folder because of it.
        for parent in (extraction.parent, extraction.parent.parent):
            if parent.is_dir():
                roots.extend(
                    child for child in parent.iterdir()
                    if child.is_dir() and (child / "models").is_dir()
                )
    extra = Path(bpy.path.abspath(settings.tail_scan_dir)) if settings.tail_scan_dir else None
    if extra and extra.is_dir():
        roots.append(extra)
    project = core.project_root(settings)
    if project:
        roots.append(project / "artifacts" / "extractions")
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _import_candidate(path: Path):
    """Import one skeleton for its rest positions, then remove it again."""
    before_objects = {obj.name for obj in bpy.context.scene.objects}
    before_actions = {action.name for action in bpy.data.actions}
    try:
        source2.import_dmx(path, append="NEW_ARMATURE")
        armatures = [
            obj for obj in bpy.context.scene.objects
            if obj.name not in before_objects and obj.type == "ARMATURE"
        ]
        if not armatures:
            return None
        armature = max(armatures, key=lambda item: len(item.data.bones))
        result = (armature, _chains(armature), {
            chain.name: _points(armature, chain) for chain in _chains(armature)
        })
        return result
    except Exception:
        return None
    finally:
        for obj in [obj for obj in bpy.context.scene.objects if obj.name not in before_objects]:
            kind = obj.type
            data = obj.data if kind in ("MESH", "ARMATURE") else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and getattr(data, "users", 0) == 0:
                if kind == "MESH":
                    bpy.data.meshes.remove(data)
                else:
                    bpy.data.armatures.remove(data)
        for action in [action for action in bpy.data.actions if action.name not in before_actions]:
            bpy.data.actions.remove(action)


def _candidate_rank(path: Path, names: list[str]) -> tuple[int, int]:
    """Prefer the declared body over a clip when both describe the same tail."""
    return (1 if live.looks_like_body(path) else 0, len(names))


def _live_root(settings) -> Path:
    return core.project_root(settings) / "artifacts" / "tail-skeletons"


def _live_titles(settings) -> dict[str, str]:
    """Map the Source page's hero folder to its display title."""
    titles: dict[str, str] = {}
    try:
        from .properties import HERO_ITEMS
    except Exception:
        return titles
    for _slug, title, model in HERO_ITEMS:
        parts = Path(model or "").parts
        for index, part in enumerate(parts):
            if part.lower() in ("heroes_wip", "heroes_staging") and index + 1 < len(parts):
                titles.setdefault(parts[index + 1].lower(), title)
                break
    return titles


def _live_label(settings, path: Path, chain: tailscan.TailChain) -> str:
    root = _live_root(settings)
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    hero = ""
    rest: tuple[str, ...] = ()
    for index, part in enumerate(parts):
        if part.lower() in ("heroes_wip", "heroes_staging") and index + 2 < len(parts):
            hero = parts[index + 1]
            rest = parts[index + 2:-1]
            break
    title = _live_titles(settings).get(hero.lower(), hero or path.parent.name)
    rest = tuple(part for part in rest if part.lower() not in ("dmx", "mesh"))
    variant = " ".join(rest[:1])
    return f"{title}{(' ' + variant) if variant else ''} / {chain.name}"


def _add_live_skeletons(settings, files: list[Path]) -> int:
    """Add every live hero skeleton's tail chains without importing its mesh.

    The skeleton cache is produced by Source 2 Viewer from the live VPK, so this
    path covers heroes that were never extracted by hand.  Names are read from
    the DMX header; the chosen tile is imported only when the owner clicks it.
    """
    found = 0
    for path in files:
        names = tailscan.dmx_bone_names(path)
        for chain in tailscan.chains(names):
            label = _live_label(settings, path, chain)
            if any(option.label.lower() == label.lower() for option in settings.tail_options):
                continue
            _add_option(
                settings,
                label=label,
                source="LIVE",
                path=path,
                chain=chain,
                points=[(0.0, 0.0, 0.0), (0.0, 0.0, 0.2 + 0.05 * len(chain.bones))],
            )
            found += 1
    return found


def discover(settings, *, live_files: list[Path] | None = None) -> int:
    """Find tail skeletons in the hero, custom rig, sibling extracts and clips."""
    settings.tail_options.clear()
    settings.tail_option_index = 0
    found = 0

    hero = settings.target_armature
    if hero is not None and hero.type == "ARMATURE":
        for chain in _chains(hero):
            _add_option(
                settings,
                label=f"{hero.name} / {chain.name}",
                source="HERO",
                path=settings.body_dmx,
                chain=chain,
                points=_points(hero, chain),
                armature=None,
            )
            found += 1

    custom = settings.custom_armature
    if custom is not None and custom.type == "ARMATURE" and custom != hero:
        for chain in _chains(custom):
            _add_option(
                settings,
                label=f"{custom.name} / {chain.name}",
                source="CUSTOM",
                path="",
                chain=chain,
                points=_points(custom, chain),
                armature=custom,
            )
            found += 1

    live_files = live_files if live_files is not None else live.tail_skeleton_files(_live_root(settings))
    live_found = _add_live_skeletons(settings, live_files) if live_files else 0
    found += live_found

    scanned = 0
    imported = 0
    for root in _candidate_roots(settings):
        best: dict[str, tuple[Path, list[str]]] = {}
        for path in root.rglob("*.dmx"):
            if path.name.startswith("_."):
                continue
            names = tailscan.dmx_bone_names(path)
            if len(names) < 2:
                continue
            key = _hero_key(root, path)
            if key not in best or _candidate_rank(path, names) > _candidate_rank(*best[key]):
                best[key] = (path, names)
        for key, (path, names) in sorted(best.items()):
            scanned += 1
            loaded = _import_candidate(path)
            if loaded is None:
                # The names still describe a real tail; draw the tile from the
                # names alone so a failed import is visible rather than silent.
                for chain in tailscan.chains(names):
                    _add_option(
                        settings,
                        label=f"{key} / {chain.name}",
                        source="CLIP",
                        path=path,
                        chain=chain,
                        points=[(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)],
                    )
                    found += 1
                continue
            armature, chains, points = loaded
            imported += 1
            for chain in chains:
                _add_option(
                    settings,
                    label=f"{key} / {chain.name}",
                    source="BODY" if live.looks_like_body(path) else "CLIP",
                    path=path,
                    chain=chain,
                    points=points.get(chain.name, []),
                )
                found += 1

    settings.tail_option_index = 0
    found = len(settings.tail_options)
    roots = len(_candidate_roots(settings))
    settings.tail_option_note = (
        f"{found} tail chain(s): {live_found} from the live roster, {imported}/{scanned} "
        f"extracted skeletons opened across {roots} folder(s)"
    )
    return found


def start_discover(settings) -> str:
    """Start a tail scan without running S2V on the main thread.

    The live skeleton cache is the only expensive step, and it is a subprocess,
    so it runs through the existing background job.  The scan itself is scheduled
    as a timer after it returns.  A cached roster is scanned immediately.
    """
    if jobs.is_running() or _SCAN_TIMER is not None:
        raise RuntimeError("tail-scan-busy: another background job is already running")
    settings.tail_options.clear()
    settings.tail_option_index = 0
    settings.tail_option_note = "scanning tail sources"
    root = _live_root(settings)
    cached = live.tail_skeleton_files(root)
    try:
        env = core.detect_environment(settings, core.core(settings))
    except Exception:
        env = None
    if cached and (env is None or live.tail_skeleton_cache_fresh(env, root)):
        _schedule_scan(settings, cached)
        return f"Scanning {len(cached)} cached live hero skeletons"
    if env is not None and env.s2v is not None and env.vpk is not None:
        def work(progress):
            progress(0.1, "decompiling live hero skeletons")
            return live.extract_tail_skeletons(env, root)

        def done(files):
            settings.tail_option_note = f"reading {len(files)} live hero skeletons"
            _schedule_scan(settings, files)

        def failed(error):
            settings.tail_option_note = f"live skeleton scan failed: {error}"
            _schedule_scan(settings, [])

        message = jobs.start(settings, "Scanning live heroes for tails", work, done, failed)
        if message:
            raise RuntimeError(message)
        return "Decompiling all live hero skeletons; the viewport stays responsive"
    _schedule_scan(settings, [])
    return "Scanning extracted folders only; set the live game and S2V to include every hero"


def _schedule_scan(settings, files: list[Path]) -> None:
    global _SCAN_TIMER
    if _SCAN_TIMER is not None:
        return
    try:
        job = _TailScanJob(settings, files)
    except Exception:
        # Construction settles the failed job before re-raising. Keep the
        # callback quiet so a S2V completion cannot leave a red traceback in
        # Blender while the page still shows the failure.
        return
    _SCAN_TIMER = job


def _release_scan_job(job=None) -> None:
    """Clear the module guard for this job, or for a setup failure."""
    global _SCAN_TIMER
    if job is None or _SCAN_TIMER is job:
        _SCAN_TIMER = None


def _settle_scan_failure(settings, error, job=None) -> None:
    """Always leave a failed scan with job_running false.

    A constructor or first timer tick can fail before the normal tick
    exception path exists.  Setting job_running first is deliberate: even if
    one of the later display fields is gone, the UI must not stay locked.
    """
    try:
        settings.job_running = False
    except Exception:
        pass
    try:
        settings.tail_option_note = f"Tail scan failed: {error}"
        settings.job_state = "FAILED"
        settings.job_message = str(error)
        lines = settings.job_log.splitlines()[-6:]
        settings.job_log = "\n".join([*lines, f"failed: {error}"])
    except Exception:
        pass
    finally:
        _release_scan_job(job)


class _TailScanJob:
    """Chunked scan: one DMX import or live skeleton per timer tick.

    The old path imported every candidate extraction in one timer callback, so
    Blender stopped drawing until the whole corpus had been opened. The file
    reads are cheap; the Blender imports are not. This keeps each tick bounded,
    reports the same job card as the other pages, and lets the viewport breathe
    between candidates.
    """

    def __init__(self, settings, files):
        self.settings = settings
        self.live_files = []
        self.live_index = 0
        self.live_found = 0
        self.roots = []
        self.root_index = 0
        self.files = None
        self.best: dict[Path, dict[str, tuple[Path, list[str]]]] = {}
        self.imports: list[tuple[str, Path, list[str]]] = []
        self.import_index = 0
        self.scanned = 0
        self.imported = 0
        self._timer = None
        try:
            self.live_files = [Path(path) for path in (files or [])]
            settings.tail_options.clear()
            settings.tail_option_index = 0
            settings.job_running = True
            settings.job_kind = "TAIL_SCAN"
            settings.job_label = "Scanning tail sources"
            settings.job_message = "reading local rigs"
            settings.job_progress = 0.02
            settings.job_state = "RUNNING"
            settings.job_cancellable = False
            settings.job_log = "Scanning tail sources: reading local rigs"
            self.roots = _candidate_roots(settings)
            self._known_rigs()
            self._timer = bpy.app.timers.register(self.tick, first_interval=0.02, persistent=True)
        except Exception as error:
            _settle_scan_failure(settings, error, self)
            raise

    def _known_rigs(self) -> None:
        settings = self.settings
        hero = settings.target_armature
        if hero is not None and hero.type == "ARMATURE":
            for chain in _chains(hero):
                _add_option(
                    settings,
                    label=f"{hero.name} / {chain.name}",
                    source="HERO",
                    path=settings.body_dmx,
                    chain=chain,
                    points=_points(hero, chain),
                )
        custom = settings.custom_armature
        if custom is not None and custom.type == "ARMATURE" and custom != hero:
            for chain in _chains(custom):
                _add_option(
                    settings,
                    label=f"{custom.name} / {chain.name}",
                    source="CUSTOM",
                    path="",
                    chain=chain,
                    points=_points(custom, chain),
                    armature=custom,
                )

    def _progress(self, value: float, message: str) -> None:
        settings = self.settings
        settings.job_progress = max(settings.job_progress, min(0.99, value))
        settings.job_message = message
        settings.tail_option_note = message
        lines = settings.job_log.splitlines()[-6:]
        settings.job_log = "\n".join([*lines, message])

    def tick(self):
        try:
            settings = self.settings
            if self.live_index < len(self.live_files):
                path = self.live_files[self.live_index]
                self.live_found += _add_live_skeletons(settings, [path])
                self.live_index += 1
                total = max(1, len(self.live_files))
                self._progress(0.04 + 0.24 * self.live_index / total, f"reading live skeletons {self.live_index}/{total}")
                return 0.01
            if self.root_index < len(self.roots):
                root = self.roots[self.root_index]
                if self.files is None:
                    self.files = root.rglob("*.dmx")
                try:
                    path = next(self.files)
                except StopIteration:
                    self.files = None
                    self.root_index += 1
                    fraction = self.root_index / max(1, len(self.roots))
                    self._progress(0.28 + 0.22 * fraction, f"scanned {self.root_index}/{len(self.roots)} folders")
                    return 0.01
                if not path.name.startswith("_."):
                    names = tailscan.dmx_bone_names(path)
                    if len(names) >= 2:
                        key = _hero_key(root, path)
                        best = self.best.setdefault(root, {})
                        if key not in best or _candidate_rank(path, names) > _candidate_rank(*best[key]):
                            best[key] = (path, names)
                return 0.005
            if not self.imports:
                for root in self.roots:
                    for key, (path, names) in sorted(self.best.get(root, {}).items()):
                        self.imports.append((key, path, names))
                if not self.imports:
                    self._finish()
                    return None
            if self.import_index < len(self.imports):
                key, path, names = self.imports[self.import_index]
                self.scanned += 1
                loaded = _import_candidate(path)
                if loaded is None:
                    for chain in tailscan.chains(names):
                        _add_option(
                            settings,
                            label=f"{key} / {chain.name}",
                            source="CLIP",
                            path=path,
                            chain=chain,
                            points=[(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)],
                        )
                else:
                    armature, chains, points = loaded
                    self.imported += 1
                    for chain in chains:
                        _add_option(
                            settings,
                            label=f"{key} / {chain.name}",
                            source="BODY" if live.looks_like_body(path) else "CLIP",
                            path=path,
                            chain=chain,
                            points=points.get(chain.name, []),
                        )
                self.import_index += 1
                total = max(1, len(self.imports))
                self._progress(0.52 + 0.45 * self.import_index / total, f"opening {key} ({self.import_index}/{total})")
                return 0.01
            self._finish()
            return None
        except Exception as error:
            self._fail(error)
            return None

    def _finish(self) -> None:
        global _SCAN_TIMER
        settings = self.settings
        try:
            settings.job_running = False
            found = len(settings.tail_options)
            settings.tail_option_index = 0
            settings.tail_option_note = (
                f"{found} tail chain(s): {self.live_found} from the live roster, "
                f"{self.imported}/{self.scanned} extracted skeletons opened across "
                f"{len(self.roots)} folder(s)"
            )
            settings.job_progress = 1.0
            settings.job_message = "done"
            settings.job_state = "DONE"
            lines = settings.job_log.splitlines()[-6:]
            settings.job_log = "\n".join([*lines, f"done: {settings.tail_option_note}"])
        finally:
            _release_scan_job(self)

    def _fail(self, error) -> None:
        _settle_scan_failure(self.settings, error, self)


def load_option(settings, index: int) -> str:
    """Load the chosen tile as the tail armature and map the hero channels."""
    if not settings.tail_options:
        raise RuntimeError("tail-options-empty: scan for tails first")
    option = settings.tail_options[max(0, min(index, len(settings.tail_options) - 1))]
    if option.rig is not None:
        settings.tail_armature = option.rig
    elif option.source == "HERO" and settings.target_armature is not None:
        source = settings.target_armature
        rig = bpy.data.objects.new(f"DMF Tail {option.chain}", source.data.copy())
        bpy.context.scene.collection.objects.link(rig)
        option.rig = rig
        settings.tail_armature = rig
    elif option.source == "CUSTOM":
        settings.tail_armature = settings.custom_armature
    else:
        path = Path(bpy.path.abspath(option.path)) if option.path else None
        if path is None or not path.is_file():
            raise RuntimeError(f"tail-source-missing: {option.path}")
        before = {obj.name for obj in bpy.context.scene.objects}
        source2.import_dmx(path, append="NEW_ARMATURE")
        armatures = [
            obj for obj in bpy.context.scene.objects
            if obj.name not in before and obj.type == "ARMATURE"
        ]
        if not armatures:
            raise RuntimeError(f"tail-import-empty: {path.name} produced no armature")
        rig = max(armatures, key=lambda item: len(item.data.bones))
        for obj in [obj for obj in bpy.context.scene.objects if obj.name not in before]:
            if obj.type == "MESH":
                bpy.data.objects.remove(obj, do_unlink=True)
        rig.name = f"DMF Tail {option.chain}"
        option.rig = rig
        settings.tail_armature = rig
    if settings.tail_armature is None:
        raise RuntimeError("tail-no-rig: the chosen tail has no armature")
    if settings.target_armature is None:
        settings.tail_note = f"{option.label}: tail rig loaded; import the hero to map channels"
        return settings.tail_note
    count = scan(settings)
    return f"{option.label}: {count} hero channels on {settings.tail_armature.name}"


def preview(settings) -> None:
    armature = settings.tail_armature
    if armature is None:
        return
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    armature.hide_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    if bpy.context.area is not None and bpy.context.area.type == "VIEW_3D":
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
        except Exception:
            pass


def source_row(settings):
    """The clip the Tails page will write, never an implicit list selection."""
    imported = [row for row in settings.clips if row.action and row.state in ("IMPORTED", "WRITTEN")]
    value = getattr(settings, "tail_clip", "NONE")
    if value not in ("", "NONE"):
        try:
            index = int(value)
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < len(settings.clips):
            row = settings.clips[index]
            if row.action:
                return row
    if len(imported) == 1:
        target = imported[0]
        for index, row in enumerate(settings.clips):
            if row.path == target.path and row.action == target.action:
                settings.tail_clip = str(index)
                break
        return target
    return None


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


class DMF_OT_scan_tails(Operator):
    bl_idname = "dmf.scan_tails"
    bl_label = "Scan Tail Sources"
    bl_description = "Find tail chains on this hero, the custom rig, sibling extractions and AG1/AG2 clips"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            message = start_discover(settings)
        except Exception as error:
            self.report({"ERROR"}, f"Tail scan failed: {error}")
            settings.tail_option_note = f"Tail scan failed: {error}"
            return {"CANCELLED"}
        self.report({"INFO"}, message)
        return {"FINISHED"}


class DMF_OT_load_tail_option(Operator):
    bl_idname = "dmf.load_tail_option"
    bl_label = "Use Tail"
    bl_description = "Load this tail skeleton as the tail rig and pair its channels"

    index: bpy.props.IntProperty(name="Tail", default=-1)

    def execute(self, context):
        settings = context.scene.dmf
        if self.index >= 0:
            settings.tail_option_index = min(self.index, len(settings.tail_options) - 1)
        try:
            message = load_option(settings, settings.tail_option_index)
        except Exception as error:
            self.report({"ERROR"}, f"Tail load failed: {error}")
            settings.tail_note = f"Tail load failed: {error}"
            return {"CANCELLED"}
        self.report({"INFO"}, message)
        return {"FINISHED"}


class DMF_OT_preview_tail(Operator):
    bl_idname = "dmf.preview_tail"
    bl_label = "Frame Tail"
    bl_description = "Select and frame the chosen tail rig in the 3D view"

    def execute(self, context):
        preview(context.scene.dmf)
        return {"FINISHED"}


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
    bl_label = "Write Selected Clip Tail"
    bl_description = "Write the source clip named on the Tails page onto the tail armature (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            row = source_row(settings)
            if row is None:
                raise RuntimeError("tail-no-source: choose Source clip on the Tails page")
            result = blend(settings, row)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, settings.tail_note, "OK")
        self.report({"INFO"}, f"Wrote {result['frames']} frames onto {result['tail']}")
        return {"FINISHED"}


class DMF_OT_build_tail_animation(Operator):
    bl_idname = "dmf.build_tail_animation"
    bl_label = "Add Tail And Compile Clips"
    bl_description = (
        "Append the selected tail's bones, key its matching source motion into every "
        "imported hero clip, write each gameplay source DMX, then compile the paired "
        "vnmclips with CSDK13; the skeleton itself is not shipped"
    )

    def execute(self, context):
        settings = context.scene.dmf
        try:
            queued = start_auto(settings, publish=True)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(
            settings,
            f"Adding the tail to {queued} clips; the viewport stays usable",
            "BUSY",
        )
        return {"FINISHED"}


class DMF_OT_publish_tail_anims(Operator):
    bl_idname = "dmf.publish_tail_anims"
    bl_label = "Compile Already-Tailed Clips"
    bl_description = (
        "Write every already-keyed gameplay source DMX, prepare the compiler skeleton, "
        "and compile the paired vnmclips without shipping a vnmskel"
    )

    def execute(self, context):
        settings = context.scene.dmf
        try:
            result = publish_tail_anims(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if result.get("mode") == "tail-only":
            core.set_status(
                settings,
                f"Tail only: wrote the tail mesh and its bones to {result['skeleton']}; "
                "no clips and no .vnmskel",
                "OK",
            )
            return {"FINISHED"}
        core.set_status(
            settings,
            f"Wrote {result['written']} source DMXs; compiled {result['compiled']} vnmclips "
            + (f"; {result['failed']} failed" if result["failed"] else "")
            + f" into {result['game_addon']}",
            "OK" if not result["failed"] else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_blend_tail_all(Operator):
    bl_idname = "dmf.blend_tail_all"
    bl_label = "Write This Hero's Clip Tails"
    bl_description = "Write every imported clip from the current hero onto the tail armature; other heroes' clips are ignored (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        hero = clipops.hero_source(settings)
        rows = [
            row for row in settings.clips
            if row.action
            and row.state in ("IMPORTED", "WRITTEN")
            and (not hero or row.source_hero == hero)
        ]
        if not rows:
            core.set_status(settings, f"No imported clips for {hero or 'this hero'}; scan and import them first", "WARN")
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


CLASSES = (
    DMF_OT_scan_tails,
    DMF_OT_load_tail_option,
    DMF_OT_preview_tail,
    DMF_OT_scan_tail,
    DMF_OT_blend_tail,
    DMF_OT_blend_tail_all,
    DMF_OT_build_tail_animation,
    DMF_OT_publish_tail_anims,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)