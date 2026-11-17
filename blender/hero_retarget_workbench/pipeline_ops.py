"""Operators behind the Mods, tool-setup and Components pages.

The scan, port, backport, download and component actions all live here so the
page panels stay draw code. Long work (scanning a drive, extracting a hero,
downloading a tool) runs through ``jobs``; short file copies run inline.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import core, jobs, properties


def _settings(context):
    return context.scene.dmf


def _abspath(value: str) -> Path:
    return Path(bpy.path.abspath(value))


def _workspace(settings) -> Path:
    return core.project_root(settings)


def _fail(settings, prefix: str):
    def handler(error):
        core.set_status(settings, f"{prefix}: {error}", "ERROR")

    return handler


def _start(settings, label: str, work, done, prefix: str) -> bool:
    if settings.job_running or jobs.is_running():
        core.set_status(settings, "A background job is already running", "WARN")
        return False
    error = jobs.start(settings, label, work, done, _fail(settings, prefix))
    if error:
        core.set_status(settings, error, "WARN")
        return False
    return True


def _client_label(root: Path) -> str:
    info = root / "game" / "citadel" / "steam.inf"
    if not info.is_file():
        return ""
    values = {}
    for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return f"{values.get('ClientVersion', '')} {values.get('VersionDate', '')}".strip()


def refresh_clients(settings, module) -> list[Path]:
    """Every game and tools install, read from the trees themselves.

    The old list only looked beside the current CSDK, so a CSDK13 hid the live
    game, an older game tree, CSDK10 and a CS2 tools build. ``forge.installs``
    reads Steam's libraries and the standard preview/tools placements on every
    drive, then classifies each tree by its own gameinfo and binaries.
    """
    roots = []
    if settings.clients_folder:
        roots.append(_abspath(settings.clients_folder))
    else:
        roots.append(_workspace(settings) / "clients")
    if settings.csdk_root:
        roots.append(_abspath(settings.csdk_root).parent)
    rows = module["installs"].discover(*roots)
    active = str(_abspath(settings.csdk_root)).lower() if settings.csdk_root else ""
    target = str(_abspath(settings.mod_target_client)).lower() if settings.mod_target_client else ""
    settings.clients.clear()
    found: list[Path] = []
    for install in rows:
        row = settings.clients.add()
        row.path = str(install.root)
        row.label = install.label
        row.build = install.build
        row.kind = install.kind
        row.engine = install.engine
        row.can_compile = install.can_compile
        row.can_backport = install.can_backport
        row.active = str(install.root).lower() in (active, target)
        row.tool_active = str(install.root).lower() == active
        found.append(install.root)
    return found


class DMF_OT_add_scan_root(Operator):
    bl_idname = "dmf.add_scan_root"
    bl_label = "Add scan folder"
    bl_description = "Choose a folder the Mods page scans for old VPKs and unpacked addons"

    directory: StringProperty(subtype="DIR_PATH")
    filter_folder: BoolProperty(default=True, options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = _settings(context)
        text = bpy.path.abspath(self.directory).strip()
        if not text:
            return {"CANCELLED"}
        row = settings.scan_roots.add()
        row.path = text
        settings.scan_root_index = len(settings.scan_roots) - 1
        core.set_status(settings, f"Scan folder added: {text}", "OK")
        return {"FINISHED"}


class DMF_OT_remove_scan_root(Operator):
    bl_idname = "dmf.remove_scan_root"
    bl_label = "Remove scan folder"
    bl_description = "Stop scanning the selected folder"

    def execute(self, context):
        settings = _settings(context)
        if not settings.scan_roots:
            return {"CANCELLED"}
        index = min(settings.scan_root_index, len(settings.scan_roots) - 1)
        settings.scan_roots.remove(index)
        settings.scan_root_index = max(0, index - 1)
        return {"FINISHED"}


class DMF_OT_scan_mods(Operator):
    bl_idname = "dmf.scan_mods"
    bl_label = "Scan for mods"
    bl_description = "Inventory old VPKs and unpacked addons in every enabled scan folder"

    def execute(self, context):
        settings = _settings(context)
        module = core.core(settings)
        roots = [bpy.path.abspath(row.path) for row in settings.scan_roots if row.enabled and row.path]
        if not roots:
            self.report({"ERROR"}, "Add at least one folder to scan")
            return {"CANCELLED"}
        try:
            since = date.fromisoformat(settings.scan_since) if settings.scan_since else None
            until = date.fromisoformat(settings.scan_until) if settings.scan_until else None
        except ValueError as error:
            self.report({"ERROR"}, f"Date is not YYYY-MM-DD: {error}")
            return {"CANCELLED"}
        report = (
            _abspath(settings.mod_report)
            if settings.mod_report
            else _workspace(settings) / "mods" / "old-mods.json"
        )
        game_vpk = None
        try:
            environment = core.detect_environment(settings, module)
            game_vpk = environment.vpk
        except Exception:
            # The scan can still use Blender's built-in asset families when the
            # game is not installed or its config is unavailable.
            game_vpk = None
        # A full game is a backport target, not a toolchain. Older scenes can
        # still carry a compiler flag from files copied into a game install;
        # correct that saved row before using it as a release date.
        for row in settings.clients:
            if row.kind == "game" and row.can_backport:
                row.can_compile = False
        toolchain_labels = [
            row.build
            for row in settings.clients
            if row.can_compile
            and row.build
            and (row.kind == "tools" or not row.can_backport)
        ]
        if not toolchain_labels:
            current = core.tools_build(settings)
            if current:
                toolchain_labels = [current]

        def work(progress):
            stage = getattr(progress, "stage", None)

            def mark(key, label, value, message, state="RUNNING"):
                if stage is not None:
                    stage(key, label, value, message, state)

            progress(0.02, f"scanning {len(roots)} folders")

            found_toolchains = list(toolchain_labels)
            found_installs = []
            try:
                mark("installs", "Installed builds", 0.0, "searching detected clients")
                progress(0.03, "finding installed builds")
                extra_roots = [
                    _abspath(row.path) for row in settings.clients if row.path
                ]
                found_installs = [
                    row
                    for row in module["installs"].discover(*extra_roots)
                    if row.can_compile or row.can_backport
                ]
                mark(
                    "installs",
                    "Installed builds",
                    1.0,
                    f"{len(found_installs)} valid builds found",
                    "DONE",
                )
                if not found_toolchains:
                    found_toolchains = [
                        row.build for row in found_installs if row.can_compile and row.build
                    ]
            except Exception:
                found_toolchains = found_toolchains or []
                mark("installs", "Installed builds", 1.0, "discovery failed", "FAILED")

            known_roots = None
            known_suffixes = None
            try:
                mark("types", "Read game file types", 0.0, "reading the live pak")
                if game_vpk is not None and game_vpk.is_file():
                    progress(0.04, f"reading {game_vpk.name} types")
                    known_roots, known_suffixes = module["oldmods"].content_shape(
                        game_vpk
                    )
                    mark(
                        "types",
                        "Read game file types",
                        1.0,
                        f"{len(known_roots or ())} folders",
                        "DONE",
                    )
                else:
                    mark("types", "Read game file types", 1.0, "using built-in types", "DONE")
            except Exception as error:
                # A missing or unreadable game pak is a smaller fallback, not a
                # reason to hide the mod folders that are already on disk.
                progress(0.04, f"game types unavailable: {error}")
                mark("types", "Read game file types", 1.0, "using built-in types", "DONE")

            def walked(fraction, message):
                progress(0.02 + 0.96 * float(fraction), message)

            result = module["oldmods"].inventory(
                roots,
                since=since,
                until=until,
                progress=walked,
                known_roots=known_roots,
                known_suffixes=known_suffixes,
                toolchains=found_toolchains,
                installs=found_installs,
                stage=stage,
            )
            mark("report", "Write report", 0.0, f"writing {report.name}")
            progress(0.98, f"writing {report.name}")
            result.save(report)
            mark("report", "Write report", 1.0, "report written", "DONE")
            progress(1.0, f"{result.counts()['packages']} packages")
            return result

        def done(result):
            settings.mods.clear()
            settings.mod_matches.clear()
            for mod in result.mods:
                row = settings.mods.add()
                row.path = mod.path
                row.addon = mod.addon
                row.kind = mod.kind
                row.hero = mod.hero
                row.modified = mod.modified
                row.toolchain = mod.toolchain
                row.sections = ", ".join(mod.cloth_sections)
                row.bytes = mod.bytes
                row.note = mod.note
                row.models = "\n".join(mod.models)
                row.blends = "\n".join(mod.blends)
                row.files = "\n".join(mod.files)
                row.counts = " · ".join(
                    f"{name} {value}" for name, value in mod.counts.items() if value
                )
                row.total_files = sum(mod.counts.values())
                for match in mod.matches:
                    found = settings.mod_matches.add()
                    found.mod_path = mod.path
                    found.relative = match.relative
                    found.install = match.install
                    found.label = match.label
                    found.build = match.build
                    found.kind = match.kind
                    found.container = match.container
                    found.entry = match.entry
                    found.size = match.size
                    found.crc32 = f"{match.crc32:08x}"
                    found.gameinfo = match.gameinfo
            properties.refresh_mod_rows(settings)
            counts = result.counts()
            settings.mods_scanned = counts["packages"]
            settings.mod_report = str(report)
            settings.mod_note = (
                f"{counts['packages']} packages: {counts['addons']} folders, "
                f"{counts['vpks']} VPKs, {counts['blends']} blends, "
                f"{counts['blend_files']} blend files, {counts['with_cloth_sections']} cloth"
            )
            if counts["skipped_game_paks"]:
                settings.mod_note += f", {counts['skipped_game_paks']} engine paks skipped"
            if result.hash_note:
                settings.mod_note += f"; {result.hash_note}"
            for root_row in settings.scan_roots:
                base = Path(bpy.path.abspath(root_row.path)).resolve()
                matched = [
                    mod
                    for mod in result.mods
                    if Path(mod.path).resolve().is_relative_to(base)
                ]
                root_row.packages = len(matched)
                root_row.folders = sum(1 for mod in matched if mod.kind == "addon")
                root_row.vpks = sum(1 for mod in matched if mod.kind == "vpk")
                root_row.blends = sum(1 for mod in matched if mod.kind == "blend")
                root_row.with_cloth = sum(1 for mod in matched if mod.cloth_sections)
            core.set_status(settings, f"Scanned {counts['packages']} packages", "OK")

        if not _start(settings, "Scanning old mods", work, done, "Scan failed"):
            return {"CANCELLED"}
        return {"FINISHED"}


def _selected_mod(settings):
    if not settings.mod_rows:
        return None
    index = min(max(settings.mod_index, 0), len(settings.mod_rows) - 1)
    return settings.mod_rows[index]


def _mod_vmdl(row) -> str:
    models = [line.strip() for line in (row.models or "").splitlines() if line.strip()]
    hero = (row.hero or "").split(",")[0].strip().lower()
    for suffix in (".vmdl", ".vmdl_c"):
        preferred = next(
            (
                path
                for path in models
                if path.lower().endswith(suffix) and hero and hero in path.lower()
            ),
            None,
        )
        if preferred:
            return preferred
    for suffix in (".vmdl", ".vmdl_c"):
        found = next((path for path in models if path.lower().endswith(suffix)), "")
        if found:
            return found
    return ""


def _mod_matches(settings, row) -> list[dict]:
    """The selected package's install matches, in the shape migrate expects."""
    return [
        {
            "relative": item.relative,
            "install": item.install,
            "label": item.label,
            "build": item.build,
            "kind": item.kind,
            "container": item.container,
            "entry": item.entry,
            "gameinfo": item.gameinfo,
            "crc32": item.crc32,
        }
        for item in settings.mod_matches
        if item.mod_path == row.path
    ]


