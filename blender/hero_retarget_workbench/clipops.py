"""Clip import: bring an extraction's animation DMX files onto the hero rig.

The queue is driven by a Blender timer, one file per step, so a folder of several
hundred clips does not lock the interface and the progress line stays truthful.
Each imported clip records the action PulseSrcOps created for it, which is what
the prefix, preview and clear actions work from afterwards.
"""
from __future__ import annotations

from pathlib import Path

import bpy
from bpy.types import Operator
from forge import clips as clipscan

from . import core, proofing

_QUEUE: list[str] = []
_TIMER = None
_STEP_SECONDS = 0.05


def folder(settings) -> Path | None:
    value = settings.clips_dir or settings.extraction_dir
    if not value:
        return None
    return Path(bpy.path.abspath(value))


def scan(settings) -> dict[str, int]:
    """Read the clip folder into the panel rows; nothing is imported."""
    root = folder(settings)
    if root is None:
        raise RuntimeError("clip-folder-missing: set the clip folder or extract a hero first")
    if not root.is_dir():
        raise RuntimeError(f"clip-folder-missing: {root} is not a folder")
    rows = clipscan.scan(root)
    settings.clips.clear()
    for row in rows:
        entry = settings.clips.add()
        entry.name = row.name
        entry.label = row.label
        entry.kind = row.kind
        entry.compiled = row.compiled
        entry.path = str(row.path)
        entry.size = row.size
        entry.state = "EDITABLE" if row.editable else "OPAQUE"
    settings.clip_index = 0
    settings.clip_imported = 0
    return clipscan.summary(rows)


def _armature(settings):
    armature = settings.target_armature
    if armature is None:
        raise RuntimeError("clip-import-needs-hero: import the hero skeleton first")
    return armature


def _import_one(settings, entry) -> str:
    """Import one clip onto the hero rig and name the action after the clip."""
    armature = _armature(settings)
    path = Path(bpy.path.abspath(entry.path))
    if not path.is_file():
        raise RuntimeError(f"clip-missing: {entry.name} is no longer on disk")
    before = {action.name for action in bpy.data.actions}
    core.select_only(bpy.context, [armature])
    bpy.context.view_layer.objects.active = armature
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.import_scene.kst_dmx(filepath=str(path), append="APPEND")
    created = [action for action in bpy.data.actions if action.name not in before]
    if not created:
        raise RuntimeError(f"clip-no-action: PulseSrcOps read {entry.name} but created no action")
    action = created[0]
    if len(created) > 1:
        # PulseSrcOps can split one file per take; the file stem is the name that
        # has to survive, so the rest keep their own names with a suffix.
        for index, extra in enumerate(sorted(created[1:], key=lambda item: item.name)):
            extra.name = f"{entry.label}.{index + 1:02d}"
    action.name = entry.label
    if armature.animation_data is not None:
        armature.animation_data.action = action
        if hasattr(armature.animation_data, "action_slot") and getattr(action, "slots", None):
            armature.animation_data.action_slot = action.slots[0]
    entry.action = action.name
    entry.state = "IMPORTED"
    return action.name


def _tick():
    global _TIMER
    settings = _settings()
    if settings is None or not _QUEUE:
        _stop()
        return None
    index = _QUEUE.pop(0)
    if index >= len(settings.clips):
        return _STEP_SECONDS
    entry = settings.clips[index]
    try:
        _import_one(settings, entry)
        settings.clip_imported += 1
        core.set_status(settings, f"Imported {entry.label}; {len(_QUEUE)} left", "BUSY")
    except Exception as error:
        entry.state = "FAILED"
        entry.action = ""
        settings.clip_note = str(error)
        core.set_status(settings, f"{entry.label}: {error}", "WARN")
    if not _QUEUE:
        done = settings.clip_imported
        failed = sum(1 for row in settings.clips if row.state == "FAILED")
        core.set_status(
            settings,
            f"Imported {done} clips as actions; {failed} failed",
            "OK" if not failed else "WARN",
        )
        _stop()
    return _STEP_SECONDS


def _settings():
    scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "dmf", None) if scene is not None else None


def _stop() -> None:
    global _TIMER
    if _TIMER is not None:
        try:
            bpy.app.timers.unregister(_TIMER)
        except ValueError:
            pass
        _TIMER = None


def start(settings, only_index: int | None = None) -> int:
    """Queue every editable clip (or the selected one) and return how many were queued."""
    global _QUEUE, _TIMER
    _QUEUE = []
    # Fail here, with the reason, rather than once per queued file.
    _armature(settings)
    if only_index is not None:
        candidates = [only_index]
    else:
        candidates = [
            index for index, row in enumerate(settings.clips) if row.state in ("EDITABLE", "FAILED")
        ]
    if not candidates:
        raise RuntimeError("clip-import-empty: scan a folder with .dmx clips first")
    _QUEUE = list(candidates)
    if _TIMER is None:
        _TIMER = bpy.app.timers.register(_tick, first_interval=0.0, persistent=True)
    return len(_QUEUE)


