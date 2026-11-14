"""Clip import and write-back: animation DMX onto the hero rig, and back out.

The queue is driven by a Blender timer, one file per step, so a folder of several
hundred clips does not lock the interface and the progress line stays truthful.
Each imported clip records the action PulseSrcOps created for it, which is what
the prefix, preview, export and clear actions work from afterwards.

Writing a clip is one PulseSrcOps animation export per row: the armature is the
only exportable, the action filter names that one action, and PulseSrcOps writes
``<root>/anims/<action>.dmx``. The action, the export list and the scene's export
settings are saved and put back, so an export never becomes the file's state.
"""
from __future__ import annotations

import os
from pathlib import Path

import bpy
from bpy.types import Operator
from forge import clips as clipscan

from . import core, proofing

_QUEUE: list[int] = []
_TIMER = None
_MODE = "import"
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
    exporting = _MODE == "export"
    try:
        if exporting:
            written = write_action(settings, entry, write_folder(settings))
            settings.clip_written += 1
            core.set_status(
                settings,
                f"Wrote {written.name} ({entry.export_bytes:,} bytes); {len(_QUEUE)} left",
                "BUSY",
            )
        else:
            _import_one(settings, entry)
            settings.clip_imported += 1
            core.set_status(settings, f"Imported {entry.label}; {len(_QUEUE)} left", "BUSY")
    except Exception as error:
        entry.state = "FAILED"
        if not exporting:
            entry.action = ""
        settings.clip_note = str(error)
        core.set_status(settings, f"{entry.label}: {error}", "WARN")
    if not _QUEUE:
        failed = sum(1 for row in settings.clips if row.state == "FAILED")
        if exporting:
            core.set_status(
                settings,
                f"Wrote {settings.clip_written} clips to {write_folder(settings)}; {failed} failed",
                "OK" if not failed else "WARN",
            )
        else:
            core.set_status(
                settings,
                f"Imported {settings.clip_imported} clips as actions; {failed} failed",
                "OK" if not failed else "WARN",
            )
        _stop()
    return _STEP_SECONDS


def write_folder(settings) -> Path:
    """The folder written clips go to; an empty field means ``<clip folder>/edited``."""
    root = clipscan.export_folder(folder(settings), settings.clip_export_dir or None)
    if root is None:
        raise RuntimeError(
            "clip-export-folder-missing: set the clip folder or a write folder first"
        )
    return Path(bpy.path.abspath(str(root)))


def _snapshot(scene, armature) -> dict:
    data = armature.animation_data
    return {
        "export_path": scene.vs.export_path,
        "export_format": scene.vs.export_format,
        "engine": scene.vs.engine,
        "dmx_format": scene.vs.dmx_format,
        "dmx_encoding": scene.vs.dmx_encoding,
        "export_list": [
            (row.name, row.ob_type, getattr(row, "icon", ""), row.obj, row.collection)
            for row in scene.vs.export_list
        ],
        "action_selection": armature.data.vs.action_selection,
        "action_filter": armature.vs.action_filter,
        "subdir": armature.vs.subdir,
        "vs_export": armature.vs.export,
        "frame": scene.frame_current,
        "action": data.action if data is not None else None,
        "slot": data.action_slot if data is not None else None,
    }


def _restore(scene, armature, saved: dict) -> None:
    for key in ("export_path", "export_format", "engine", "dmx_format", "dmx_encoding"):
        setattr(scene.vs, key, saved[key])
    scene.vs.export_list.clear()
    for name, ob_type, icon, obj, collection in saved["export_list"]:
        row = scene.vs.export_list.add()
        row.name = name
        row.ob_type = ob_type
        if icon:
            row.icon = icon
        if obj is not None:
            row.obj = obj
        if collection is not None:
            row.collection = collection
    armature.data.vs.action_selection = saved["action_selection"]
    armature.vs.action_filter = saved["action_filter"]
    armature.vs.subdir = saved["subdir"]
    armature.vs.export = saved["vs_export"]
    data = armature.animation_data
    if data is not None:
        data.action = saved["action"]
        if saved["action"] is not None and saved["slot"] is not None:
            try:
                data.action_slot = saved["slot"]
            except (TypeError, ValueError):
                pass
    try:
        scene.frame_set(saved["frame"])
    except (TypeError, ValueError):
        pass


def _dmx_files(root: Path) -> dict[Path, int]:
    if not root.is_dir():
        return {}
    found = {}
    for path in root.rglob("*.dmx"):
        try:
            found[path] = path.stat().st_mtime_ns
        except OSError:
            continue
    return found


