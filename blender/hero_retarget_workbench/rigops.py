"""Keep the custom model's own skinning when its weights are better than a solve.

Two fallbacks live here:

``use mapped names``
    Rename every mapped custom bone and its matching vertex group to the hero
    target name.  The custom mesh keeps its original weights and is bound to its
    own armature; no vertex weight is written.

``bake hero to custom``
    Do the rename automatically, then bake every imported hero action onto the
    custom armature by solved pose matrices.  The custom rig gets its own
    actions, a compiler skeleton DMX and a ``.vnmskel`` document.  The hero rig
    remains the animation source throughout.
"""
from __future__ import annotations

import re
from pathlib import Path

import bpy
from bpy.types import Operator
from mathutils import Matrix

from . import clipops, core, jobs, parts, proofing, tailops

_ACTIVE = None
_PREVIEW = None


class RigError(RuntimeError):
    pass


def _status(settings, message: str, kind: str = "INFO") -> None:
    core.set_status(settings, message, kind)


def mapped_pairs(settings) -> dict[str, str]:
    """Mapped source -> target names, refusing two sources on one target."""
    pairs: dict[str, str] = {}
    targets: dict[str, str] = {}
    for row in settings.bone_map:
        if row.state != "MAPPED":
            continue
        source = (row.source or "").strip()
        target = (row.target or "").strip()
        if not source or not target:
            continue
        if source == target:
            continue
        prior = targets.get(target)
        if prior is not None and prior != source:
            raise RigError(
                f"mapped-names-collision: {target} is the target of {prior} and {source}"
            )
        pairs[source] = target
        targets[target] = source
    return pairs


def _custom_meshes(settings) -> list:
    """The active custom mesh plus the collection parts, never the hero body."""
    found = []
    seen = set()
    for obj in (settings.custom_mesh, *parts.export_meshes(settings)):
        if obj is None or obj.type != "MESH" or obj.data is None:
            continue
        if obj == settings.target_body or obj.name in seen:
            continue
        seen.add(obj.name)
        found.append(obj)
    return found


def _source_presence(settings, pairs: dict[str, str]) -> tuple[set[str], set[str]]:
    """Sources that exist as custom bones and sources that exist as groups."""
    bones = set(settings.custom_armature.data.bones.keys()) if settings.custom_armature else set()
    groups: set[str] = set()
    for mesh in _custom_meshes(settings):
        groups.update(group.name for group in mesh.vertex_groups)
    return {source for source in pairs if source in bones}, {
        source for source in pairs if source in groups
    }


def _validate_names(settings, pairs: dict[str, str]) -> None:
    if not pairs:
        return
    bone_sources, group_sources = _source_presence(settings, pairs)
    if not bone_sources and not group_sources:
        raise RigError("mapped-names-source-missing: no mapped source exists on the custom model")
    if settings.custom_armature is not None:
        existing = set(settings.custom_armature.data.bones.keys())
        movable = {source for source in bone_sources if source in pairs}
        targets = {pairs[source] for source in movable}
        for target in targets:
            if target in existing and target not in movable:
                raise RigError(f"mapped-names-bone-occupied: {target} already exists on the custom rig")
    for mesh in _custom_meshes(settings):
        existing = set(mesh.vertex_groups.keys())
        movable = {source for source in group_sources if source in existing}
        for source in movable:
            target = pairs[source]
            if target in existing and target not in movable:
                raise RigError(
                    f"mapped-names-group-occupied: {target} already exists on {mesh.name}"
                )


def _temporary_names(names: set[str]) -> dict[str, str]:
    """Unique temporary names for a safe two-phase rename."""
    used = set(names)
    result = {}
    for index, name in enumerate(sorted(names)):
        candidate = f"__dmf_name_{index:04d}"
        while candidate in used:
            candidate += "_"
        used.add(candidate)
        result[name] = candidate
    return result


def _rename_bones(settings, pairs: dict[str, str]) -> int:
    armature = settings.custom_armature
    if armature is None:
        return 0
    existing = set(armature.data.bones.keys())
    movable = {source for source in pairs if source in existing}
    if not movable:
        return 0
    targets = {pairs[source] for source in movable}
    if len(targets) != len(movable):
        raise RigError("mapped-names-collision: two custom bones would get one target")
    temporary = _temporary_names(existing)
    core.select_only(bpy.context, [armature])
    bpy.context.view_layer.objects.active = armature
    if armature.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for source in movable:
            edit_bone = armature.data.edit_bones.get(source)
            if edit_bone is None:
                raise RigError(f"mapped-names-bone-missing: {source}")
            edit_bone.name = temporary[source]
        for source in movable:
            edit_bone = armature.data.edit_bones.get(temporary[source])
            if edit_bone is None:
                raise RigError(f"mapped-names-temporary-lost: {source}")
            edit_bone.name = pairs[source]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return len(movable)


