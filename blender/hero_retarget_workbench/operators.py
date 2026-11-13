"""Operators for the Hero Retarget Workbench workflow."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path, PurePosixPath

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from . import core, jobs, parts, properties, proofing, weights


def _status(settings, message: str, kind: str = "INFO") -> None:
    core.set_status(settings, message, kind)


def _new_objects(before: set[str]) -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.name not in before]


@dataclass(frozen=True)
class ExportedModel:
    primary: Path
    lods: list[Path]


def _logical_relative(path: str | Path, root: Path, fallback: str) -> str:
    resolved = Path(path).resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError:
        return fallback
    if relative.parts and relative.parts[0].lower() == "models":
        return relative.as_posix()
    return fallback


def _model_material_path(settings) -> str:
    """The content-relative folder a model's materials belong in.

    Source 2 addons keep a model's materials next to the model's vmdl under a
    ``materials`` folder. A bare DMX material token resolves at the content root,
    which is why a VPK built from the addon tree otherwise gets root-level vmats.
    """
    for relative in (settings.vmdl_relative, settings.target_dmx_relative):
        normalized = (relative or "").replace("\\", "/").strip("/")
        parent = PurePosixPath(normalized).parent
        if parent.as_posix() not in ("", "."):
            return (parent / "materials").as_posix()
    return "materials"


def _pick_imported(before: set[str]) -> tuple[bpy.types.Object | None, bpy.types.Object | None]:
    imported = _new_objects(before)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    arms = [obj for obj in imported if obj.type == "ARMATURE"]
    mesh = max(meshes, key=lambda obj: len(obj.data.vertices)) if meshes else None
    arm = max(arms, key=lambda obj: len(obj.data.bones)) if arms else None
    return mesh, arm


class DMF_OT_detect_paths(Operator):
    bl_idname = "dmf.detect_paths"
    bl_label = "Detect Installed Tools"
    bl_description = "Fill the Setup fields from Steam, PATH, the environment, and any paths already set in this file"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            module = core.core(settings)
            env = core.detect_environment(settings, module)
            if env.game_root is None:
                raise RuntimeError("Deadlock install not found. Choose the Steam Deadlock folder in Setup.")
            settings.deadlock_root = str(env.game_root)
            settings.build = f"{env.build} {env.version_date}".strip()
            if env.s2v is not None:
                settings.s2v_cli = str(env.s2v)
            if env.csdk_root is not None:
                settings.csdk_root = str(env.csdk_root)
            missing = [
                name
                for name, value in (
                    ("Source 2 Viewer CLI (choose Source2Viewer-CLI.exe, not the GUI)", env.s2v),
                    ("CSDK13 root", env.csdk_root),
                )
                if value is None
            ]
            if missing:
                _status(settings, f"Build {settings.build or 'unknown'}; set " + " and ".join(missing), "WARN")
            else:
                _status(settings, f"Build {settings.build or 'unknown'}; all tool paths found", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_detect(Operator):
    bl_idname = "dmf.detect"
    bl_label = "Detect Live Build"
    bl_description = "Find the live Deadlock install and list its heroes through Source 2 Viewer without blocking the viewport"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            module = core.core(settings)
            root = core.project_root(settings)

            def work(progress):
                progress(0.05, "reading live install")
                env = core.detect_environment(settings, module)
                if not env.game_root:
                    raise RuntimeError("Live game not found. Choose the Steam Deadlock folder in Setup.")
                if not env.s2v:
                    raise RuntimeError(
                        "Source 2 Viewer CLI not found. Choose Source2Viewer-CLI.exe in Setup; "
                        "Source2Viewer.exe is the GUI and cannot extract VPK files for the addon."
                    )
                progress(0.25, "reading hero table through S2V")
                heroes = module["live"].list_heroes(env)
                return env, heroes

            def done(result):
                env, heroes = result
                old = settings.hero_slug
                properties.set_hero_items(heroes)
                settings.hero_slug = "NONE"
                if old and old != "NONE" and any(hero.slug == old for hero in heroes):
                    settings.hero_slug = old
                settings.build = f"{env.build} {env.version_date}".strip()
                settings.deadlock_root = str(env.game_root) if env.game_root else settings.deadlock_root
                settings.s2v_cli = str(env.s2v) if env.s2v else settings.s2v_cli
                settings.csdk_root = str(env.csdk_root) if env.csdk_root else settings.csdk_root
                settings.project_root = str(root)
                _status(settings, f"{len(heroes)} hero entries on build {settings.build}", "OK")

            def failed(error):
                _status(settings, str(error), "ERROR")

            message = jobs.start(settings, "Detecting live build", work, done, failed)
            if message:
                raise RuntimeError(message)
            _status(settings, "Reading the live build; S2V runs off the main thread", "BUSY")
        except Exception as error:  # Blender must see a readable failure, not a traceback dialog.
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_extract(Operator):
    bl_idname = "dmf.extract"
    bl_label = "Extract Hero"
    bl_description = "Run Source 2 Viewer on the selected live hero off the main thread and collect its extracted files"

    def execute(self, context):
        settings = context.scene.dmf
        if settings.hero_slug in ("", "NONE"):
            self.report({"ERROR"}, "Choose a hero first")
            return {"CANCELLED"}
        try:
            module = core.core(settings)
            root = core.project_root(settings)
            slug = settings.hero_slug
            previous_model = settings.hero_model_path
            preferred = (
                Path(bpy.path.abspath(settings.extraction_dir))
                if settings.extraction_dir
                else root / "artifacts" / "extractions" / slug
            )

            def work(progress):
                progress(0.1, "reading live install")
                env = core.detect_environment(settings, module)
                progress(0.2, "reading hero table through S2V")
                heroes = module["live"].list_heroes(env)
                hero = next((item for item in heroes if item.slug == slug), None)
                if hero is None:
                    raise RuntimeError("The selected hero is no longer in the live build. Detect the build again.")
                destination = preferred
                if previous_model and previous_model != hero.model_path:
                    destination = root / "artifacts" / "extractions" / hero.slug
                progress(0.3, f"extracting {hero.title}")
                result = module["live"].extract(env, hero, destination)
                return hero, result

            def done(pair):
                hero, result = pair
                settings.extraction_dir = str(result.root)
                settings.hero_model_path = hero.model_path
                settings.body_dmx = str(result.body_dmx) if result.body_dmx else ""
                if result.vmdl:
                    settings.vmdl = str(result.vmdl)
                else:
                    settings.vmdl = ""
                if settings.body_dmx:
                    settings.target_dmx_relative = _logical_relative(
                        settings.body_dmx,
                        result.root,
                        f"{Path(hero.model_path).parent.as_posix()}/{Path(settings.body_dmx).name}",
                    )
                settings.vmdl_relative = _logical_relative(
                    settings.vmdl,
                    result.root,
                    f"{Path(hero.model_path).parent.as_posix()}/{Path(settings.vmdl).name if settings.vmdl else Path(module['live'].hero_vmdl_path(hero.model_path)).name}",
                )
                if result.material_files:
                    settings.materials_dir = str(result.root)
                elif previous_model and previous_model != hero.model_path:
                    settings.materials_dir = ""
                settings.material_count = len(result.material_files)
                if result.vmdl:
                    _status(settings, f"Extracted {hero.title}; the vmdl is unchanged", "OK")
                else:
                    _status(
                        settings,
                        "Extracted geometry, but this S2V CLI emitted no vmdl. Choose the vmdl from your S2V extraction; the addon will not rebuild it.",
                        "WARN",
                    )

            def failed(error):
                _status(settings, str(error), "ERROR")

            message = jobs.start(settings, "Extracting hero", work, done, failed)
            if message:
                raise RuntimeError(message)
            _status(settings, "Extracting the hero; S2V and file inventory run off the main thread", "BUSY")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_import_hero(Operator):
    bl_idname = "dmf.import_hero"
    bl_label = "Import Hero Skeleton"
    bl_description = "Import the live-extracted hero body DMX with PulseSrcOps"

    def execute(self, context):
        settings = context.scene.dmf
        path = Path(bpy.path.abspath(settings.body_dmx)) if settings.body_dmx else None
        if path is None or not path.is_file():
            self.report({"ERROR"}, "Choose a hero body DMX from the S2V extraction")
            return {"CANCELLED"}
        before = {obj.name for obj in context.scene.objects}
        try:
            bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE", upAxis="Z", forwardAxis="-Y")
        except Exception as error:
            _status(settings, f"Hero import failed: {error}", "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        mesh, arm = _pick_imported(before)
        if arm is None or mesh is None:
            _status(settings, "PulseSrcOps found no armature or mesh in the DMX", "ERROR")
            self.report({"ERROR"}, "The DMX did not contain both a hero armature and a body mesh")
            return {"CANCELLED"}
        settings.target_armature = arm
        settings.target_body = mesh
        settings.material_source = mesh
        parts.scan_materials(settings)
        if settings.extraction_dir:
            settings.target_dmx_relative = _logical_relative(
                path,
                Path(bpy.path.abspath(settings.extraction_dir)),
                f"{Path(settings.hero_model_path).parent.as_posix()}/{path.name}" if settings.hero_model_path else f"models/heroes_staging/{settings.hero_slug or 'hero'}/{path.name}",
            )
        context.view_layer.objects.active = arm
        proofing.bump_tick(settings)
        _status(settings, f"Hero ready: {len(arm.data.bones)} bones, {len(mesh.data.vertices):,} vertices", "OK")
        return {"FINISHED"}


class DMF_OT_import_custom(Operator):
    bl_idname = "dmf.import_custom"
    bl_label = "Import Custom Model"
    bl_description = "Import a custom glTF, GLB, FBX, OBJ, or DMX and scan its collection parts"

    def execute(self, context):
        settings = context.scene.dmf
        path = Path(bpy.path.abspath(settings.custom_model)) if settings.custom_model else None
        if path is None or not path.is_file():
            self.report({"ERROR"}, "Choose a custom model file")
            return {"CANCELLED"}
        suffix = path.suffix.lower()
        before = {obj.name for obj in context.scene.objects}
        bpy.ops.object.select_all(action="DESELECT")
        try:
            if suffix in (".gltf", ".glb"):
                bpy.ops.import_scene.gltf(filepath=str(path))
            elif suffix == ".fbx":
                bpy.ops.import_scene.fbx(filepath=str(path))
            elif suffix == ".obj":
                if hasattr(bpy.ops.wm, "obj_import"):
                    bpy.ops.wm.obj_import(filepath=str(path))
                else:
                    bpy.ops.import_scene.obj(filepath=str(path))
            elif suffix == ".dmx":
                bpy.ops.import_scene.kst_dmx(filepath=str(path), append="NEW_ARMATURE")
            else:
                raise RuntimeError(f"unsupported model type: {suffix or 'no extension'}")
        except Exception as error:
            _status(settings, f"Custom import failed: {error}", "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        mesh, arm = _pick_imported(before)
        if mesh is None:
            _status(settings, "The custom import produced no mesh", "ERROR")
            self.report({"ERROR"}, "The custom import produced no mesh")
            return {"CANCELLED"}
        collection = parts.capture_import(context, path, _new_objects(before))
        settings.custom_collection = collection
        settings.custom_mesh = None
        settings.custom_armature = arm
        if settings.material_source is None and settings.target_body is not None:
            settings.material_source = settings.target_body
        count = parts.scan_parts(settings)
        settings.custom_mesh = None
        settings.custom_armature = arm
        parts.scan_materials(settings)
        context.view_layer.objects.active = mesh
        mesh.select_set(True)
        proofing.bump_tick(settings)
        _status(
            settings,
            f"Custom import ready: {count} parts in {collection.name}; choose a part in Parts & Materials",
            "OK",
        )
        return {"FINISHED"}


class DMF_OT_fit(Operator):
    bl_idname = "dmf.fit"
    bl_label = "Fit to Hero"
    bl_description = "Apply the selected axis transform and optional height scale to the custom model"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        if mesh is None:
            self.report({"ERROR"}, "Choose the custom mesh first")
            return {"CANCELLED"}
        objects = [obj for obj in (mesh, settings.custom_armature) if obj is not None]
        try:
            from mathutils import Matrix

            module = core.core(settings)
            from forge.axis import AxisTransform

            scale = Fraction(str(round(settings.fit_scale, 6)))
            if settings.fit_to_height and settings.target_body is not None:
                target_low, target_high = core.world_bounds([settings.target_body])
                source_low, source_high = core.world_bounds([mesh])
                source_height = source_high - source_low
                target_height = target_high - target_low
                if source_height > 1e-6 and target_height > 1e-6:
                    scale = Fraction(str(round(settings.fit_scale * (target_height / source_height), 6)))
            transform = AxisTransform.preset(settings.axis_preset, scale=scale, allow_mirror=(settings.axis_preset == "mirror-x"))
            matrix = Matrix(transform.matrix4())
            roots = [obj for obj in objects if obj.parent not in objects]
            for obj in roots:
                obj.matrix_world = matrix @ obj.matrix_world
            context.view_layer.update()
            proofing.bump_tick(settings)
            _status(settings, f"Applied {settings.axis_preset} at {float(scale):.4f}x and left the weights unchanged", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_use_active_collection(Operator):
    bl_idname = "dmf.use_active_collection"
    bl_label = "Use Active Collection"
    bl_description = "Use the active Blender collection as the custom part scope and scan its mesh objects"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            collection = context.view_layer.active_layer_collection.collection
            if collection is None:
                raise RuntimeError("part-collection-missing: the active layer has no collection")
            settings.custom_collection = collection
            count = parts.scan_parts(settings)
            active = settings.custom_mesh.name if settings.custom_mesh is not None else "none"
            _status(settings, f"Scoped {count} parts in {collection.name}; active part {active}", "OK" if count else "WARN")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_scan_parts(Operator):
    bl_idname = "dmf.scan_parts"
    bl_label = "Scan Parts"
    bl_description = "Scan the selected collection and child collections for mesh parts; do not assign materials"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = parts.scan_parts(settings)
            active = settings.custom_mesh.name if settings.custom_mesh is not None else "none"
            _status(settings, f"Scanned {count} parts; active part {active}", "OK" if count else "WARN")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_use_part(Operator):
    bl_idname = "dmf.use_part"
    bl_label = "Use Active Part"
    bl_description = "Make the selected collection row the active custom part for fit, weights, materials and export"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            obj = parts.use_part(settings, settings.part_index)
            proofing.bump_tick(settings)
            _status(
                settings,
                f"Active part {obj.name}: {len(obj.data.vertices):,} vertices, {len(obj.data.materials)} material slots",
                "OK",
            )
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_scan_materials(Operator):
    bl_idname = "dmf.scan_materials"
    bl_label = "Scan Material Slots"
    bl_description = "Refresh the source object's slots and the active part's slots without assigning either"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            source_count, part_count = parts.scan_materials(settings)
            source_name = settings.material_source.name if settings.material_source is not None else "none"
            _status(
                settings,
                f"Material source {source_name}: {source_count} slots; active part: {part_count} slots",
                "OK" if source_count else "WARN",
            )
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_assign_material(Operator):
    bl_idname = "dmf.assign_material"
    bl_label = "Assign Selected Material"
    bl_description = "Replace the selected active-part material slot with the selected source slot; never copies every slot"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            material, slot, added = parts.assign_material(settings, append=False)
            target = settings.custom_mesh
            _status(
                settings,
                f"Assigned {material} to {target.name} slot {slot} ({'appended' if added else 'replaced'}); other slots unchanged",
                "OK",
            )
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_append_material(Operator):
    bl_idname = "dmf.append_material"
    bl_label = "Append Selected Material"
    bl_description = "Append the selected source slot to the active part instead of replacing a slot"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            material, slot, _ = parts.assign_material(settings, append=True)
            target = settings.custom_mesh
            _status(settings, f"Appended {material} to {target.name} slot {slot}; existing slots unchanged", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_clear_part_material(Operator):
    bl_idname = "dmf.clear_part_material"
    bl_label = "Clear Part Slot"
    bl_description = "Remove the selected active-part material slot and remap face material indices"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            removed, slot = parts.clear_material(settings)
            _status(settings, f"Cleared {removed} from active part slot {slot}; face indices remapped", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_retarget(Operator):
    bl_idname = "dmf.retarget"
    bl_label = "Solve & Bind"
    bl_description = "Map the custom groups, solve surface/envelope weights in timer chunks, and attach the hero armature"

    def execute(self, context):
        settings = context.scene.dmf
        mesh = settings.custom_mesh
        armature = settings.target_armature
        if mesh is None or armature is None:
            self.report({"ERROR"}, "Import a hero skeleton and a custom mesh first")
            return {"CANCELLED"}
        if settings.job_running or weights.is_running():
            self.report({"ERROR"}, "A weight solve or background job is already running")
            return {"CANCELLED"}
        try:
            core.core(settings)
            from . import workbench

            if not settings.bone_map:
                workbench.scan_bone_map(settings)
            options = weights.WeightOptions.from_settings(settings)
            weights.start(settings, options)
            _status(settings, "Weight solve started; vertex chunks run on a timer so Blender stays responsive", "BUSY")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def _join_export_parts(context, settings, collection, source_parts, armature):
    """Duplicate and join every custom part without changing the scene meshes."""
    duplicates = []
    for obj in source_parts:
        if obj.data is None or not len(obj.data.vertices):
            continue
        duplicate = obj.copy()
        duplicate.data = obj.data.copy()
        duplicate.name = f"DMF export {obj.name}"
        world = obj.matrix_world.copy()
        duplicate.parent = None
        duplicate.matrix_world = world
        collection.objects.link(duplicate)
        if hasattr(duplicate, "vs"):
            duplicate.vs.export = True
        duplicates.append((obj, duplicate))

    if not duplicates:
        raise RuntimeError("Choose a custom collection with at least one mesh before export")

    armatures = {
        modifier.object
        for _, duplicate in duplicates
        for modifier in duplicate.modifiers
        if modifier.type == "ARMATURE" and modifier.object is not None
    }
    if len(armatures) > 1:
        names = ", ".join(sorted(obj.name for obj in armatures))
        raise RuntimeError(
            f"mixed-armature: the export parts use more than one skeleton ({names}); "
            "bind them to one target skeleton before export"
        )
    if armature is None:
        armature = next(iter(armatures), None)
    if armature is None:
        raise RuntimeError("Choose the hero skeleton before export")

    if context.object is not None and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    active_source = settings.custom_mesh if settings.custom_mesh in source_parts else None
    if active_source is None:
        active_source = max(source_parts, key=lambda obj: len(obj.data.vertices))
    active = next(duplicate for source, duplicate in duplicates if source == active_source)
    bpy.ops.object.select_all(action="DESELECT")
    for _, duplicate in duplicates:
        duplicate.select_set(True)
    context.view_layer.objects.active = active
    result = bpy.ops.object.join()
    if "FINISHED" not in result:
        raise RuntimeError("Blender could not join the custom parts for export")
    joined = context.view_layer.objects.active
    joined.name = "DMF joined export"
    if not any(
        modifier.type == "ARMATURE" and modifier.object is armature
        for modifier in joined.modifiers
    ):
        modifier = joined.modifiers.new(name="DMF export armature", type="ARMATURE")
        modifier.object = armature
    if collection.objects.get(armature.name) is None:
        collection.objects.link(armature)
    if hasattr(armature, "vs"):
        armature.vs.export = True
    return joined, armature, [joined.name]


def _purge_export_leftovers(
    scene_name: str | None,
    collection_name: str,
    objects_before: set[str],
    collections_before: set[str],
) -> list[str]:
    """Remove the collections and objects one export created.

    PulseSrcOps copies every exportable object, armature included, into a
    ``<scope>_lodN`` collection for each generated level. Left behind they show
    up in the Outliner and the next export copies them too, which is the lag.
    This unlinks the export's own collections and objects; the datablocks are
    only dropped by the orphan purge, never by deleting something the scene
    still references.
    """
    removed: list[str] = []
    for collection in list(bpy.data.collections):
        if collection.name in collections_before:
            continue
        if not collection.name.startswith(collection_name):
            continue
        for obj in list(collection.objects):
            collection.objects.unlink(obj)
        removed.append(collection.name)
        try:
            bpy.data.collections.remove(collection)
        except Exception:  # A dangling depsgraph reference must not kill the export.
            pass
    for obj in list(bpy.data.objects):
        if obj.name in objects_before:
            continue
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        removed.append(obj.name)
    try:
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=False)
    except Exception:
        pass
    return removed


def _lod_collection(settings):
    """The persistent collection the built LOD meshes live in."""
    name = f"DMF LODs {(settings.addon_name or '').strip() or 'model'}"
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    scene = bpy.context.scene
    if scene is not None and scene.collection.children.get(collection.name) is None:
        scene.collection.children.link(collection)
    return collection


def clear_lods(settings) -> int:
    """Delete the built LOD meshes and forget the rows."""
    removed = 0
    for row in list(settings.lod_levels):
        obj = row.object
        if obj is None or bpy.data.objects.get(obj.name) is None:
            continue
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
    settings.lod_levels.clear()
    settings.lod_index = 0
    settings.lod_tick = -1
    return removed


def build_lods(context, settings) -> list[tuple[int, int]]:
    """Build the LOD meshes once and keep them in the file.

    Each level is joined from the same export scope, decimated, and left bound
    to the hero armature. Export then reuses these meshes, so it neither
    decimates nor copies the armature per level.
    """
    source_parts = parts.export_meshes(settings)
    if not source_parts:
        raise RuntimeError("Choose a custom collection with at least one mesh before building LODs")
    armature = settings.target_armature
    if armature is None:
        raise RuntimeError("Choose the hero skeleton before building LODs")
    count = settings.lod_count or 3
    collection = _lod_collection(settings)
    clear_lods(settings)
    temp = bpy.data.collections.new("DMF LOD build")
    context.scene.collection.children.link(temp)
    armature_export = bool(getattr(getattr(armature, "vs", None), "export", False))
    built: list[tuple[int, int]] = []
    try:
        for level in range(1, count + 1):
            joined, _, _ = _join_export_parts(context, settings, temp, source_parts, armature)
            ratio = max(0.05, 1.0 - (float(settings.lod_decimate) / 100.0) * level)
            modifier = joined.modifiers.new(name="DMF LOD decimate", type="DECIMATE")
            modifier.decimate_type = "COLLAPSE"
            modifier.ratio = ratio
            core.select_only(context, [joined])
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            joined.name = f"DMF LOD {level}"
            for owner in list(joined.users_collection):
                owner.objects.unlink(joined)
            collection.objects.link(joined)
            row = settings.lod_levels.add()
            row.object = joined
            row.level = level
            row.vertices = len(joined.data.vertices)
            built.append((level, row.vertices))
    finally:
        for obj in list(temp.objects):
            temp.objects.unlink(obj)
        try:
            bpy.data.collections.remove(temp)
        except Exception:
            pass
        try:
            bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=False)
        except Exception:
            pass
        if hasattr(armature, "vs"):
            armature.vs.export = armature_export
    settings.lod_tick = settings.axis_tick
    return built


class DMF_OT_build_lods(Operator):
    bl_idname = "dmf.build_lods"
    bl_label = "Build LODs"
    bl_description = (
        "Join, decimate and keep the LOD meshes in this file, bound to the hero rig, "
        "so export reuses them instead of regenerating them"
    )

    def execute(self, context):
        settings = context.scene.dmf
        try:
            built = build_lods(context, settings)
            settings.live_lods = True
            detail = ", ".join(f"L{level} {vertices:,}v" for level, vertices in built)
            _status(settings, f"Built {len(built)} LODs: {detail}; export reuses them until the model changes", "OK")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_clear_lods(Operator):
    bl_idname = "dmf.clear_lods"
    bl_label = "Clear LODs"
    bl_description = "Delete the built LOD meshes and let export generate them again"

    def execute(self, context):
        settings = context.scene.dmf
        removed = clear_lods(settings)
        settings.live_lods = False
        _status(settings, f"Removed {removed} built LOD meshes; export generates LODs again", "INFO")
        return {"FINISHED"}


class DMF_OT_export_stage(Operator):
    bl_idname = "dmf.export_stage"
    bl_label = "Export & Stage"
    bl_description = "Join every mesh in the custom collection, export it as one DMX, then install the addon at content/citadel_addons/<addon> in the CSDK13 root with the unchanged S2V vmdl and its materials"

    def _export(
        self,
        context,
        settings,
        target_stem: str,
        destination: Path,
        lod_count: int,
        lod_decimate: float,
        live_lods: list[bpy.types.Object] | None = None,
    ) -> ExportedModel:
        scene = context.scene
        live_lods = list(live_lods or [])
        objects_before = {obj.name for obj in bpy.data.objects}
        collections_before = {other.name for other in bpy.data.collections}
        scene_name = scene.name
        if not hasattr(scene, "vs"):
            raise RuntimeError("PulseSrcOps is required for DMX export; enable it in Blender")
        source_parts = parts.export_meshes(settings)
        if not source_parts:
            raise RuntimeError("Choose a custom collection or mesh before export")
        armature = settings.target_armature
        old_path = scene.vs.export_path
        old_format = scene.vs.export_format
        old_engine = scene.vs.engine
        old_dmx_format = scene.vs.dmx_format
        old_encoding = scene.vs.dmx_encoding
        old_material_paths = [item.path for item in scene.vs.material_paths]
        old_material_indices = {
            material.name: material.vs.material_path_index
            for material in bpy.data.materials
            if hasattr(material, "vs")
        }
        old_export_entries = [
            {
                "name": row.name,
                "ob_type": row.ob_type,
                "icon": getattr(row, "icon", ""),
                "collection": row.collection.name if getattr(row, "collection", None) else "",
            }
            for row in scene.vs.export_list
        ]
        old_export_flags = {
            obj.name: bool(getattr(getattr(obj, "vs", None), "export", False))
            for obj in (*source_parts, armature)
            if obj is not None
        }
        collection = bpy.data.collections.new("DMF Export")
        collection_name = collection.name
        scene.collection.children.link(collection)
        temporary_names = []
        try:
            # The ported model owns its material slots. Overwriting them with the
            # hero's pbr.vfx/NPR slots is an explicit button, never an export side
            # effect. A custom slot path survives into the DMX unchanged.
            joined, armature, temporary_names = _join_export_parts(
                context, settings, collection, source_parts, armature
            )
            joined.vs.generate_lods = lod_count > 0 and not live_lods
            joined.vs.lod_count = max(1, lod_count)
            joined.vs.decimate_factor = float(lod_decimate)
            scene.vs.material_paths.clear()
            scene.vs.material_paths.add().path = _model_material_path(settings)
            scene.vs.material_paths_index = 0
            for slot in joined.material_slots:
                if slot.material is not None and hasattr(slot.material, "vs"):
                    slot.material.vs.material_path_index = "0"
            scene.vs.export_path = str(destination) + os.sep
            scene.vs.export_format = "DMX"
            scene.vs.engine = "SOURCE"
            scene.vs.dmx_format = "22_modeldoc"
            scene.vs.dmx_encoding = "3"
            collection.vs.export = True
            joined.vs.export = True
            if armature is not None:
                armature.vs.export = True
            # Built LODs are reused as they are. Each level is copied into the
            # export scope under the DMX stem PulseSrcOps writes from, sharing
            # the built mesh data, so no armature copy and no decimation runs
            # here.
            for order, source_lod in enumerate(live_lods, 1):
                duplicate = source_lod.copy()
                duplicate.name = f"{target_stem}_lod{order}"
                duplicate.parent = None
                duplicate.matrix_world = source_lod.matrix_world.copy()
                collection.objects.link(duplicate)
                if hasattr(duplicate, "vs"):
                    duplicate.vs.export = True
                    duplicate.vs.generate_lods = False
            # A dedicated collection makes PulseSrcOps export exactly this mesh
            # and its armature, instead of every selected object's collection.
            scene.vs.export_list.clear()
            row = scene.vs.export_list.add()
            row.name = collection.name
            row.ob_type = "COLLECTION"
            row.icon = "GROUP"
            row.collection = collection
            # PulseSrcOps pushes an undo step and calls bpy.ops.ed.undo() in
            # its finally block. Running that nested undo while this operator is
            # still on the stack crashes Blender 5.4 with joined/LOD meshes.
            # debug_value > 1 makes PulseSrcOps skip its own undo rollback; the
            # temporary objects here are ours, not scene edits that need rollback.
            old_debug_value = bpy.app.debug_value
            bpy.app.debug_value = max(2, old_debug_value)
            try:
                result = bpy.ops.export_scene.smd(collection=collection.name)
            finally:
                bpy.app.debug_value = old_debug_value
            if "FINISHED" not in result:
                raise RuntimeError("PulseSrcOps did not finish the DMX export")
            dmx_files = sorted(destination.rglob("*.dmx"))
            if not dmx_files:
                raise RuntimeError("PulseSrcOps produced no DMX file")
            lod_pattern = re.compile(r"_lod(\d+)$", re.IGNORECASE)
            base_files = [path for path in dmx_files if not lod_pattern.search(path.stem)]
            if not base_files:
                raise RuntimeError("PulseSrcOps produced LOD DMXs but no base mesh DMX")
            chosen = next(
                (path for path in base_files if path.stem == target_stem),
                max(base_files, key=lambda path: path.stat().st_size),
            )
            if chosen.stem != target_stem:
                renamed = destination / f"{target_stem}.dmx"
                chosen.replace(renamed)
                chosen = renamed
            lod_files = []
            for path in dmx_files:
                match = lod_pattern.search(path.stem)
                if match:
                    lod_files.append((int(match.group(1)), path))
            lod_files.sort(key=lambda item: (item[0], item[1].name))
            if not lod_count and lod_files:
                raise RuntimeError("PulseSrcOps produced LOD DMXs while LOD generation was off")
            if lod_count and len(lod_files) != lod_count:
                raise RuntimeError(
                    f"PulseSrcOps produced {len(lod_files)} of {lod_count} LOD DMXs. "
                    "Lower Decimate per LOD and export again."
                )
            lods = []
            for order, (_, source) in enumerate(lod_files, 1):
                renamed = destination / f"{target_stem}_lod{order}.dmx"
                if source != renamed:
                    source.replace(renamed)
                lods.append(renamed)
            return ExportedModel(chosen, lods)
        finally:
            # PulseSrcOps pushes and rolls back an undo step during export. That can
            # invalidate Python references even when the datablocks still exist, so
            # resolve the scene and the temporary collection again by name.
            fresh_scene = core.fresh_scene(scene_name)
            if fresh_scene is not None:
                fresh_scene.vs.export_path = old_path
                fresh_scene.vs.export_format = old_format
                fresh_scene.vs.engine = old_engine
                fresh_scene.vs.dmx_format = old_dmx_format
                fresh_scene.vs.dmx_encoding = old_encoding
                fresh_scene.vs.material_paths.clear()
                for path in old_material_paths:
                    fresh_scene.vs.material_paths.add().path = path
                for material_name, path_index in old_material_indices.items():
                    restored_material = bpy.data.materials.get(material_name)
                    if restored_material is not None and hasattr(restored_material, "vs"):
                        restored_material.vs.material_path_index = path_index
                fresh_scene.vs.export_list.clear()
                for entry in old_export_entries:
                    row = fresh_scene.vs.export_list.add()
                    row.name = entry["name"]
                    row.ob_type = entry["ob_type"]
                    if entry["icon"]:
                        row.icon = entry["icon"]
                    if entry["collection"]:
                        restored_collection = bpy.data.collections.get(entry["collection"])
                        if restored_collection is not None:
                            row.collection = restored_collection
                for object_name, export_flag in old_export_flags.items():
                    restored_object = bpy.data.objects.get(object_name)
                    if restored_object is not None and hasattr(restored_object, "vs"):
                        restored_object.vs.export = export_flag
            _purge_export_leftovers(
                scene_name, collection_name, objects_before, collections_before
            )

    def execute(self, context):
        settings = context.scene.dmf
        module = core.core(settings)
        if not settings.vmdl or not settings.target_dmx_relative or not settings.addon_name:
            self.report({"ERROR"}, "Choose the S2V vmdl, then set the DMX path and addon name")
            return {"CANCELLED"}
        try:
            proofing.require_current(settings)
        except Exception as proof_error:
            _status(settings, str(proof_error), "ERROR")
            self.report({"ERROR"}, str(proof_error))
            return {"CANCELLED"}
        extraction = Path(bpy.path.abspath(settings.extraction_dir)) if settings.extraction_dir else None
        vmdl = Path(bpy.path.abspath(settings.vmdl))
        if extraction is None or not extraction.is_dir() or not vmdl.is_file():
            self.report({"ERROR"}, "The extraction folder and hero vmdl must both exist")
            return {"CANCELLED"}
        target_stem = Path(settings.target_dmx_relative).stem
        scene_name = context.scene.name
        source_parts = parts.export_meshes(settings)
        custom_slots = len({
            material.name
            for part in source_parts
            for material in part.data.materials
            if material is not None
        })
        part_count = len(source_parts)
        export_dir = Path(tempfile.mkdtemp(prefix="dmf-export-"))
        try:
            existing_lods = module["stage"].target_lod_relatives(extraction, settings.target_dmx_relative)
            lod_count = 0
            lod_decimate = float(settings.lod_decimate)
            if settings.generate_lods:
                lod_count = settings.lod_count or len(existing_lods) or 3
                if not settings.lod_count and lod_count:
                    # Auto mode keeps the deepest generated level non-empty even
                    # when a hero has more than the usual three LOD slots.
                    lod_decimate = min(lod_decimate, 100.0 / (lod_count + 1))
            live_lods: list[bpy.types.Object] = []
            if settings.live_lods:
                live_lods = [row.object for row in settings.lod_levels if row.object is not None]
                if not live_lods:
                    raise RuntimeError(
                        "Use built LODs is on but none are built. Press Build LODs in CSDK Addon, "
                        "or turn it off so PulseSrcOps generates them."
                    )
                lod_count = len(live_lods)
            exported = self._export(
                context,
                settings,
                target_stem,
                export_dir,
                lod_count,
                lod_decimate,
                live_lods=live_lods,
            )
            fresh_scene = core.fresh_scene(scene_name)
            if fresh_scene is None:
                raise RuntimeError("The DMX export left no Blender scene")
            settings = fresh_scene.dmf
            target_dmx = extraction / settings.target_dmx_relative
            if not target_dmx.is_file():
                target_dmx = extraction / Path(settings.target_dmx_relative).name
            if not target_dmx.is_file():
                raise RuntimeError("The target DMX is not in the extraction. Set its logical path from S2V.")
            material_root = (
                Path(bpy.path.abspath(settings.materials_dir))
                if settings.materials_dir
                else extraction
            )
            if not material_root.is_dir():
                raise RuntimeError(f"The materials root is missing: {material_root}")
            materials = module["stage"].material_files(material_root)
            custom_materials = []
            if settings.custom_materials_dir:
                custom_root = Path(bpy.path.abspath(settings.custom_materials_dir))
                if not custom_root.is_dir():
                    raise RuntimeError(f"The model materials root is missing: {custom_root}")
                custom_materials = module["stage"].material_files(custom_root)
            destination = core.csdk_addon_root(settings)
            if destination is None:
                raise RuntimeError(
                    "No CSDK13 install root. Set CSDK13 in Setup so Export & stage can install "
                    f"{settings.addon_name} under content/citadel_addons"
                )
            request = module["stage"].StageRequest(
                extraction_root=extraction,
                vmdl=vmdl,
                target_dmx=target_dmx,
                custom_dmx=exported.primary,
                target_dmx_relative=settings.target_dmx_relative,
                vmdl_relative=settings.vmdl_relative,
                addon_name=settings.addon_name,
                destination=destination,
                materials=materials,
                custom_materials=custom_materials,
                custom_lods=exported.lods,
            )
            # The DMX export above must stay on the main thread because it calls
            # PulseSrcOps operators. Copying the addon tree and hashing every
            # staged file do not touch Blender, so they run in the background job
            # instead of freezing the viewport.
            def work(progress):
                progress(0.1, "copying the addon tree")
                staged = module["stage"].stage(request)
                progress(0.9, "hashing the staged files")
                module["stage"].verify(staged)
                return staged

            def done(staged):
                try:
                    scene = core.fresh_scene(scene_name)
                    current = scene.dmf if scene is not None else settings
                    current.stage_dir = str(destination)
                    current.exported_dmx = str(staged.custom_dmx)
                    _status(
                        current,
                        f"Staged {current.addon_name} into {staged.root}: {part_count} parts joined, "
                        f"{len(staged.custom_lods)} LODs, {custom_slots} custom slots, "
                        f"{staged.material_count} material files ({staged.material_texture_count} textures), "
                        f"{staged.custom_material_count} custom; vmdl unchanged ({staged.vmdl_blake3[:10]})",
                        "OK",
                    )
                finally:
                    shutil.rmtree(export_dir, ignore_errors=True)

            def failed(error):
                try:
                    _status(settings, str(error), "ERROR")
                finally:
                    shutil.rmtree(export_dir, ignore_errors=True)

            started = jobs.start(settings, "Staging the CSDK addon", work, done, failed)
            if started:
                raise RuntimeError(started)
            _status(settings, f"DMX exported; staging {settings.addon_name} in the background", "BUSY")
        except Exception as error:
            shutil.rmtree(export_dir, ignore_errors=True)
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_compile(Operator):
    bl_idname = "dmf.compile"
    bl_label = "Compile with CSDK13"
    bl_description = "Run resourcecompiler in place on the installed addon and leave the compiled files in game/citadel_addons/<addon>, without blocking the viewport"

    def execute(self, context):
        settings = context.scene.dmf
        stage_dir = core.csdk_addon_root(settings)
        if stage_dir is None:
            self.report({"ERROR"}, "Set the CSDK13 root in Setup, then stage the model")
            return {"CANCELLED"}
        if settings.job_running or jobs.is_running():
            self.report({"ERROR"}, "A background job is already running")
            return {"CANCELLED"}
        try:
            module = core.core(settings)
            log_path = core.project_root(settings) / "logs" / "compile.log"
            addon_name = settings.addon_name

            def work(progress):
                progress(0.1, "detecting CSDK13")
                env = core.detect_environment(settings, module)
                progress(0.25, "running resourcecompiler")
                return module["compile"].compile_stage(env, stage_dir, addon_name, log_path=log_path)

            def done(result):
                if result.returncode:
                    _status(settings, f"CSDK13 could not compile the stage; see {result.log}", "ERROR")
                else:
                    installed = result.game_addon or result.content_addon
                    _status(
                        settings,
                        f"Compiled {len(result.compiled_files)} files into {installed}; staged vmdl unchanged",
                        "OK",
                    )

            def failed(error):
                _status(settings, str(error), "ERROR")

            message = jobs.start(settings, "Compiling with CSDK13", work, done, failed)
            if message:
                raise RuntimeError(message)
            _status(settings, "resourcecompiler is running off the main thread", "BUSY")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_pick_old_vpk(Operator):
    bl_idname = "dmf.pick_old_vpk"
    bl_label = "Choose old addon"
    bl_description = "Select an old addon VPK or an extracted addon folder; the live hero is read separately"
    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        context.scene.dmf.old_vpk = str(Path(bpy.path.abspath(self.filepath)))
        return {"FINISHED"}


class DMF_OT_pick_old_vmdl(Operator):
    bl_idname = "dmf.pick_old_vmdl"
    bl_label = "Choose old vmdl"
    bl_description = "Select the old model when the old addon contains more than one vmdl"
    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        context.scene.dmf.update_old_vmdl = str(Path(bpy.path.abspath(self.filepath)))
        return {"FINISHED"}


class DMF_OT_update_old_addon(Operator):
    bl_idname = "dmf.update_old_addon"
    bl_label = "Import & update old addon"
    bl_description = "Extract an old addon, update its hero model to the live game's vmdl, and preserve its cloth/physics and custom assets"

    def execute(self, context):
        settings = context.scene.dmf
        if settings.hero_slug in ("", "NONE"):
            self.report({"ERROR"}, "Choose and detect a live hero first")
            return {"CANCELLED"}
        if not settings.old_vpk:
            self.report({"ERROR"}, "Choose the old VPK or addon folder")
            return {"CANCELLED"}
        if settings.job_running or jobs.is_running():
            self.report({"ERROR"}, "A background job is already running")
            return {"CANCELLED"}
        try:
            module = core.core(settings)
            env = core.detect_environment(settings, module)
            if env.game_root is None:
                raise RuntimeError("The live Deadlock install was not found; set it in Setup")
            if env.s2v is None:
                raise RuntimeError("Source 2 Viewer CLI was not found; set it in Setup")
            output = (
                Path(bpy.path.abspath(settings.update_output))
                if settings.update_output
                else core.project_root(settings) / "updates"
            )
            addon = settings.update_addon_name.strip() or f"{Path(settings.old_vpk).stem}_updated"
            sections = None if settings.update_preserve_cloth else ()
            old_path = Path(bpy.path.abspath(settings.old_vpk))
            old_vmdl = Path(bpy.path.abspath(settings.update_old_vmdl)) if settings.update_old_vmdl else None
            hero_slug = settings.hero_slug
            model_policy = settings.update_model_policy
            preserve_materials = settings.update_preserve_materials
            replace_output = settings.update_replace_output

            def work(progress):
                progress(0.05, "reading live hero roster")
                heroes = module["live"].list_heroes(env)
                hero = next((item for item in heroes if item.slug == hero_slug), None)
                if hero is None:
                    raise RuntimeError(f"Live hero {hero_slug} is no longer in the roster")
                progress(0.2, "extracting old addon and live hero")
                result = module["migrate"].update_from_package(
                    env,
                    old_path,
                    output,
                    addon,
                    hero=hero,
                    old_vmdl=old_vmdl,
                    preserve_model=model_policy,
                    preserve_materials=preserve_materials,
                    sections=sections,
                    force=replace_output,
                )
                progress(0.95, "migration manifest written")
                return result

            def done(result):
                settings.stage_dir = str(result.output)
                settings.extraction_dir = str(result.new_root)
                settings.vmdl = str(result.vmdl)
                settings.vmdl_relative = result.vmdl.relative_to(result.root).as_posix()
                settings.addon_name = addon
                settings.old_vpk = str(old_path)
                settings.update_output = str(output)
                settings.update_addon_name = addon
                settings.custom_materials_dir = str(result.old_root)
                settings.materials_dir = str(result.new_root)
                if result.new_model_files:
                    settings.target_dmx_relative = result.new_model_files[0]
                    body = result.new_root / result.new_model_files[0]
                    settings.body_dmx = str(body) if body.is_file() else ""
                if result.model_files:
                    candidates = [result.old_root / relative for relative in result.model_files]
                    candidates = [path for path in candidates if path.is_file()]
                    if candidates:
                        settings.custom_model = str(max(candidates, key=lambda path: path.stat().st_size))
                metadata = json.loads(result.manifest.read_text(encoding="utf-8"))
                cloth = f"; {metadata.get('cloth_chains', 0)} cloth chains, {metadata.get('cloth_hinges', 0)} hinges"
                _status(
                    settings,
                    f"Updated {addon} from {old_path.name}; {'old' if result.preserved_model else 'live'} model, "
                    f"{result.material_count} old material assets{cloth}; compile from the Handoff panel",
                    "OK",
                )

            def failed(error):
                _status(settings, str(error), "ERROR")

            message = jobs.start(settings, "Updating old addon", work, done, failed)
            if message:
                raise RuntimeError(message)
            _status(settings, "Reading the old addon and live hero off the main thread", "BUSY")
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_pick_vmdl(Operator):
    bl_idname = "dmf.pick_vmdl"
    bl_label = "Choose vmdl"
    bl_description = "Select an S2V-extracted vmdl; staging copies it unchanged"
    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = context.scene.dmf
        path = Path(bpy.path.abspath(self.filepath))
        settings.vmdl = str(path)
        if settings.extraction_dir:
            settings.vmdl_relative = _logical_relative(
                path,
                Path(bpy.path.abspath(settings.extraction_dir)),
                f"{Path(settings.hero_model_path).parent.as_posix()}/{path.name}" if settings.hero_model_path else f"models/heroes_staging/{settings.hero_slug or 'hero'}/{path.name}",
            )
        return {"FINISHED"}


CLASSES = (
    DMF_OT_detect_paths,
    DMF_OT_detect,
    DMF_OT_extract,
    DMF_OT_import_hero,
    DMF_OT_import_custom,
    DMF_OT_use_active_collection,
    DMF_OT_scan_parts,
    DMF_OT_use_part,
    DMF_OT_scan_materials,
    DMF_OT_assign_material,
    DMF_OT_append_material,
    DMF_OT_clear_part_material,
    DMF_OT_fit,
    DMF_OT_retarget,
    DMF_OT_build_lods,
    DMF_OT_clear_lods,
    DMF_OT_export_stage,
    DMF_OT_compile,
    DMF_OT_pick_old_vpk,
    DMF_OT_pick_old_vmdl,
    DMF_OT_update_old_addon,
    DMF_OT_pick_vmdl,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