def _selected_nodes(settings) -> list[str] | None:
    if not settings.mod_nodes:
        return None
    return [item.name for item in settings.mod_nodes if item.selected]


def _source_slug(value: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (value or "mod").strip())
    return "_".join(part for part in slug.split("_") if part) or "mod"


def _scene_source(settings, context) -> dict[str, str]:
    """Bind the current Blender scene as the custom model source.

    A project opened from a mod's own .blend is already a Blender scene; asking
    S2V to extract that .blend would be a category error. The largest mesh is
    the same choice the DMX importer makes, and its armature is the rig the
    Source page's custom-model fields expect.
    """
    meshes = [obj for obj in context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("mod-source-scene-empty: the open project carries no mesh")
    mesh = max(meshes, key=lambda obj: len(obj.data.vertices))
    armature = mesh.find_armature()
    if armature is None and mesh.parent is not None and mesh.parent.type == "ARMATURE":
        armature = mesh.parent
    settings.custom_mesh = mesh
    settings.custom_armature = armature
    settings.custom_name = mesh.name
    project = Path(settings.project_file).name if settings.project_file else "open scene"
    settings.source_origin = f"project {project}"
    settings.mod_source_kind = "blend"
    return {
        "origin": settings.source_origin,
        "mesh": mesh.name,
        "armature": armature.name if armature is not None else "no rig",
    }


def _start_package_source(settings, context, package: Path, row=None) -> bool:
    """Fill the Source page from a package without updating it to the live hero."""
    package = _abspath(str(package))
    if not package.exists():
        raise RuntimeError(f"old-package-missing: {package}")
    if package.suffix.lower() in (".blend", ".blend1"):
        current = _abspath(settings.project_file).resolve() if settings.project_file else None
        if current is not None and current == package.resolve():
            result = _scene_source(settings, context)
            core.set_status(
                settings,
                f"Using {result['origin']} as source: {result['mesh']} with {result['armature']}",
                "OK",
            )
            return True
        raise RuntimeError(
            f"old-source-is-blend: {package}; open the project, then use Use project as source"
        )
    module = core.core(settings)
    env = core.detect_environment(settings, module)
    name = (getattr(row, "addon", "") if row is not None else "") or package.stem
    hero = (getattr(row, "hero", "") if row is not None else "").split(",")[0].strip()
    preferred = (
        _mod_vmdl(row) if row is not None else settings.mod_source_vmdl or settings.update_old_vmdl
    )
    matches = _mod_matches(settings, row) if row is not None else []
    kind = getattr(row, "kind", "") if row is not None else package.suffix.lower().lstrip(".")
    destination = _workspace(settings) / "sources" / _source_slug(name)

    def work(progress):
        progress.stage("package", "Read package", 0.08, f"reading {package.name}")
        progress(0.2, "extracting the old package")
        result = module["migrate"].resolve_package_source(
            env,
            package,
            destination,
            old_vmdl=preferred or None,
            hero=hero,
            matches=matches,
        )
        progress.stage("package", "Read package", 1.0, "package read", "DONE")
        progress.stage(
            "model",
            "Resolve model",
            1.0,
            f"{Path(result['vmdl']).name}, {result['material_count']} material assets",
            "DONE",
        )
        return result

    def done(result):
        root = result["root"]
        material_root = result["materials_dir"] or root
        settings.extraction_dir = root
        settings.vmdl = result["vmdl"]
        settings.vmdl_relative = result["vmdl_relative"]
        settings.body_dmx = result["body_dmx"]
        settings.target_dmx_relative = result["body_relative"]
        settings.materials_dir = material_root
        settings.custom_materials_dir = material_root
        settings.old_vpk = str(package)
        settings.update_old_vmdl = result["vmdl"]
        settings.mod_source_package = str(package)
        settings.mod_source_addon = name
        settings.mod_source_kind = kind
        settings.mod_source_vmdl = preferred or result["vmdl_relative"]
        settings.source_origin = f"old mod {name}"
        if result["body_dmx"]:
            core.set_status(
                settings,
                f"Using {name} as source: {Path(result['vmdl']).name}, body {Path(result['body_dmx']).name}, "
                f"{result['material_count']} material assets. Source page points at this package.",
                "OK",
            )
        else:
            core.set_status(
                settings,
                f"Using {name} as source: {Path(result['vmdl']).name} and {result['material_count']} material assets; "
                "the model named no body DMX, so choose one in Source > Files.",
                "WARN",
            )

    if not _start(settings, f"Reading {name} as source", work, done, "Source read failed"):
        return False
    core.set_status(settings, f"Reading {name} as a Source-page file set", "BUSY")
    return True


class DMF_OT_use_mod_source(Operator):
    bl_idname = "dmf.use_mod_source"
    bl_label = "Use mod as source"
    bl_description = "Read the selected old package as a Source-page model, body and material set without updating it to the live hero"

    def execute(self, context):
        settings = _settings(context)
        row = _selected_mod(settings)
        package = None
        if row is not None:
            package = Path(row.path)
        elif settings.mod_source_package:
            package = Path(settings.mod_source_package)
        if package is None:
            self.report({"ERROR"}, "Select a package or create a project from one first")
            return {"CANCELLED"}
        try:
            started = _start_package_source(settings, context, package, row)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"} if started else {"CANCELLED"}


class DMF_OT_use_project_source(Operator):
    bl_idname = "dmf.use_project_source"
    bl_label = "Use project as source"
    bl_description = "Use the package the active project was created from, or the open Blender scene, as the Source-page model"

    def execute(self, context):
        settings = _settings(context)
        package = Path(settings.mod_source_package) if settings.mod_source_package else None
        try:
            if package is not None and not package.exists():
                raise RuntimeError(f"mod-source-package-missing: {package}")
            if package is not None and package.suffix.lower() not in (".blend", ".blend1"):
                started = _start_package_source(settings, context, package)
            else:
                result = _scene_source(settings, context)
                core.set_status(
                    settings,
                    f"Using {result['origin']} as source: {result['mesh']} with {result['armature']}",
                    "OK",
                )
                started = True
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"} if started else {"CANCELLED"}


class DMF_OT_analyze_mod(Operator):
    bl_idname = "dmf.analyze_mod"
    bl_label = "Analyze package"
    bl_description = "Resolve the old model, list the nodes it carries, and compare its files with the live hero"

    def execute(self, context):
        settings = _settings(context)
        row = _selected_mod(settings)
        if row is None:
            self.report({"ERROR"}, "Select a package first")
            return {"CANCELLED"}
        if row.kind == "blend":
            self.report({"ERROR"}, "Blend projects are edited directly; there is no model to analyze")
            return {"CANCELLED"}
        hero_slug = (row.hero or "").split(",")[0].strip()
        if not hero_slug:
            self.report({"ERROR"}, "This package does not name a hero model")
            return {"CANCELLED"}
        module = core.core(settings)
        env = core.detect_environment(settings, module)
        if env.game_root is None or env.s2v is None:
            self.report({"ERROR"}, "Set the live game and Source 2 Viewer in Setup first")
            return {"CANCELLED"}
        old_path = _abspath(row.path)
        old_vmdl = _mod_vmdl(row)
        matches = _mod_matches(settings, row)
        slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (row.addon or old_path.stem))
        output = _workspace(settings) / "analysis" / (slug or "package")

        def work(progress):
            progress(0.03, "reading the live hero roster")
            heroes = module["live"].list_heroes(env)
            hero = next((item for item in heroes if item.slug.lower() == hero_slug.lower()), None)
            if hero is None:
                raise RuntimeError(f"Hero {hero_slug} is not in the live roster")
            progress(0.2, "resolving both models")
            return module["migrate"].analyze_package(
                env,
                old_path,
                output,
                hero=hero,
                old_vmdl=Path(old_vmdl) if old_vmdl else None,
                old_matches=matches,
            )

        def done(result):
            settings.mod_nodes.clear()
            for node in result.get("nodes", []):
                item = settings.mod_nodes.add()
                item.name = node["name"]
                item.selected = bool(node.get("selected"))
                item.changed = bool(node.get("changed"))
                item.old_lines = int(node.get("old_lines", 0))
                item.new_lines = int(node.get("new_lines", 0))
            settings.mod_diffs.clear()
            for diff in result.get("files", []):
                item = settings.mod_diffs.add()
                item.path = diff["path"]
                item.state = diff["state"]
                item.old_size = diff.get("old_size", 0)
                item.new_size = diff.get("new_size", 0)
            settings.mod_node_index = 0
            settings.mod_diff_index = 0
            source = result.get("old_source") or {}
            settings.mod_analysis_old_vmdl = result.get("old_vmdl", "")
            settings.mod_analysis_new_vmdl = result.get("new_vmdl", "")
            settings.mod_analysis_source = source.get("kind", "source")
            settings.mod_analysis_note = (
                f"{len(settings.mod_nodes)} nodes, {len(settings.mod_diffs)} differing files"
            )
            if settings.mod_analysis_source == "compiled":
                settings.mod_analysis_note += (
                    f"; compiled model matched {source.get('install_build') or 'no installed build'}"
                )
            core.set_status(settings, f"Analyzed {row.addon}: {settings.mod_analysis_note}", "OK")

        if not _start(settings, f"Analyzing {row.addon}", work, done, "Analyze failed"):
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_port_mod(Operator):
    bl_idname = "dmf.port_mod"
    bl_label = "Update to latest"
    bl_description = "Transplant the selected old package onto the live hero model"

    def execute(self, context):
        settings = _settings(context)
        row = _selected_mod(settings)
        if row is None:
            self.report({"ERROR"}, "Scan for mods and select a package first")
            return {"CANCELLED"}
        hero_slug = (row.hero or "").split(",")[0].strip()
        if not hero_slug:
            self.report({"ERROR"}, "This package does not name a hero model")
            return {"CANCELLED"}
        module = core.core(settings)
        env = core.detect_environment(settings, module)
        if env.game_root is None or env.s2v is None:
            self.report({"ERROR"}, "Set the live game and Source 2 Viewer in Setup first")
            return {"CANCELLED"}
        if env.csdk_root is None:
            self.report({"ERROR"}, "Choose the CSDK13 toolchain in Setup so the update can stage into it")
            return {"CANCELLED"}
        old_path = _abspath(row.path)
        old_vmdl = _mod_vmdl(row)
        old_matches = _mod_matches(settings, row)
        sections = _selected_nodes(settings)
        addon = f"{(row.addon or old_path.stem).strip().replace(' ', '_')}_updated"
        output = (
            _abspath(settings.update_output)
            if settings.update_output
            else _workspace(settings) / "ports"
        )
        # Name the output before work starts so a failure still shows the addon
        # and the Stage button points at the tree that was attempted.
        settings.update_addon_name = addon
        settings.update_output = str(output)
        model_policy = settings.update_model_policy
        preserve_materials = settings.update_preserve_materials

        def work(progress):
            progress(0.05, "reading the live hero roster")
            heroes = module["live"].list_heroes(env)
            hero = next((item for item in heroes if item.slug.lower() == hero_slug.lower()), None)
            if hero is None:
                raise RuntimeError(f"Hero {hero_slug} is not in the live roster")
            progress(0.2, "extracting and migrating")
            result = module["migrate"].update_from_package(
                env,
                old_path,
                output,
                addon,
                hero=hero,
                old_vmdl=Path(old_vmdl) if old_vmdl else None,
                old_matches=old_matches,
                preserve_model=model_policy,
                preserve_materials=preserve_materials,
                sections=sections,
                force=True,
            )
            progress(0.9, f"staging {addon} in {env.csdk_root.name}")
            installed = module["compile"].stage_content(env, result.output, addon)
            progress(0.98, "staged for material editing")
            return result, installed

        def done(payload):
            result, installed = payload
            settings.old_vpk = str(old_path)
            settings.update_addon_name = addon
            settings.addon_name = addon
            settings.update_output = str(output)
            settings.stage_dir = str(env.csdk_root)
            settings.extraction_dir = str(result.new_root)
            actions = ", ".join(f"{name}:{action['action']}" for name, action in result.sections.items()) or "no sections"
            core.set_status(
                settings,
                f"Ported {row.addon} onto {hero_slug}: {actions}; staged {result.material_count} old material assets in {installed}. "
                "Edit the material files there, then press Compile.",
                "OK",
            )

        if not _start(settings, f"Porting {row.addon}", work, done, "Port failed"):
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_backport_mod(Operator):
    bl_idname = "dmf.backport_mod"
    bl_label = "Backport to client (experimental)"
    bl_description = "Transplant the selected package onto an older client's hero model"

    def execute(self, context):
        settings = _settings(context)
        if not settings.backport_experimental:
            self.report({"ERROR"}, "Enable backport first; it is experimental")
            return {"CANCELLED"}
        row = _selected_mod(settings)
        if row is None:
            self.report({"ERROR"}, "Select a package first")
            return {"CANCELLED"}
        if not settings.mod_target_client:
            self.report({"ERROR"}, "Choose a target client in Setup > Clients")
            return {"CANCELLED"}
        relative = _mod_vmdl(row)
        if not relative and not row.hero:
            self.report(
                {"ERROR"},
                "The package names no model and no hero, so the target build cannot be searched",
            )
            return {"CANCELLED"}
        module = core.core(settings)
        env = core.detect_environment(settings, module)
        old_path = _abspath(row.path)
        client = _abspath(settings.mod_target_client)
        matches = _mod_matches(settings, row)
        sections = _selected_nodes(settings)
        addon = f"{(row.addon or old_path.stem).strip().replace(' ', '_')}_backport"
        output = _workspace(settings) / "backports"

        def work(progress):
            progress(
                0.05,
                f"searching {client.name} for {relative or row.hero or 'the hero model'}",
            )
            return module["backport"].backport_package(
                env,
                client,
                old_path,
                output,
                addon,
                relative=relative,
                hero=row.hero,
                old_matches=matches,
                preserve_model=settings.update_model_policy,
                preserve_materials=settings.update_preserve_materials,
                sections=sections,
                force=True,
            )

        def done(result):
            settings.stage_dir = str(result.output)
            settings.extraction_dir = str(result.new_root)
            actions = ", ".join(f"{name}:{action['action']}" for name, action in result.sections.items()) or "no sections"
            detail = ""
            try:
                data = json.loads(Path(result.manifest).read_text(encoding="utf-8"))
                detail = f" using {data.get('backport_model', '')}"
                if not data.get("backport_exact_model", True):
                    detail += " (path moved in this build)"
            except (OSError, ValueError):
                pass
            core.set_status(
                settings,
                f"Backported {row.addon} onto {client.name} (experimental):{detail}; {actions}",
                "OK",
            )

        if not _start(settings, f"Backporting {row.addon}", work, done, "Backport failed"):
            return {"CANCELLED"}
        return {"FINISHED"}