def _rename_groups(settings, pairs: dict[str, str]) -> tuple[int, list]:
    meshes = _custom_meshes(settings)
    renamed = 0
    for mesh in meshes:
        existing = set(mesh.vertex_groups.keys())
        movable = {source for source in pairs if source in existing}
        # Blender already renames a vertex group when its bone is renamed.  Count
        # that case instead of reporting a second, silent rename.
        automatic = {
            source
            for source in pairs
            if source not in existing and pairs[source] in existing
        }
        if not movable:
            renamed += len(automatic)
            continue
        targets = {pairs[source] for source in movable}
        if len(targets) != len(movable):
            raise RigError(f"mapped-names-collision: two groups on {mesh.name} would get one target")
        temporary = _temporary_names(existing)
        for source in movable:
            mesh.vertex_groups[source].name = temporary[source]
        for source in movable:
            mesh.vertex_groups[temporary[source]].name = pairs[source]
        renamed += len(movable) + len(automatic)
    return renamed, meshes


def _bind_custom(settings, meshes) -> int:
    armature = settings.custom_armature
    if armature is None:
        return 0
    bound = 0
    for mesh in meshes:
        for modifier in list(mesh.modifiers):
            if modifier.type != "ARMATURE":
                continue
            if modifier.object == armature:
                modifier.use_vertex_groups = True
                bound += 1
                continue
            mesh.modifiers.remove(modifier)
        if not any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in mesh.modifiers
        ):
            modifier = mesh.modifiers.new(name="Deadlock Custom Armature", type="ARMATURE")
            modifier.object = armature
            modifier.use_vertex_groups = True
            bound += 1
    return bound


def _update_map(settings, pairs: dict[str, str]) -> None:
    for row in settings.bone_map:
        source = (row.source or "").strip()
        if source not in pairs:
            continue
        row.source = pairs[source]
        row.target = row.source
        row.state = "MAPPED"
        row.note = "renamed in place; original weights kept"


def apply_mapped_names(settings) -> dict:
    """Rename mapped custom bones/groups and keep every original weight.

    The mesh is rebound to the custom armature with the renamed groups.  The
    target hero rig is not modified and no weight map is solved or normalized.
    """
    armature = settings.custom_armature
    if armature is None:
        raise RigError("mapped-names-needs-rig: choose the custom armature first")
    if settings.custom_mesh is None:
        raise RigError("mapped-names-needs-mesh: choose the custom mesh first")
    pairs = mapped_pairs(settings)
    mapped_rows = any(
        row.state == "MAPPED" and row.source and row.target for row in settings.bone_map
    )
    if not pairs and not mapped_rows:
        raise RigError("mapped-names-empty: map at least one custom bone or group to a hero target")
    _validate_names(settings, pairs)
    bones = _rename_bones(settings, pairs)
    groups, meshes = _rename_groups(settings, pairs)
    _update_map(settings, pairs)
    bound = _bind_custom(settings, meshes)
    proofing.bump_tick(settings)
    return {
        "bones": bones,
        "groups": groups,
        "meshes": len(meshes),
        "bound": bound,
        "pairs": pairs,
    }


def _preview_action(settings):
    hero = settings.target_armature
    action = getattr(settings, "hand_preview_action", None) or settings.compare_action
    if action is None and settings.clips:
        index = max(0, min(int(settings.clip_index), len(settings.clips) - 1))
        row = settings.clips[index]
        action = bpy.data.actions.get(row.action) if row.action else None
    if action is None and hero is not None and hero.animation_data is not None:
        action = hero.animation_data.action
    return action


def _set_action(armature, action):
    data = armature.animation_data or armature.animation_data_create()
    data.action = action
    if action is not None and hasattr(data, "action_slot") and getattr(action, "slots", None):
        data.action_slot = action.slots[0]
    return data


