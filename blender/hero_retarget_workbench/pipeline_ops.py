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
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from . import core, jobs


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

        def work(progress):
            progress(0.02, f"scanning {len(roots)} folders")

            def walked(fraction, message):
                progress(0.02 + 0.93 * float(fraction), message)

            result = module["oldmods"].inventory(
                roots, since=since, until=until, progress=walked
            )
            progress(0.96, f"writing {report.name}")
            result.save(report)
            progress(1.0, f"{result.counts()['packages']} packages")
            return result

        def done(result):
            settings.mods.clear()
            for mod in result.mods:
                row = settings.mods.add()
                row.path = mod.path
                row.addon = mod.addon
                row.kind = mod.kind
                row.hero = mod.hero
                row.modified = mod.modified
                row.sections = ", ".join(mod.cloth_sections)
                row.bytes = mod.bytes
                row.note = mod.note
                row.models = "\n".join(mod.models)
            counts = result.counts()
            settings.mods_scanned = counts["packages"]
            settings.mod_report = str(report)
            settings.mod_note = (
                f"{counts['packages']} packages, {counts['addons']} addons, "
                f"{counts['vpks']} VPKs, {counts['with_cloth_sections']} with cloth, "
                f"{counts['skipped_game_paks']} engine paks skipped"
            )
            for root_row in settings.scan_roots:
                base = bpy.path.abspath(root_row.path).replace("\\", "/").lower()
                matched = [
                    mod for mod in result.mods if Path(mod.path).as_posix().lower().startswith(base)
                ]
                root_row.packages = len(matched)
                root_row.with_cloth = sum(1 for mod in matched if mod.cloth_sections)
            core.set_status(settings, f"Scanned {counts['packages']} packages", "OK")

        if not _start(settings, "Scanning old mods", work, done, "Scan failed"):
            return {"CANCELLED"}
        return {"FINISHED"}


def _selected_mod(settings):
    if not settings.mods:
        return None
    index = min(max(settings.mod_index, 0), len(settings.mods) - 1)
    return settings.mods[index]


def _mod_vmdl(row) -> str:
    models = [line.strip() for line in (row.models or "").splitlines() if line.strip()]
    hero = (row.hero or "").split(",")[0].strip().lower()
    preferred = next(
        (path for path in models if path.lower().endswith(".vmdl") and hero and hero in path.lower()),
        None,
    )
    return preferred or next((path for path in models if path.lower().endswith(".vmdl")), "")


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
        old_path = _abspath(row.path)
        old_vmdl = _mod_vmdl(row)
        addon = f"{(row.addon or old_path.stem).strip().replace(' ', '_')}_updated"
        output = (
            _abspath(settings.update_output)
            if settings.update_output
            else _workspace(settings) / "ports"
        )

        def work(progress):
            progress(0.05, "reading the live hero roster")
            heroes = module["live"].list_heroes(env)
            hero = next((item for item in heroes if item.slug.lower() == hero_slug.lower()), None)
            if hero is None:
                raise RuntimeError(f"Hero {hero_slug} is not in the live roster")
            progress(0.2, "extracting and migrating")
            return module["migrate"].update_from_package(
                env,
                old_path,
                output,
                addon,
                hero=hero,
                old_vmdl=Path(old_vmdl) if old_vmdl else None,
                preserve_model=settings.update_model_policy,
                preserve_materials=settings.update_preserve_materials,
                force=True,
            )

        def done(result):
            settings.old_vpk = str(old_path)
            settings.update_addon_name = addon
            settings.stage_dir = str(result.output)
            settings.extraction_dir = str(result.new_root)
            actions = ", ".join(f"{name}:{action['action']}" for name, action in result.sections.items()) or "no sections"
            core.set_status(settings, f"Ported {row.addon} onto {hero_slug}: {actions}", "OK")

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
                preserve_model=settings.update_model_policy,
                preserve_materials=settings.update_preserve_materials,
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
    bl_description = "Make the selected client the CSDK this file compiles with"

    def execute(self, context):
        settings = _settings(context)
        if not settings.clients:
            return {"CANCELLED"}
        index = min(max(settings.client_index, 0), len(settings.clients) - 1)
        row = settings.clients[index]
        used = []
        if row.can_compile:
            settings.csdk_root = row.path
            used.append("compiler")
        if row.can_backport:
            settings.mod_target_client = row.path
            used.append("backport target")
        if not used:
            core.set_status(
                settings,
                f"{row.label} is neither a compiler host nor has Citadel VPKs",
                "WARN",
            )
            return {"CANCELLED"}
        for item in settings.clients:
            item.active = item.path == row.path
        core.set_status(settings, f"Using {row.label} for {' and '.join(used)}", "OK")
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
    DMF_OT_port_mod,
    DMF_OT_backport_mod,
    DMF_OT_install_s2v,
    DMF_OT_open_csdk_page,
    DMF_OT_install_csdk,
    DMF_OT_refresh_clients,
    DMF_OT_add_client,
    DMF_OT_use_client,
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