def write_action(settings, entry, destination: Path) -> Path:
    """Write one imported action back to ``<destination>/anims/<label>.dmx``."""
    armature = _armature(settings)
    from . import ikops

    if ikops.has_constraints(armature):
        raise RuntimeError(
            "clip-export-unbaked-ik: bake the IK action before writing it; the constraints are not in a DMX"
        )
    action = bpy.data.actions.get(entry.action) if entry.action else None
    if action is None:
        raise RuntimeError(
            f"clip-not-imported: {entry.label} has no action; import it before writing it out"
        )
    scene = bpy.context.scene
    if not hasattr(armature, "vs") or not hasattr(scene, "vs"):
        raise RuntimeError("clip-export-needs-pulsesrcops: enable the PulseSrcOps extension")
    target = clipscan.written_path(destination, entry.label)
    target.parent.mkdir(parents=True, exist_ok=True)
    before = _dmx_files(target.parent)
    saved = _snapshot(scene, armature)
    try:
        # An armature is an animation export only when it is the whole export and
        # its action selection is not CURRENT; FILTERED_ACTIONS writes one file per
        # action name the filter matches, which this narrows to exactly this one.
        armature.data.vs.action_selection = "FILTERED_ACTIONS"
        armature.vs.action_filter = clipscan.glob_escape(action.name)
        armature.vs.subdir = "anims"
        armature.vs.export = True
        data = armature.animation_data or armature.animation_data_create()
        data.action = action
        if getattr(action, "slots", None):
            data.action_slot = action.slots[0]
        scene.vs.export_path = str(destination) + os.sep
        scene.vs.export_format = "DMX"
        scene.vs.engine = "SOURCE"
        scene.vs.dmx_format = "22_modeldoc"
        scene.vs.dmx_encoding = "3"
        scene.vs.export_list.clear()
        row = scene.vs.export_list.add()
        row.name = armature.name
        row.ob_type = "OBJECT"
        row.icon = "ARMATURE"
        row.obj = armature
        core.select_only(bpy.context, [armature])
        # PulseSrcOps rolls back an undo step in its finally block; debug_value > 1
        # makes it skip that, the same guard the model export uses.
        old_debug_value = bpy.app.debug_value
        bpy.app.debug_value = max(2, old_debug_value)
        try:
            result = bpy.ops.export_scene.smd(object_name=armature.name)
        finally:
            bpy.app.debug_value = old_debug_value
        if "FINISHED" not in result:
            raise RuntimeError(f"clip-export-refused: PulseSrcOps did not finish {entry.label}")
    finally:
        fresh_scene = getattr(bpy.context, "scene", scene)
        restored = bpy.data.objects.get(armature.name) or armature
        _restore(fresh_scene, restored, saved)
    after = _dmx_files(target.parent)
    fresh = [path for path, stamp in after.items() if before.get(path) != stamp]
    if not fresh:
        raise RuntimeError(f"clip-export-empty: PulseSrcOps wrote no DMX for {entry.label}")
    chosen = next((path for path in fresh if path.stem == action.name), None)
    if chosen is None:
        chosen = max(fresh, key=lambda path: path.stat().st_size)
    if chosen != target:
        # The file has to carry the clip's own name: that stem is what the
        # animgraph and the vnmclip it replaces refer to.
        if target.exists():
            target.unlink()
        chosen.replace(target)
        chosen = target
    if not chosen.is_file() or chosen.stat().st_size == 0:
        raise RuntimeError(f"clip-export-empty: {chosen.name} is empty")
    entry.exported = str(chosen)
    entry.export_bytes = chosen.stat().st_size
    entry.state = "WRITTEN"
    return chosen


def start_export(settings, only_index: int | None = None) -> int:
    """Queue the imported clips that can be written out; returns how many were queued."""
    global _QUEUE, _TIMER, _MODE
    _armature(settings)
    write_folder(settings)
    if only_index is not None:
        rows = [only_index]
    else:
        rows = [
            index
            for index, row in enumerate(settings.clips)
            if row.action and row.state in ("IMPORTED", "WRITTEN", "FAILED")
        ]
    if not rows:
        raise RuntimeError("clip-export-empty: import a clip before writing one out")
    _QUEUE = list(rows)
    _MODE = "export"
    if _TIMER is None:
        _TIMER = bpy.app.timers.register(_tick, first_interval=0.0, persistent=True)
    return len(_QUEUE)


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
        row.exported = ""
        row.export_bytes = 0
        row.state = "EDITABLE" if row.kind == "dmx" and not row.compiled else "OPAQUE"
    settings.clip_imported = 0
    settings.clip_written = 0
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


class DMF_OT_export_clips(Operator):
    bl_idname = "dmf.export_clips"
    bl_label = "Write All Clips"
    bl_description = "Write every imported action back to an animation DMX, one file per timer step"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            queued = start_export(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, f"Writing {queued} clips to {write_folder(settings)}", "BUSY")
        return {"FINISHED"}


class DMF_OT_export_clip(Operator):
    bl_idname = "dmf.export_clip"
    bl_label = "Write Clip"
    bl_description = "Write the selected clip's action back to an animation DMX"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.clips:
            self.report({"ERROR"}, "Scan a clip folder first")
            return {"CANCELLED"}
        try:
            start_export(settings, only_index=settings.clip_index)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (
    DMF_OT_scan_clips,
    DMF_OT_import_clips,
    DMF_OT_import_clip,
    DMF_OT_cancel_clips,
    DMF_OT_prefix_clips,
    DMF_OT_clear_clips,
    DMF_OT_preview_clip,
    DMF_OT_export_clips,
    DMF_OT_export_clip,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    cancel()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