def _frame(scene, _depsgraph=None):
    session = _PREVIEW
    if session is None:
        return
    try:
        session.apply()
    except Exception as error:
        session.settings.hand_preview_note = f"Hand preview stopped at frame {scene.frame_current}: {error}"


def _on_load(*_args) -> None:
    """A loaded file owns new objects; do not keep a handler from the old one."""
    global _PREVIEW
    if _PREVIEW is not None:
        try:
            _PREVIEW.stop(restore=False)
        except Exception:
            pass
        _PREVIEW = None


class _HandPreview:
    """Live action preview with in-memory hand nudges; no action is keyed."""

    def __init__(self, settings, action):
        self.settings = settings
        self.scene = bpy.context.scene
        self.hero = settings.target_armature
        self.custom = settings.custom_armature
        self.action = action
        self.offsets: dict[str, list[tuple[bool, int, float]]] = {}
        self._applying = False
        self._custom_had_data = self.custom.animation_data is not None
        self._hero_had_data = self.hero.animation_data is not None
        self._custom_action = self.custom.animation_data.action if self._custom_had_data else None
        self._custom_slot = (
            getattr(self.custom.animation_data, "action_slot", None) if self._custom_had_data else None
        )
        self._hero_action = self.hero.animation_data.action if self._hero_had_data else None
        self._hero_slot = getattr(self.hero.animation_data, "action_slot", None) if self._hero_had_data else None
        self._hero_nla = self.hero.animation_data.use_nla if self._hero_had_data else False
        self._custom_nla = self.custom.animation_data.use_nla if self._custom_had_data else False
        self._pose = {
            bone.name: (bone.rotation_mode, bone.matrix_basis.copy()) for bone in self.custom.pose.bones
        }
        self._pose_position = self.custom.data.pose_position
        self._hero_pose_position = self.hero.data.pose_position
        self._frame = self.scene.frame_current
        self._range = (self.scene.frame_start, self.scene.frame_end)
        start, end = (int(round(value)) for value in action.frame_range)
        if end <= start:
            raise RigError("hand-preview-empty-range: the action has no frame range")
        try:
            _set_action(self.hero, action)
            self.hero.animation_data.use_nla = False
            self.hero.data.pose_position = "POSE"
            custom_data = self.custom.animation_data_create()
            custom_data.action = None
            custom_data.use_nla = False
            self.custom.data.pose_position = "POSE"
            self.scene.frame_start = start
            self.scene.frame_end = end
            if self.scene.frame_current < start or self.scene.frame_current > end:
                self.scene.frame_set(start)
            bpy.app.handlers.frame_change_post.append(_frame)
        except Exception:
            self.stop(restore=True)
            raise

    def apply(self):
        if self._applying:
            return
        self._applying = True
        try:
            bpy.context.view_layer.update()
            tailops.apply_retarget_pose(self.custom, self.hero)
            for name, records in self.offsets.items():
                bone = self.custom.pose.bones.get(name)
                if bone is None:
                    continue
                basis = bone.matrix_basis.copy()
                for rotate, axis, amount in records:
                    if rotate:
                        basis = basis @ Matrix.Rotation(amount, 4, "XYZ"[axis])
                    else:
                        basis.translation[axis] += amount
                bone.matrix_basis = basis
            bpy.context.view_layer.update()
        finally:
            self._applying = False

    def nudge(self, bone_name: str, axis: int, amount: float, rotate: bool) -> None:
        self.offsets.setdefault(bone_name, []).append((bool(rotate), int(axis), float(amount)))
        self.apply()
        jobs._tag_redraw()

    def reset(self) -> None:
        self.offsets.clear()
        self.apply()
        jobs._tag_redraw()

    def stop(self, *, restore: bool = True) -> None:
        global _PREVIEW
        if _PREVIEW is self:
            _PREVIEW = None
        while _frame in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(_frame)
        if restore:
            self.scene.frame_start, self.scene.frame_end = self._range
            if self._hero_had_data:
                _set_action(self.hero, self._hero_action)
                if self._hero_action is not None and hasattr(self.hero.animation_data, "action_slot"):
                    self.hero.animation_data.action_slot = self._hero_slot
                self.hero.animation_data.use_nla = self._hero_nla
            else:
                self.hero.animation_data_clear()
            if self._custom_had_data:
                _set_action(self.custom, self._custom_action)
                if self._custom_action is not None and hasattr(self.custom.animation_data, "action_slot"):
                    self.custom.animation_data.action_slot = self._custom_slot
                self.custom.animation_data.use_nla = self._custom_nla
            else:
                self.custom.animation_data_clear()
            self.custom.data.pose_position = self._pose_position
            self.hero.data.pose_position = self._hero_pose_position
            self.scene.frame_set(self._frame)
            for name, (mode, basis) in self._pose.items():
                bone = self.custom.pose.bones.get(name)
                if bone is not None:
                    bone.rotation_mode = mode
                    bone.matrix_basis = basis
            bpy.context.view_layer.update()
        self.settings.hand_preview_active = False
        self.settings.hand_preview_note = (
            "Hand preview stopped; the action, pose and frame range were restored"
            if restore
            else "Hand preview stopped"
        )
        jobs._tag_redraw()