def cancel() -> None:
    global _QUEUE
    _QUEUE = []
    _stop()


def is_running() -> bool:
    return _TIMER is not None


def clear_imported(settings) -> int:
    """Remove the actions this panel imported and reset their rows."""
    removed = 0
    for row in settings.clips:
        if row.state != "IMPORTED" or not row.action:
            continue
        action = bpy.data.actions.get(row.action)
        if action is not None:
            bpy.data.actions.remove(action)
            removed += 1
        row.action = ""
        row.state = "EDITABLE" if row.kind == "dmx" and not row.compiled else "OPAQUE"
    settings.clip_imported = 0
    return removed


def prefix_actions(settings, prefix: str) -> int:
    """Rename the imported actions with one prefix, idempotently."""
    changed = 0
    clean = (prefix or "").strip()
    for row in settings.clips:
        if not row.action:
            continue
        action = bpy.data.actions.get(row.action)
        if action is None:
            row.action = ""
            continue
        name = f"{clean}{row.label}" if clean else row.label
        if action.name != name:
            action.name = name
            row.action = action.name
            changed += 1
    return changed


def use_action(settings, index: int) -> str:
    row = settings.clips[max(0, min(index, len(settings.clips) - 1))]
    action = bpy.data.actions.get(row.action) if row.action else None
    if action is None:
        raise RuntimeError("clip-not-imported: import this clip before previewing it")
    settings.compare_action = action
    return action.name


class DMF_OT_scan_clips(Operator):
    bl_idname = "dmf.scan_clips"
    bl_label = "Scan Clips"
    bl_description = "List the animation clips under the clip folder and mark which ones Blender can import"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            counts = scan(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        settings.clip_note = (
            f"{counts['vnmclip']} vnmclip files stay untouched: they are compiled data, not animation DMX"
            if counts["vnmclip"]
            else ""
        )
        core.set_status(
            settings,
            f"{counts['dmx']} DMX / {counts['vnmclip']} vnmclip; {counts['paired']} pairs, {counts['dmx_only']} DMX only",
            "OK" if counts["editable"] else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_import_clips(Operator):
    bl_idname = "dmf.import_clips"
    bl_label = "Import All Clips"
    bl_description = "Import every editable clip DMX onto the hero rig as an action, one file per timer step"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            queued = start(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, f"Importing {queued} clips; the viewport stays usable", "BUSY")
        return {"FINISHED"}


class DMF_OT_import_clip(Operator):
    bl_idname = "dmf.import_clip"
    bl_label = "Import Clip"
    bl_description = "Import the selected clip onto the hero rig"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.clips:
            self.report({"ERROR"}, "Scan a clip folder first")
            return {"CANCELLED"}
        try:
            queued = start(settings, only_index=settings.clip_index)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, f"Importing one clip; {queued} queued", "BUSY")
        return {"FINISHED"}


class DMF_OT_cancel_clips(Operator):
    bl_idname = "dmf.cancel_clips"
    bl_label = "Stop Importing"
    bl_description = "Stop the clip queue; clips already imported keep their actions"

    def execute(self, context):
        settings = context.scene.dmf
        cancel()
        core.set_status(settings, f"Stopped the clip queue at {settings.clip_imported} imported", "INFO")
        return {"FINISHED"}


class DMF_OT_prefix_clips(Operator):
    bl_idname = "dmf.prefix_clips"
    bl_label = "Prefix Actions"
    bl_description = "Rename every imported action with the prefix, so a bulk edit is identifiable in the file"

    def execute(self, context):
        settings = context.scene.dmf
        changed = prefix_actions(settings, settings.clip_prefix)
        core.set_status(settings, f"Renamed {changed} imported actions" if changed else "No imported action to rename", "OK" if changed else "WARN")
        return {"FINISHED"}


class DMF_OT_clear_clips(Operator):
    bl_idname = "dmf.clear_clips"
    bl_label = "Clear Imported"
    bl_description = "Delete the actions this panel imported; the clip files on disk are not touched"

    def execute(self, context):
        settings = context.scene.dmf
        cancel()
        removed = clear_imported(settings)
        core.set_status(settings, f"Removed {removed} imported actions; the clips are untouched" if removed else "No imported action to remove", "INFO")
        return {"FINISHED"}


class DMF_OT_preview_clip(Operator):
    bl_idname = "dmf.preview_clip"
    bl_label = "Use As Preview"
    bl_description = "Make the selected clip's action the Compare preview action"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            name = use_action(settings, settings.clip_index)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, f"Preview action {name}; use Apply to both rigs in Compare", "OK")
        return {"FINISHED"}


CLASSES = (
    DMF_OT_scan_clips,
    DMF_OT_import_clips,
    DMF_OT_import_clip,
    DMF_OT_cancel_clips,
    DMF_OT_prefix_clips,
    DMF_OT_clear_clips,
    DMF_OT_preview_clip,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    cancel()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