def _project_slug(value: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (value or "mod").strip())
    return "_".join(part for part in slug.split("_") if part) or "mod"


def _mod_blend(row) -> Path | None:
    """An existing blend inside the selected package, when it has one."""
    if row.kind == "blend":
        path = _abspath(row.path)
        return path if path.is_file() else None
    if row.kind != "addon":
        return None
    for line in (row.blends or "").splitlines():
        path = _abspath(row.path) / line
        if path.is_file():
            return path
    return None


class DMF_OT_create_mod_project(Operator):
    bl_idname = "dmf.create_mod_project"
    bl_label = "Create Blender project"
    bl_description = "Open a blend the mod carries, or save the current scene as a project for it"

    def invoke(self, context, event):
        row = _selected_mod(_settings(context))
        if row is not None and _mod_blend(row) is not None and bpy.data.is_dirty:
            return context.window_manager.invoke_confirm(
                self,
                event,
                title="Open the mod's Blender project?",
                message="The current file has unsaved changes. Opening the project replaces it.",
                confirm_text="Open project",
                icon="WARNING",
            )
        return self.execute(context)

    def execute(self, context):
        settings = _settings(context)
        row = _selected_mod(settings)
        if row is None:
            self.report({"ERROR"}, "Scan for mods and select a package first")
            return {"CANCELLED"}
        blend = _mod_blend(row)
        if blend is not None:
            try:
                bpy.ops.wm.open_mainfile(filepath=str(blend))
            except RuntimeError as error:
                core.set_status(settings, f"Could not open {blend.name}: {error}", "ERROR")
                return {"CANCELLED"}
            # The .blend may predate this addon and carry no project fields, so
            # point the freshly loaded scene at the file that was just opened.
            opened = _settings(context)
            opened.project_root = str(blend.parent)
            opened.project_file = str(blend)
            opened.mod_source_package = str(blend)
            opened.mod_source_addon = blend.stem
            opened.mod_source_kind = "blend"
            opened.mod_source_vmdl = ""
            core.set_status(opened, f"Opened project {blend.name}", "OK")
            return {"FINISHED"}

        base = _workspace(settings) / "projects" / _project_slug(row.addon or Path(row.path).stem)
        base.mkdir(parents=True, exist_ok=True)
        target = base / f"{base.name}.blend"
        suffix = 2
        while target.exists():
            target = base / f"{base.name}-{suffix}.blend"
            suffix += 1
        # Set the fields before saving the copy, so reopening the project keeps
        # its own active-project card instead of reverting to no project.
        previous = (
            settings.project_root,
            settings.project_file,
            settings.mod_source_package,
            settings.mod_source_addon,
            settings.mod_source_kind,
            settings.mod_source_vmdl,
        )
        settings.project_root = str(base)
        settings.project_file = str(target)
        # Remember the package the project came from. Reopening this .blend and
        # pressing Use project as source then reads the same package again.
        settings.mod_source_package = str(_abspath(row.path))
        settings.mod_source_addon = row.addon or Path(row.path).stem
        settings.mod_source_kind = row.kind
        settings.mod_source_vmdl = _mod_vmdl(row)
        try:
            bpy.ops.wm.save_as_mainfile(filepath=str(target), copy=True)
        except RuntimeError as error:
            (
                settings.project_root,
                settings.project_file,
                settings.mod_source_package,
                settings.mod_source_addon,
                settings.mod_source_kind,
                settings.mod_source_vmdl,
            ) = previous
            core.set_status(settings, f"Could not create {target.name}: {error}", "ERROR")
            return {"CANCELLED"}
        core.set_status(settings, f"Created project {target.name} in {base}", "OK")
        return {"FINISHED"}