def start_hand_preview(settings) -> str:
    global _PREVIEW
    if settings.job_running or _ACTIVE is not None:
        raise RigError("hand-preview-job-running: wait for the current job before previewing")
    if _PREVIEW is not None:
        _PREVIEW.stop()
    if settings.target_armature is None or settings.custom_armature is None:
        raise RigError("hand-preview-needs-rigs: choose the hero and custom armatures")
    if settings.target_armature == settings.custom_armature:
        raise RigError("hand-preview-same-rig: the custom armature is already the target")
    action = _preview_action(settings)
    if action is None:
        raise RigError("hand-preview-needs-action: choose or import a hero action")
    _PREVIEW = _HandPreview(settings, action)
    settings.hand_preview_active = True
    settings.hand_preview_note = (
        f"Previewing {action.name}; nudge the selected hand or finger row. No keys are written"
    )
    jobs._tag_redraw()
    return action.name


def stop_hand_preview(settings) -> bool:
    if _PREVIEW is None:
        settings.hand_preview_active = False
        return False
    _PREVIEW.stop()
    return True


def nudge_hand_preview(settings, bone_name: str, axis: int, amount: float, rotate: bool) -> bool:
    if _PREVIEW is None:
        return False
    _PREVIEW.nudge(bone_name, axis, amount, rotate)
    settings.hand_preview_note = (
        f"Previewing {_PREVIEW.action.name}; nudged {bone_name} {settings.nudge_axis} "
        f"{amount:+.4f}. No keys written"
    )
    jobs._tag_redraw()
    return True


def reset_hand_nudges(settings) -> bool:
    if _PREVIEW is None:
        return False
    _PREVIEW.reset()
    settings.hand_preview_note = "Hand preview nudges reset; no keys written"
    jobs._tag_redraw()
    return True


def action_rows(settings) -> list[tuple[object, object]]:
    """Imported clip rows paired with their live hero actions."""
    found = []
    for row in settings.clips:
        if not row.action:
            continue
        action = bpy.data.actions.get(row.action)
        if action is not None:
            found.append((row, action))
    return found


def output_folder(settings) -> Path:
    if getattr(settings, "custom_bake_dir", ""):
        return Path(bpy.path.abspath(settings.custom_bake_dir))
    slug = getattr(settings, "hero_slug", "") or ""
    if slug in ("", "NONE"):
        armature = settings.target_armature
        slug = armature.name if armature is not None else "custom"
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", slug).strip("._") or "custom"
    return Path(core.project_root(settings)) / "artifacts" / "custom-anim" / slug


def _safe_label(row, index: int) -> str:
    label = (getattr(row, "label", "") or getattr(row, "name", "") or f"clip_{index}").strip()
    label = Path(label).name
    return label or f"clip_{index}"


def _bake_one(settings, custom, hero, row, action, output: Path, index: int, *, write: bool) -> dict:
    label = _safe_label(row, index)
    baked = tailops._bake_body_action(custom, hero, action, f"{label} custom")
    written = None
    if write:
        old_target = settings.target_armature
        old_action = row.action
        old_state = row.state
        old_exported = row.exported
        settings.target_armature = custom
        row.action = baked.name
        try:
            target = output / "clips" / f"{label}.dmx"
            written = clipops.write_action(settings, row, output, target=target)
        finally:
            settings.target_armature = old_target
            row.action = old_action
            row.state = old_state
            row.exported = old_exported
    return {"row": row, "label": label, "action": baked, "written": written}


