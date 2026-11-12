"""Operators for the Deadlock Model Forge workflow."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from . import core, jobs, properties, proofing, weights


def _status(settings, message: str, kind: str = "INFO") -> None:
    core.set_status(settings, message, kind)


def _new_objects(before: set[str]) -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.name not in before]


def _assign_hero_materials(target, source) -> int:
    """Copy hero slots onto the custom mesh and keep face material indices sane.

    A name match wins. Otherwise the old slot index is kept when it still exists,
    which preserves multi-material customs instead of assigning every face to the
    first hero slot.
    """
    old_names = [material.name if material else "" for material in target.data.materials]
    old_indices = [polygon.material_index for polygon in target.data.polygons]
    hero_materials = [material for material in source.data.materials if material is not None]
    target.data.materials.clear()
    for material in hero_materials:
        target.data.materials.append(material)
    by_name = {material.name: index for index, material in enumerate(hero_materials)}
    remap = {}
    for old_index, name in enumerate(old_names):
        if name in by_name:
            remap[old_index] = by_name[name]
        elif old_index < len(hero_materials):
            remap[old_index] = old_index
        elif hero_materials:
            remap[old_index] = 0
    for polygon, old_index in zip(target.data.polygons, old_indices):
        polygon.material_index = remap.get(old_index, 0)
    return len(hero_materials)


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


def _pick_imported(before: set[str]) -> tuple[bpy.types.Object | None, bpy.types.Object | None]:
    imported = _new_objects(before)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    arms = [obj for obj in imported if obj.type == "ARMATURE"]
    mesh = max(meshes, key=lambda obj: len(obj.data.vertices)) if meshes else None
    arm = max(arms, key=lambda obj: len(obj.data.bones)) if arms else None
    return mesh, arm


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
                env = module["paths"].detect()
                if not env.game_root:
                    raise RuntimeError("Live game not found. Set DEADLOCK_GAME to the Steam Deadlock folder.")
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
                env = module["paths"].detect()
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
        if settings.extraction_dir:
            settings.target_dmx_relative = _logical_relative(
                path,
                Path(bpy.path.abspath(settings.extraction_dir)),
                f"{Path(settings.hero_model_path).parent.as_posix()}/{path.name}" if settings.hero_model_path else f"models/heroes_staging/{settings.hero_slug or 'hero'}/{path.name}",
            )
        context.view_layer.objects.active = arm
        settings.material_count = len(mesh.data.materials)
        proofing.bump_tick(settings)
        _status(settings, f"Hero ready: {len(arm.data.bones)} bones, {len(mesh.data.vertices):,} vertices", "OK")
        return {"FINISHED"}


class DMF_OT_import_custom(Operator):
    bl_idname = "dmf.import_custom"
    bl_label = "Import Custom Model"
    bl_description = "Import a custom glTF, GLB, FBX, OBJ, or DMX and select its mesh"

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
        settings.custom_mesh = mesh
        settings.custom_armature = arm
        context.view_layer.objects.active = mesh
        mesh.select_set(True)
        proofing.bump_tick(settings)
        _status(settings, f"Custom mesh ready: {len(mesh.data.vertices):,} vertices", "OK")
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


class DMF_OT_copy_materials(Operator):
    bl_idname = "dmf.copy_materials"
    bl_label = "Use Hero Materials"
    bl_description = "Put the imported live hero material slots on the custom mesh"

    def execute(self, context):
        settings = context.scene.dmf
        source = settings.target_body
        target = settings.custom_mesh
        if source is None or target is None:
            self.report({"ERROR"}, "Import both the hero body and a custom mesh")
            return {"CANCELLED"}
        settings.material_count = _assign_hero_materials(target, source)
        _status(settings, f"Copied {settings.material_count} hero material slots; .vmat files stay verbatim", "OK")
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


class DMF_OT_export_stage(Operator):
    bl_idname = "dmf.export_stage"
    bl_label = "Export & Stage"
    bl_description = "Export the custom mesh as DMX, then copy the unchanged S2V vmdl and its materials into a CSDK13 handoff"

    def _export(
        self,
        context,
        settings,
        target_stem: str,
        destination: Path,
        lod_count: int,
        lod_decimate: float,
    ) -> ExportedModel:
        scene = context.scene
        scene_name = scene.name
        if not hasattr(scene, "vs"):
            raise RuntimeError("PulseSrcOps is required for DMX export; enable it in Blender")
        custom = settings.custom_mesh
        armature = settings.target_armature
        if custom is None:
            raise RuntimeError("Choose a custom mesh before export")
        old_name = custom.name
        old_path = scene.vs.export_path
        old_format = scene.vs.export_format
        old_engine = scene.vs.engine
        old_dmx_format = scene.vs.dmx_format
        old_encoding = scene.vs.dmx_encoding
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
            for obj in (custom, armature)
            if obj is not None
        }
        old_lods = {
            "generate_lods": bool(getattr(custom.vs, "generate_lods", False)),
            "lod_count": int(getattr(custom.vs, "lod_count", 1)),
            "decimate_factor": float(getattr(custom.vs, "decimate_factor", 50.0)),
        }
        blocking = bpy.data.objects.get(target_stem)
        blocking_name = None
        blocking_temp_name = None
        collection = bpy.data.collections.new("DMF Export")
        collection_name = collection.name
        scene.collection.children.link(collection)
        try:
            # The imported hero body can share the target DMX stem. Move it aside
            # so the custom object can take the stem without Blender suffixing it.
            if blocking is not None and blocking is not custom:
                blocking_name = blocking.name
                blocking.name = f"DMF hero source {target_stem}"
                blocking_temp_name = blocking.name
            # The ported model owns its material slots. Overwriting them with the
            # hero's pbr.vfx/NPR slots is an explicit button, never an export side
            # effect. A custom slot path survives into the DMX unchanged.
            custom.vs.generate_lods = lod_count > 0
            custom.vs.lod_count = max(1, lod_count)
            custom.vs.decimate_factor = float(lod_decimate)
            scene.vs.export_path = str(destination) + os.sep
            scene.vs.export_format = "DMX"
            scene.vs.engine = "SOURCE"
            scene.vs.dmx_format = "22_modeldoc"
            scene.vs.dmx_encoding = "3"
            custom.name = target_stem
            collection.objects.link(custom)
            if armature is not None:
                collection.objects.link(armature)
            collection.vs.export = True
            for obj in (custom, armature):
                if obj is not None:
                    obj.vs.export = True
            # A dedicated collection makes PulseSrcOps export exactly this mesh
            # and its armature, instead of every selected object's collection.
            scene.vs.export_list.clear()
            row = scene.vs.export_list.add()
            row.name = collection.name
            row.ob_type = "COLLECTION"
            row.icon = "GROUP"
            row.collection = collection
            result = bpy.ops.export_scene.smd(collection=collection.name)
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
            # resolve the mesh and the temporary collection again by name.
            fresh = bpy.data.objects.get(target_stem) or bpy.data.objects.get(old_name)
            fresh_scene = core.fresh_scene(scene_name)
            if fresh is not None:
                fresh.name = old_name
                if hasattr(fresh, "vs"):
                    fresh.vs.generate_lods = old_lods["generate_lods"]
                    fresh.vs.lod_count = old_lods["lod_count"]
                    fresh.vs.decimate_factor = old_lods["decimate_factor"]
                if fresh_scene is not None:
                    try:
                        fresh_scene.dmf.custom_mesh = fresh
                    except Exception:
                        pass
            if blocking_name and blocking_temp_name:
                blocker = bpy.data.objects.get(blocking_temp_name)
                if blocker is not None:
                    try:
                        blocker.name = blocking_name
                    except Exception:
                        pass
            if fresh_scene is not None:
                fresh_scene.vs.export_path = old_path
                fresh_scene.vs.export_format = old_format
                fresh_scene.vs.engine = old_engine
                fresh_scene.vs.dmx_format = old_dmx_format
                fresh_scene.vs.dmx_encoding = old_encoding
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
            fresh_collection = bpy.data.collections.get(collection_name)
            if fresh_collection is not None:
                for obj in list(fresh_collection.objects):
                    fresh_collection.objects.unlink(obj)
                if fresh_scene is not None:
                    try:
                        fresh_scene.collection.children.unlink(fresh_collection)
                    except Exception:
                        pass
                bpy.data.collections.remove(fresh_collection)

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
        stage_dir = Path(bpy.path.abspath(settings.stage_dir)) if settings.stage_dir else (
            core.project_root(settings) / "artifacts" / "staged" / settings.addon_name
        )
        custom_slots = len(settings.custom_mesh.data.materials) if settings.custom_mesh else 0
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
            exported = self._export(
                context,
                settings,
                target_stem,
                export_dir,
                lod_count,
                lod_decimate,
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
            request = module["stage"].StageRequest(
                extraction_root=extraction,
                vmdl=vmdl,
                target_dmx=target_dmx,
                custom_dmx=exported.primary,
                target_dmx_relative=settings.target_dmx_relative,
                vmdl_relative=settings.vmdl_relative,
                addon_name=settings.addon_name,
                destination=stage_dir,
                materials=materials,
                custom_materials=custom_materials,
                custom_lods=exported.lods,
            )
            staged = module["stage"].stage(request)
            module["stage"].verify(staged)
            settings.stage_dir = str(staged.root.parents[2]) if len(staged.root.parents) >= 3 else str(stage_dir)
            settings.exported_dmx = str(exported.primary)
            _status(
                settings,
                f"Staged {settings.addon_name}: {len(staged.custom_lods)} LODs, {custom_slots} custom slots, "
                f"{staged.material_count} material files ({staged.material_texture_count} textures), "
                f"{staged.custom_material_count} custom; vmdl unchanged ({staged.vmdl_blake3[:10]})",
                "OK",
            )
        except Exception as error:
            _status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        finally:
            shutil.rmtree(export_dir, ignore_errors=True)
        return {"FINISHED"}


class DMF_OT_compile(Operator):
    bl_idname = "dmf.compile"
    bl_label = "Compile with CSDK13"
    bl_description = "Run resourcecompiler on the staged, unchanged vmdl without blocking the viewport"

    def execute(self, context):
        settings = context.scene.dmf
        stage_dir = Path(bpy.path.abspath(settings.stage_dir)) if settings.stage_dir else None
        if stage_dir is None:
            self.report({"ERROR"}, "Stage the model first")
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
                env = module["paths"].detect()
                progress(0.25, "running resourcecompiler")
                return module["compile"].compile_stage(env, stage_dir, addon_name, log_path=log_path)

            def done(result):
                if result.returncode:
                    _status(settings, f"CSDK13 could not compile the stage; see {result.log}", "ERROR")
                else:
                    _status(
                        settings,
                        f"CSDK13 compiled {len(result.compiled_files)} files; input vmdl unchanged; temporary CSDK mirror removed",
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
    DMF_OT_detect,
    DMF_OT_extract,
    DMF_OT_import_hero,
    DMF_OT_import_custom,
    DMF_OT_fit,
    DMF_OT_copy_materials,
    DMF_OT_retarget,
    DMF_OT_export_stage,
    DMF_OT_compile,
    DMF_OT_pick_vmdl,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