class DMF_OT_open_project_folder(Operator):
    bl_idname = "dmf.open_project_folder"
    bl_label = "Open project folder"
    bl_description = "Open the active project folder in the file browser"

    def execute(self, context):
        settings = _settings(context)
        folder = Path(settings.project_root) if settings.project_root else _workspace(settings)
        if not folder.is_dir():
            self.report({"ERROR"}, f"Project folder does not exist: {folder}")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=str(folder))
        return {"FINISHED"}


class DMF_OT_install_s2v(Operator):
    bl_idname = "dmf.install_s2v"
    bl_label = "Download Source 2 Viewer CLI"
    bl_description = "Download the latest Source 2 Viewer CLI archive and point Setup at it"

    def execute(self, context):
        settings = _settings(context)
        module = core.core(settings)
        folder = _abspath(settings.tools_folder) if settings.tools_folder else _workspace(settings) / "tools"

        def work(progress):
            version, _url = module["provision"].latest_cli_release()
            cli = module["provision"].install_s2v(folder, progress=progress)
            return cli, version

        def done(result):
            cli, version = result
            settings.s2v_cli = str(cli)
            settings.s2v_version = version
            settings.tools_note = f"Source 2 Viewer {version} installed at {cli}"
            core.set_status(settings, f"Source 2 Viewer {version} installed", "OK")

        if not _start(settings, "Downloading Source 2 Viewer", work, done, "Download failed"):
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_open_csdk_page(Operator):
    bl_idname = "dmf.open_csdk_page"
    bl_label = "Open CSDK 13 download page"
    bl_description = "Open the community CSDK13 page; its Google Drive and Mega links are not direct downloads"

    def execute(self, context):
        settings = _settings(context)
        module = core.core(settings)
        import webbrowser

        webbrowser.open(module["provision"].CSDK13_PAGE)
        settings.tools_note = (
            "Download the Reduced CSDK 13 archive from that page, then install the zip here."
        )
        return {"FINISHED"}