def _vnmskel_source(settings) -> Path | None:
    value = getattr(settings, "clip_vnmskel", "")
    if value:
        path = Path(bpy.path.abspath(value))
        if path.is_file():
            return path
    body = Path(bpy.path.abspath(settings.body_dmx)) if settings.body_dmx else None
    if body is not None:
        found = sorted(body.parent.glob("*.vnmskel"))
        if found:
            return found[0]
    extraction = Path(bpy.path.abspath(settings.extraction_dir)) if settings.extraction_dir else None
    if extraction is not None and extraction.is_dir():
        found = sorted(extraction.rglob("*.vnmskel"))
        if found:
            return found[0]
    return None


def export_bundle(settings, output: Path) -> dict:
    """Export the custom armature as a skeleton DMX and point a vnmskel at it."""
    from forge import animgraph

    custom = settings.custom_armature
    hero = settings.target_armature
    if custom is None or hero is None:
        raise RigError("custom-bake-needs-rigs: choose the hero and custom armatures")
    slug = getattr(settings, "hero_slug", "") or ""
    if slug in ("", "NONE"):
        slug = hero.name
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", slug).strip("._") or "custom"
    root = output / "models" / "heroes_staging" / slug
    skeleton = root / "dmx" / "mesh" / f"{slug}_custom_skel.dmx"
    skeleton.parent.mkdir(parents=True, exist_ok=True)
    old_target = settings.target_armature
    settings.target_armature = custom
    try:
        tailops.export_tail_skeleton(settings, skeleton)
    finally:
        settings.target_armature = old_target
    source = _vnmskel_source(settings)
    document = None
    if source is not None and source.is_file():
        relative = skeleton.relative_to(output).as_posix()
        text = source.read_text(encoding="utf-8", errors="replace")
        document = root / f"{slug}_custom.vnmskel"
        document.write_text(animgraph.point_skeleton(text, relative), encoding="utf-8")
    return {"skeleton": skeleton, "vnmskel": document}


def bake_all(
    settings,
    output: Path | None = None,
    *,
    write: bool = False,
    bundle: bool = True,
    progress=None,
) -> dict:
    """Synchronous path used by the probe; production uses the timer job."""
    hero = settings.target_armature
    custom = settings.custom_armature
    if hero is None or custom is None:
        raise RigError("custom-bake-needs-rigs: choose the hero and custom armatures")
    if hero == custom:
        raise RigError("custom-bake-same-rig: the custom armature is already the target")
    rows = action_rows(settings)
    if not rows:
        raise RigError("custom-bake-needs-clips: import the hero's clips first")
    output = Path(output) if output is not None else output_folder(settings)
    output.mkdir(parents=True, exist_ok=True)
    apply_mapped_names(settings)
    baked = []
    for index, (row, action) in enumerate(rows):
        baked.append(_bake_one(settings, custom, hero, row, action, output, index, write=write))
        if progress is not None:
            progress((index + 1) / len(rows), f"Baked {index + 1} of {len(rows)} clips")
    exported = export_bundle(settings, output) if bundle else {}
    return {"actions": baked, "output": output, **exported}


class _BakeJob:
    """One action per timer tick: a folder of clips must not freeze the UI."""

    def __init__(self, settings, rows, output: Path):
        self.settings = settings
        self.rows = list(rows)
        self.output = output
        self.hero = settings.target_armature
        self.custom = settings.custom_armature
        self.done = 0
        self.failures: list[str] = []
        self.baked = []
        settings.job_running = True
        settings.job_kind = "CUSTOM_BAKE"
        settings.job_label = "Bake hero to custom"
        settings.job_message = f"Baking 1 of {len(self.rows)} clips"
        settings.job_progress = 0.0
        settings.job_cancellable = False
        settings.job_state = "RUNNING"
        self._timer = bpy.app.timers.register(self._tick, first_interval=0.01, persistent=True)

    def _tick(self):
        global _ACTIVE
        if _ACTIVE is not self:
            return None
        if not self.rows:
            return self._finish()
        row, action = self.rows.pop(0)
        index = self.done
        self.done += 1
        try:
            self.baked.append(
                _bake_one(self.settings, self.custom, self.hero, row, action, self.output, index, write=True)
            )
        except Exception as error:
            self.failures.append(f"{row.label or row.name}: {error}")
        self.settings.job_progress = self.done / max(1, self.done + len(self.rows))
        self.settings.job_message = f"Baked {self.done} of {self.done + len(self.rows)} clips"
        jobs._tag_redraw()
        return 0.01

    def _finish(self):
        global _ACTIVE
        try:
            self.settings.job_message = "Writing custom skeleton"
            bundle = export_bundle(self.settings, self.output)
            self.settings.job_progress = 1.0
            self.settings.job_state = "DONE" if not self.failures else "WARN"
            self.settings.custom_bake_note = (
                f"Baked {len(self.baked)} clips; custom skeleton {bundle['skeleton']}"
            )
            _status(
                self.settings,
                f"Baked {len(self.baked)} clips to the custom armature; "
                f"{len(self.failures)} failed; bundle {self.output}",
                "OK" if not self.failures else "WARN",
            )
            self.settings.clip_note = self.settings.custom_bake_note
        except Exception as error:
            self.settings.job_state = "FAILED"
            self.settings.custom_bake_note = str(error)
            _status(self.settings, f"Custom bake failed: {error}", "ERROR")
        finally:
            self.settings.job_running = False
            self.settings.job_cancellable = False
            _ACTIVE = None
            jobs._tag_redraw()
        return None


