"""Clip import and write-back: animation DMX onto the hero rig, and back out.

The queue is driven by a Blender timer, one file per step, so a folder of several
hundred clips does not lock the interface and the progress line stays truthful.
Each imported clip records the action PulseSrcOps created for it, which is what
the prefix, preview, export and clear actions work from afterwards.

Writing a clip is one PulseSrcOps animation export per row: the armature is the
only exportable, the action filter names that one action, and PulseSrcOps writes
``<root>/anims`` for AG1 and ``<root>/clips`` for AG2. The action, the export list and the scene's export
settings are saved and put back, so an export never becomes the file's state.
"""
from __future__ import annotations

import os
from pathlib import Path

import bpy
from bpy.types import Operator
from forge import clips as clipscan
from forge import tails as tailscan

from . import core, proofing, source2

_QUEUE: list[int] = []
_TIMER = None
_MODE = "import"
_STEP_SECONDS = 0.05


def folder(settings) -> Path | None:
    value = settings.clips_dir
    if not value:
        return None
    return Path(bpy.path.abspath(value))


def roots(settings) -> list[Path]:
    """Every folder that can hold this hero's clips, without a mandatory pick.

    An explicit Clip folder is authoritative.  Otherwise the body DMX, the live
    model and the vmdl identify the current hero; the extraction is added only
    when the body still lives inside it.  Adding a stale extraction is how
    Werewolf clips ended up in Shiv's list after a body swap.
    """
    chosen = folder(settings)
    if chosen is not None:
        return [chosen]
    candidates: list[Path] = []
    body = Path(bpy.path.abspath(settings.body_dmx)) if settings.body_dmx else None
    if body is not None:
        # The body is the authority.  A clip panel for Werewolf must not keep
        # reading a Shiv vmdl or extraction left in the scene fields.
        candidates.append(body.parent)
        if settings.extraction_dir:
            extraction = Path(bpy.path.abspath(settings.extraction_dir))
            if extraction in body.parents:
                candidates.append(extraction)
    else:
        for value in (settings.extraction_dir, settings.hero_model_path, settings.vmdl):
            if not value:
                continue
            path = Path(bpy.path.abspath(value))
            candidates.append(path if path.is_dir() else path.parent)
    found: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        for root in clipscan.clip_roots(candidate):
            key = str(root.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(root)
    return found


def hero_source(settings) -> str:
    """A stable label for the hero extraction a clip row came from."""
    if settings.hero_slug not in ("", "NONE"):
        return settings.hero_slug
    if settings.body_dmx:
        return Path(bpy.path.abspath(settings.body_dmx)).parent.name
    if settings.extraction_dir:
        return Path(bpy.path.abspath(settings.extraction_dir)).name
    return ""


def scan(settings) -> dict[str, int]:
    """Discover AG1/AG2 clips beside the extraction; nothing is imported."""
    roots_found = roots(settings)
    if not roots_found:
        raise RuntimeError(
            "clip-folder-missing: extract a hero, choose its body DMX, or set a clip folder"
        )
    missing = [str(root) for root in roots_found if not root.is_dir()]
    if missing and len(missing) == len(roots_found):
        raise RuntimeError(f"clip-folder-missing: {missing[0]} is not a folder")
    rows = clipscan.discover(roots_found)
    skeleton = clipscan.find_vnmskel(roots_found)
    if skeleton is None and settings.clip_vnmskel:
        candidate = Path(bpy.path.abspath(settings.clip_vnmskel))
        skeleton = candidate if candidate.is_file() else None
    settings.clip_vnmskel = str(skeleton) if skeleton is not None else ""
    settings.clips.clear()
    source_hero = hero_source(settings)
    for row in rows:
        entry = settings.clips.add()
        entry.name = row.name
        entry.label = row.label
        entry.kind = row.kind
        entry.compiled = row.compiled
        entry.path = str(row.path)
        entry.size = row.size
        entry.source_hero = source_hero
        entry.state = "EDITABLE" if row.editable else "OPAQUE"
        entry.ag = clipscan.animgraph(row.path, roots_found, skeleton)
    settings.clip_index = 0
    settings.clip_imported = 0
    settings.clip_written = 0
    settings.clip_baked = 0
    settings.tail_clip = "NONE"
    counts = clipscan.summary(rows)
    counts["ag1"] = sum(1 for row in settings.clips if row.ag == "AG1")
    counts["ag2"] = sum(1 for row in settings.clips if row.ag == "AG2")
    counts["unknown"] = sum(1 for row in settings.clips if row.ag == "UNKNOWN")
    counts["vnmskel"] = 1 if skeleton is not None else 0
    settings.clip_auto_note = (
        f"{len(roots_found)} clip root{'s' if len(roots_found) != 1 else ''}; "
        f"AG2 skeleton {skeleton.name if skeleton else 'not found'}"
    )
    if skeleton is None and counts["ag2"]:
        settings.clip_auto_note += "; make the vnmskel in ModelDoc for AG2"
    return counts


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
    source2.import_dmx(path, append="APPEND")
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
    entry.source_hero = entry.source_hero or hero_source(settings)
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
    baking = _MODE == "bake"
    try:
        if exporting:
            written = write_action(settings, entry, write_folder(settings))
            settings.clip_written += 1
            core.set_status(
                settings,
                f"Wrote {written.name} ({entry.export_bytes:,} bytes); {len(_QUEUE)} left",
                "BUSY",
            )
        elif baking:
            baked = bake_action(settings, entry)
            written = write_action(settings, entry, write_folder(settings))
            settings.clip_written += 1
            core.set_status(
                settings,
                f"Baked {baked['frames']} frames and wrote {written.name}; {len(_QUEUE)} left",
                "BUSY",
            )
        else:
            _import_one(settings, entry)
            settings.clip_imported += 1
            settings.tail_clip = str(index)
            core.set_status(settings, f"Imported {entry.label}; {len(_QUEUE)} left", "BUSY")
    except Exception as error:
        entry.state = "FAILED"
        if not exporting:
            entry.action = ""
        settings.clip_note = str(error)
        core.set_status(settings, f"{entry.label}: {error}", "WARN")
    if not _QUEUE:
        failed = sum(1 for row in settings.clips if row.state == "FAILED")
        if exporting or baking:
            core.set_status(
                settings,
                f"Baked {settings.clip_baked}, wrote {settings.clip_written} clips to "
                f"{write_folder(settings)}; {failed} failed",
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
    """The folder written clips go to; nothing is written into the extraction."""
    base = folder(settings)
    if base is None and settings.clip_vnmskel:
        base = Path(bpy.path.abspath(settings.clip_vnmskel)).parent
    if base is None and settings.extraction_dir:
        base = Path(bpy.path.abspath(settings.extraction_dir))
    root = clipscan.export_folder(base, settings.clip_export_dir or None)
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
    """Write one imported action back under its animgraph's source folder."""
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
    target = clipscan.written_path(destination, entry.label, entry.ag)
    target.parent.mkdir(parents=True, exist_ok=True)
    before = _dmx_files(target.parent)
    saved = _snapshot(scene, armature)
    try:
        # An armature is an animation export only when it is the whole export and
        # its action selection is not CURRENT; FILTERED_ACTIONS writes one file per
        # action name the filter matches, which this narrows to exactly this one.
        armature.data.vs.action_selection = "FILTERED_ACTIONS"
        armature.vs.action_filter = clipscan.glob_escape(action.name)
        armature.vs.subdir = target.parent.name
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


def bake_action(settings, entry) -> dict:
    """Bake one imported action with visual keying before it is written.

    The VmClip guide's Blender section requires the IK/weapon constraints to be
    baked and cleared before export.  Every pose bone is baked, so extra tail
    bones carried by a joined custom chain are included.  Only this addon's IK
    constraints are removed; any other constraint the owner added stays.
    """
    armature = _armature(settings)
    action = bpy.data.actions.get(entry.action) if entry.action else None
    if action is None:
        raise RuntimeError(
            f"clip-not-imported: {entry.label} has no action; import it before baking it"
        )
    start, end = (int(round(value)) for value in action.frame_range)
    if end <= start:
        raise RuntimeError(f"clip-bake-empty-range: {entry.label} has no frame range")
    data = armature.animation_data or armature.animation_data_create()
    data.action = action
    if hasattr(data, "action_slot") and getattr(action, "slots", None):
        data.action_slot = action.slots[0]
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    try:
        core.select_only(bpy.context, [armature])
        bpy.context.view_layer.objects.active = armature
        if armature.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="POSE")
        result = bpy.ops.nla.bake(
            frame_start=start,
            frame_end=end,
            step=1,
            only_selected=False,
            visual_keying=True,
            clear_constraints=False,
            clear_parents=False,
            use_current_action=True,
            bake_types={"POSE"},
        )
    finally:
        current = bpy.data.objects.get(armature.name) or armature
        if current.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        core.select_only(bpy.context, selected)
        if active is not None:
            bpy.context.view_layer.objects.active = active
    if "FINISHED" not in result:
        raise RuntimeError(f"clip-bake-refused: Blender did not finish {entry.label}")
    from . import ikops

    cleared = ikops.clear(settings) if ikops.has_constraints(armature) else 0
    settings.clip_baked += 1
    return {"action": action.name, "frames": end - start + 1, "cleared": cleared}


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


def start_bake_export(settings, only_index: int | None = None) -> int:
    """Queue imported actions for visual bake, then write each as DMX."""
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
        raise RuntimeError("clip-bake-empty: import a clip before baking it")
    _QUEUE = list(rows)
    _MODE = "bake"
    settings.clip_baked = 0
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
    global _QUEUE, _TIMER, _MODE
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
    _MODE = "import"
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
            f"{counts['dmx']} DMX / {counts['vnmclip']} vnmclip; "
            f"AG1 {counts['ag1']}, AG2 {counts['ag2']}, unknown {counts['unknown']}",
            "OK" if counts["editable"] else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_bake_clips(Operator):
    bl_idname = "dmf.bake_clips"
    bl_label = "Bake And Write Clips"
    bl_description = (
        "Bake every imported action with visual keying, clear this addon's IK constraints, "
        "and write each one as a Model 22 DMX for ModelDoc"
    )

    def execute(self, context):
        settings = context.scene.dmf
        try:
            queued = start_bake_export(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, f"Baking and writing {queued} clips; the viewport stays usable", "BUSY")
        return {"FINISHED"}


class DMF_OT_bake_clip(Operator):
    bl_idname = "dmf.bake_clip"
    bl_label = "Bake Clip"
    bl_description = "Bake the selected action and write it as a Model 22 DMX"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.clips:
            self.report({"ERROR"}, "Scan clips first")
            return {"CANCELLED"}
        try:
            start_bake_export(settings, only_index=settings.clip_index)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
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
    DMF_OT_bake_clips,
    DMF_OT_bake_clip,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    cancel()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