class DMF_OT_install_csdk(Operator):
    bl_idname = "dmf.install_csdk"
    bl_label = "Install CSDK archive"
    bl_description = "Extract a downloaded Reduced CSDK zip into the clients folder and select it"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.zip", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = _settings(context)
        module = core.core(settings)
        archive = _abspath(self.filepath)
        if not archive.is_file():
            self.report({"ERROR"}, "Choose a downloaded CSDK zip")
            return {"CANCELLED"}
        folder = (
            _abspath(settings.clients_folder)
            if settings.clients_folder
            else _workspace(settings) / "clients"
        )

        def work(progress):
            return module["provision"].install_archive(archive, folder, progress=progress)

        def done(root):
            settings.csdk_root = str(root)
            refresh_clients(settings, module)
            settings.tools_note = f"CSDK installed at {root}"
            core.set_status(settings, f"CSDK installed at {root.name}", "OK")

        if not _start(settings, "Installing CSDK", work, done, "CSDK install failed"):
            return {"CANCELLED"}
        return {"FINISHED"}


class DMF_OT_refresh_clients(Operator):
    bl_idname = "dmf.refresh_clients"
    bl_label = "Find clients"
    bl_description = "Find every game and tools install in Steam libraries and the standard preview folders"

    def execute(self, context):
        settings = _settings(context)
        module = core.core(settings)
        found = refresh_clients(settings, module)
        compile_count = sum(1 for row in settings.clients if row.can_compile)
        target_count = sum(1 for row in settings.clients if row.can_backport)
        core.set_status(
            settings,
            f"Found {len(found)} installs: {compile_count} with a compiler, {target_count} backport targets",
            "OK",
        )
        return {"FINISHED"}