def start_custom_bake(settings) -> int:
    global _ACTIVE
    if settings.job_running or _ACTIVE is not None:
        raise RigError("custom-bake-running: another job is already running")
    hero = settings.target_armature
    custom = settings.custom_armature
    if hero is None or custom is None:
        raise RigError("custom-bake-needs-rigs: choose the hero and custom armatures")
    if hero == custom:
        raise RigError("custom-bake-same-rig: the custom armature is already the target")
    if settings.custom_mesh is None:
        raise RigError("custom-bake-needs-mesh: choose the custom mesh first")
    rows = action_rows(settings)
    if not rows:
        raise RigError("custom-bake-needs-clips: import the hero's clips first")
    output = output_folder(settings)
    output.mkdir(parents=True, exist_ok=True)
    apply_mapped_names(settings)
    _ACTIVE = _BakeJob(settings, rows, output)
    return len(rows)


class DMF_OT_use_mapped_names(Operator):
    bl_idname = "dmf.use_mapped_names"
    bl_label = "Use Mapped Names"
    bl_description = "Rename mapped custom bones and vertex groups to the hero names; keep the original weights and bind the custom armature"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            result = apply_mapped_names(settings)
            _status(
                settings,
                f"Kept original weights; renamed {result['bones']} bones and "
                f"{result['groups']} groups on {result['meshes']} meshes",
                "OK",
            )
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_preview_hands(Operator):
    bl_idname = "dmf.preview_hands"
    bl_label = "Preview Hands"
    bl_description = "Play the chosen hero action on the custom rig without keying; nudge hands live, then stop to restore the pose"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            if _PREVIEW is not None:
                stop_hand_preview(settings)
                _status(settings, "Hand preview stopped; the pose and actions were restored", "OK")
            else:
                name = start_hand_preview(settings)
                _status(settings, f"Hand preview running {name}; nudge the selected hand row", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_reset_hand_nudges(Operator):
    bl_idname = "dmf.reset_hand_nudges"
    bl_label = "Reset Hand Nudges"
    bl_description = "Clear the in-memory nudge offsets in the hand preview; no action is changed"

    def execute(self, context):
        settings = context.scene.dmf
        if not reset_hand_nudges(settings):
            _status(settings, "Start the hand preview before resetting its nudges", "INFO")
        return {"FINISHED"}


class DMF_OT_bake_custom_rig(Operator):
    bl_idname = "dmf.bake_custom_rig"
    bl_label = "Bake Hero to Custom"
    bl_description = "Rename mapped bones automatically, bake every imported hero action onto the custom armature, and write a custom skeleton and vnmskel"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = start_custom_bake(settings)
            _status(settings, f"Baking {count} hero clips onto the custom armature", "BUSY")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (
    DMF_OT_use_mapped_names,
    DMF_OT_preview_hands,
    DMF_OT_reset_hand_nudges,
    DMF_OT_bake_custom_rig,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister() -> None:
    global _ACTIVE, _PREVIEW
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _PREVIEW is not None:
        try:
            _PREVIEW.stop()
        except Exception:
            pass
        _PREVIEW = None
    if _ACTIVE is not None:
        try:
            bpy.app.timers.unregister(_ACTIVE._timer)
        except Exception:
            pass
        _ACTIVE = None
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