class DMF_OT_add_client(Operator):
    bl_idname = "dmf.add_client"
    bl_label = "Add client folder"
    bl_description = "Register an existing CSDK install as a client this file can target"

    directory: StringProperty(subtype="DIR_PATH")
    filter_folder: BoolProperty(default=True, options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = _settings(context)
        path = _abspath(self.directory)
        if not core.is_csdk_install(path):
            self.report({"ERROR"}, "That folder has no game/bin/win64/resourcecompiler.exe")
            return {"CANCELLED"}
        module = core.core(settings)
        refresh_clients(settings, module)
        settings.csdk_root = str(path)
        refresh_clients(settings, module)
        core.set_status(settings, f"Client added: {path.name}", "OK")
        return {"FINISHED"}


class DMF_OT_use_client(Operator):
    bl_idname = "dmf.use_client"
    bl_label = "Use this client"
    bl_description = "Extract from the selected game client and follow its build"

    def execute(self, context):
        settings = _settings(context)
        if not settings.clients:
            return {"CANCELLED"}
        index = min(max(settings.client_index, 0), len(settings.clients) - 1)
        row = settings.clients[index]
        if not row.can_backport:
            core.set_status(
                settings,
                f"{row.label} carries no Citadel VPKs; choose a game client here or a compiler row in Compile toolchain",
                "WARN",
            )
            return {"CANCELLED"}
        previous = core._norm(settings.deadlock_root)
        settings.deadlock_root = row.path
        settings.build = row.build or core.source_build(settings)
        # Keep the old one-selection workflow: if the backport target was the
        # extraction client, it follows the new one. A deliberately different
        # target stays where it is.
        if not settings.mod_target_client or core._norm(settings.mod_target_client) == previous:
            settings.mod_target_client = row.path
        for item in settings.clients:
            item.active = item.path == row.path
        core.set_status(
            settings,
            f"Extracting from {row.label} ({row.build or 'build unknown'})",
            "OK",
        )
        return {"FINISHED"}


class DMF_OT_use_backport_client(Operator):
    bl_idname = "dmf.use_backport_client"
    bl_label = "Use this backport client"
    bl_description = "Target the selected game client for a backport, separately from extraction"

    def execute(self, context):
        settings = _settings(context)
        if not settings.clients:
            return {"CANCELLED"}
        index = min(max(settings.client_index, 0), len(settings.clients) - 1)
        row = settings.clients[index]
        if not row.can_backport:
            core.set_status(
                settings,
                f"{row.label} carries no Citadel VPKs and cannot be a backport target",
                "WARN",
            )
            return {"CANCELLED"}
        settings.mod_target_client = row.path
        core.set_status(
            settings,
            f"Backporting to {row.label} ({row.build or 'build unknown'})",
            "OK",
        )
        return {"FINISHED"}


class DMF_OT_use_toolchain(Operator):
    bl_idname = "dmf.use_toolchain"
    bl_label = "Use this toolchain"
    bl_description = "Compile and pack with the selected install's resourcecompiler, separately from the game files"

    index: IntProperty(name="Toolchain", default=-1)

    def execute(self, context):
        settings = _settings(context)
        rows = [row for row in settings.clients if row.can_compile]
        if not rows:
            core.set_status(settings, "No install with a resourcecompiler was found", "ERROR")
            return {"CANCELLED"}
        index = self.index if self.index >= 0 else settings.toolchain_index
        index = min(max(index, 0), len(rows) - 1)
        row = rows[index]
        settings.csdk_root = row.path
        settings.toolchain_index = index
        for item in settings.clients:
            item.tool_active = item.path == row.path
        label = row.build or row.label
        core.set_status(settings, f"Compiling with {row.label} ({label})", "OK")
        return {"FINISHED"}


def _component_source(settings) -> tuple[Path | None, Path | None]:
    """The extraction and model vmdl the Components page should read.

    The body DMX is the authority on a non-hero import.  A model chosen from
    the expanded roster can live under a different extraction than the one the
    page last remembered, and the vmdl beside that body is the model whose
    render list names its components.  Fall back to the extraction fields for
    a hand-picked folder with no imported body.
    """
    body = _abspath(settings.body_dmx) if settings.body_dmx else None
    root = _abspath(settings.extraction_dir) if settings.extraction_dir else None
    if body is not None and body.is_file():
        if root is None or not root.is_dir() or root.resolve() not in body.resolve().parents:
            root = next(
                (parent.parent for parent in body.parents if parent.name.lower() == "models"),
                body.parent,
            )
    vmdl = _abspath(settings.vmdl) if settings.vmdl else None
    if vmdl is not None and (not vmdl.is_file() or (root and root.resolve() not in vmdl.resolve().parents)):
        vmdl = None
    if vmdl is None and body is not None and body.is_file():
        vmdl = next(iter(sorted(body.parent.glob("*.vmdl"))), None)
    if vmdl is None and root is not None and root.is_dir():
        vmdl = next(iter(sorted(root.rglob("*.vmdl"))), None)
    return root, vmdl


class DMF_OT_scan_components(Operator):
    bl_idname = "dmf.scan_components"
    bl_label = "Find components"
    bl_description = "Find the current model's render-mesh components, hero or non-hero"

    def execute(self, context):
        settings = _settings(context)
        module = core.core(settings)
        root, vmdl = _component_source(settings)
        if root is None or not root.is_dir():
            self.report({"ERROR"}, "Extract a model first; its folder holds the component meshes")
            return {"CANCELLED"}
        try:
            found = module["components"].inventory(root, vmdl=vmdl)
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        settings.components.clear()
        for item in found:
            row = settings.components.add()
            row.name = item.name
            row.relative = item.relative
            row.path = str(item.path)
            row.kind = item.kind
            row.bytes = item.bytes
            row.selected = item.kind == "dmx" and not getattr(item, "primary", False)
        model = vmdl.stem if vmdl is not None else root.name
        meshes = sum(1 for item in found if item.kind == "dmx")
        components = sum(
            1 for item in found if item.kind == "dmx" and not getattr(item, "primary", False)
        )
        settings.component_note = (
            f"{model}: {components} components, {meshes} render meshes"
            if components
            else f"{model}: {meshes} render mesh{'es' if meshes != 1 else ''}, no separate components"
        )
        if not settings.component_addon:
            settings.component_addon = settings.addon_name
        core.set_status(settings, settings.component_note, "OK" if components else "WARN")
        return {"FINISHED"}


class DMF_OT_pick_component_vmdl(Operator):
    bl_idname = "dmf.pick_component_vmdl"
    bl_label = "Choose target vmdl"
    bl_description = "Choose the staged addon vmdl that receives the component render mesh and body group"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.vmdl", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = _settings(context)
        settings.component_vmdl = self.filepath
        return {"FINISHED"}


class DMF_OT_stage_components(Operator):
    bl_idname = "dmf.stage_components"
    bl_label = "Stage selected components"
    bl_description = (
        "Copy the selected component files into the component addon and, when a target vmdl "
        "is chosen, register each DMX as a render mesh and a body-group choice"
    )

    def execute(self, context):
        settings = _settings(context)
        module = core.core(settings)
        selected = [row for row in settings.components if row.selected]
        if not selected:
            self.report({"ERROR"}, "Tick at least one component")
            return {"CANCELLED"}
        addon = (settings.component_addon or settings.addon_name or "").strip()
        if not addon:
            self.report({"ERROR"}, "Name the component addon")
            return {"CANCELLED"}
        vmdl = None
        if settings.component_merge:
            if not settings.component_vmdl:
                self.report({"ERROR"}, "Choose the target vmdl or turn off Register in vmdl")
                return {"CANCELLED"}
            vmdl = _abspath(settings.component_vmdl)
            if not vmdl.is_file():
                self.report({"ERROR"}, f"Target vmdl not found: {vmdl}")
                return {"CANCELLED"}
        files = [
            module["components"].ComponentFile(
                name=row.name,
                path=_abspath(row.path),
                relative=row.relative,
                kind=row.kind,
                bytes=row.bytes,
            )
            for row in selected
        ]
        try:
            manifest = module["components"].stage(
                files,
                _workspace(settings) / "components",
                addon=addon,
                hero=settings.hero_slug,
                extraction_root=_abspath(settings.extraction_dir) if settings.extraction_dir else None,
                vmdl=vmdl,
                bodygroup=settings.component_slot.strip(),
            )
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        data = json.loads(manifest.read_text(encoding="utf-8"))
        settings.component_manifest = str(manifest)
        settings.component_note = (
            f"Staged {len(files)} files; vmdl merge: {data.get('vmdl_merge')}; "
            f"body group: {settings.component_slot.strip() or 'none'}"
        )
        core.set_status(settings, settings.component_note, "OK")
        return {"FINISHED"}


CLASSES = (
    DMF_OT_add_scan_root,
    DMF_OT_remove_scan_root,
    DMF_OT_scan_mods,
    DMF_OT_analyze_mod,
    DMF_OT_use_mod_source,
    DMF_OT_use_project_source,
    DMF_OT_port_mod,
    DMF_OT_backport_mod,
    DMF_OT_create_mod_project,
    DMF_OT_open_project_folder,
    DMF_OT_install_s2v,
    DMF_OT_open_csdk_page,
    DMF_OT_install_csdk,
    DMF_OT_refresh_clients,
    DMF_OT_add_client,
    DMF_OT_use_client,
    DMF_OT_use_toolchain,
    DMF_OT_use_backport_client,
    DMF_OT_scan_components,
    DMF_OT_pick_component_vmdl,
    DMF_OT_stage_components,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
