"""The Mods, tool-setup and Components pages.

Mods is the pipeline the owner asked for: folders to scan, what the scan found,
and one button that transplants a package onto the live hero (or, as an
experiment, onto an older client). Tools lives on Setup and installs Source 2
Viewer from its release, opens the community CSDK13 page and manages several
CSDK-style clients. Components stages cosmetic-shaped meshes and registers them
as render meshes and body-group choices in a staged vmdl.
"""
from __future__ import annotations

from pathlib import Path

import bpy
from bpy.types import Panel

from . import ui_popit


def _short(value: str, limit: int = 34) -> str:
    text = " ".join((value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _section(layout, title: str, icon: str, detail: str = ""):
    return ui_popit.section(layout, title, icon, _short(detail, 26) if detail else "")


def _hint(layout, text: str, icon: str = "INFO") -> None:
    if text:
        layout.label(text=_short(text, 48), icon=icon)


def _tail(value: str, limit: int = 48) -> str:
    text = value or ""
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


def _size(value: int) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "0 B"


def _chips(layout, settings, prop: str, values) -> None:
    for start in range(0, len(values), 3):
        row = layout.row(align=True)
        row.scale_y = 1.1
        for value, label in values[start:start + 3]:
            row.prop_enum(settings, prop, value, text=label)


def _project_label(row) -> str:
    blend = row.kind == "blend" or (row.kind == "addon" and bool(row.blends))
    return "Open project" if blend else "Create project"


class DMF_PT_setup_tools(Panel):
    bl_label = "Tools & clients"
    bl_idname = "DMF_PT_setup_tools"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout

        ui_popit.title(
            layout,
            "Tools & clients",
            settings.s2v_version or ("S2V installed" if settings.s2v_cli else "S2V missing"),
            "TOOL_SETTINGS" if settings.s2v_cli else "QUESTION",
            alert=not settings.s2v_cli,
        )
        tools = _section(
            layout,
            "Source 2 Viewer",
            "FILEBROWSER",
            settings.s2v_version or ("installed" if settings.s2v_cli else "not installed"),
        )
        tools.prop(settings, "s2v_cli", text="CLI")
        row = tools.row(align=True)
        row.operator("dmf.install_s2v", text="Download & install", icon="IMPORT")
        row.operator("dmf.detect_paths", text="Detect", icon="FILE_REFRESH")
        if settings.tools_note:
            _hint(tools, settings.tools_note, "INFO")

        csdk = _section(
            layout,
            "Game clients",
            "PACKAGE",
            Path(settings.mod_target_client).name if settings.mod_target_client else "choose one",
        )
        csdk.prop(settings, "clients_folder", text="Clients")
        row = csdk.row(align=True)
        row.operator("dmf.refresh_clients", text="Find clients", icon="FILE_REFRESH")
        row.operator("dmf.add_client", text="Add folder", icon="FILE_FOLDER")
        if settings.clients:
            head = csdk.split(factor=settings.list_name_width, align=True)
            head.label(text="Install")
            right = head.row(align=True)
            right.alignment = "RIGHT"
            right.label(text="Kind · build")
            csdk.template_list(
                "DMF_UL_clients",
                "",
                settings,
                "clients",
                settings,
                "client_index",
                rows=5,
            )
            csdk.prop(settings, "list_name_width", text="Name width", slider=True)
            picked = settings.clients[min(settings.client_index, len(settings.clients) - 1)]
            ui_popit.stat(csdk, "build", picked.build or "unknown", "INFO")
            ui_popit.stat(csdk, "path", _short(picked.path, 42), "FILE_FOLDER")
            roles = csdk.row(align=True)
            roles.label(text="Game files", icon="CHECKMARK" if picked.can_backport else "X")
            roles.label(text="Compiler", icon="CHECKMARK" if picked.can_compile else "X")
            use = csdk.row(align=True)
            use.operator("dmf.use_client", text="Use for extraction", icon="CHECKMARK")
            use.operator("dmf.use_backport_client", text="Use for backport", icon="LOOP_BACK")
        else:
            _hint(
                csdk,
                "Find clients reads game and tools installs on every Steam library and the standard preview folders.",
                "QUESTION",
            )
            _hint(
                csdk,
                "A compiler host builds the handoff; a game with Citadel VPKs is a backport target.",
                "INFO",
            )


class DMF_PT_setup_toolchains(Panel):
    bl_label = "Compile toolchains"
    bl_idname = "DMF_PT_setup_toolchains"
    bl_parent_id = "DMF_PT_setup_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        from . import core

        chain = _section(
            layout,
            "Compile toolchains",
            "TOOL_SETTINGS",
            core.tools_build(settings) or "choose one",
        )
        chain.prop(settings, "csdk_root", text="Active")
        toolchains = [row for row in settings.clients if row.can_compile]
        if toolchains:
            ui_popit.micro(chain, "Versions found", "PACKAGE")
            for index, row in enumerate(toolchains[:10]):
                line = chain.row(align=True)
                line.alert = not row.tool_active
                line.label(
                    text=_short(row.label, 18),
                    icon="CHECKMARK" if row.tool_active else "TOOL_SETTINGS",
                )
                right = line.row(align=True)
                right.alignment = "RIGHT"
                right.label(text=_short(row.build or row.kind, 22))
                button = right.operator("dmf.use_toolchain", text="", icon="PLAY")
                button.index = index
                if row.tool_active:
                    chain.label(text=_short(row.path, 42), icon="FILE_FOLDER")
        else:
            _hint(
                chain,
                "Find clients lists every compiler host with its own build; choose one here.",
                "INFO",
            )
        row = chain.row(align=True)
        row.operator("dmf.open_csdk_page", text="Get CSDK", icon="URL")
        row.operator("dmf.install_csdk", text="Install zip", icon="FILEBROWSER")
        row.operator("dmf.refresh_clients", text="Find", icon="FILE_REFRESH")


class DMF_PT_mods(Panel):
    bl_label = "Mods"
    bl_idname = "DMF_PT_mods"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout

        ui_popit.job(layout, settings)
        ui_popit.page(
            layout,
            settings,
            "Mods",
            f"{settings.mods_scanned} found" if settings.mods_scanned else "not scanned",
            "PACKAGE",
        )

        scan = _section(layout, "Scan folders", "FILE_FOLDER", f"{len(settings.scan_roots)} roots")
        scan.template_list(
            "DMF_UL_scan_roots",
            "",
            settings,
            "scan_roots",
            settings,
            "scan_root_index",
            rows=3,
        )
        if settings.scan_roots:
            root = settings.scan_roots[min(settings.scan_root_index, len(settings.scan_roots) - 1)]
            scan.prop(root, "path", text="Folder")
        row = scan.row(align=True)
        row.operator("dmf.add_scan_root", text="Add folder", icon="ADD")
        row.operator("dmf.remove_scan_root", text="Remove", icon="REMOVE")
        scan.prop(settings, "scan_since", text="Since")
        scan.prop(settings, "scan_until", text="Until")
        scan.operator("dmf.scan_mods", text="Scan for mods", icon="VIEWZOOM")
        if settings.mod_note:
            ui_popit.bubble(scan, settings.mod_note, "INFO", width=30, max_lines=3)

        found = _section(layout, "Mod collection", "PACKAGE", f"{len(settings.mods)} packages")
        if settings.mods:
            folders = sum(1 for row in settings.mods if row.kind == "addon")
            vpks = sum(1 for row in settings.mods if row.kind == "vpk")
            blends = sum(1 for row in settings.mods if row.kind == "blend")
            _chips(
                found,
                settings,
                "mod_filter",
                [
                    ("ALL", f"All {len(settings.mods)}"),
                    ("FOLDER", f"Folders {folders}"),
                    ("VPK", f"VPKs {vpks}"),
                    ("BLEND", f"Blends {blends}"),
                ],
            )
            found.template_list(
                "DMF_UL_mods",
                "",
                settings,
                "mod_rows",
                settings,
                "mod_index",
                rows=6,
            )
            if not settings.mod_rows:
                _hint(found, "No packages of this type in the last scan.", "INFO")
        else:
            _hint(found, "Add a folder and scan for VPKs, addon folders and blends.", "QUESTION")

        if settings.mod_rows:
            selected = settings.mod_rows[min(settings.mod_index, len(settings.mod_rows) - 1)]
            icons = {"vpk": "PACKAGE", "addon": "FILE_FOLDER", "blend": "FILE_BLEND"}
            detail = _section(
                layout,
                selected.addon or Path(selected.path).name,
                icons.get(selected.kind, "PACKAGE"),
                f"{selected.total_files:,} files" if selected.total_files else selected.kind,
            )
            detail.label(text=Path(selected.path).name, icon="FILE")
            detail.label(text=_tail(str(Path(selected.path).parent), 44), icon="FILE_FOLDER")
            ui_popit.stat(detail, "Kind", selected.kind)
            ui_popit.stat(detail, "Hero", selected.hero or "unknown")
            ui_popit.stat(detail, "Updated", selected.modified or "unknown")
            ui_popit.stat(detail, "Size", _size(selected.bytes))
            if selected.counts:
                _hint(detail, selected.counts, "FILE")

            project = detail.row(align=True)
            project.scale_y = 1.2
            project.operator(
                "dmf.create_mod_project",
                text=_project_label(selected),
                icon="FILE_BLEND",
            )
            if selected.blends and selected.kind != "blend":
                detail.label(
                    text=_short(selected.blends.splitlines()[0], 44),
                    icon="FILE_BLEND",
                )

            if settings.mod_content_filter:
                content_counts = {}
                for row in settings.mod_contents:
                    content_counts[row.category] = content_counts.get(row.category, 0) + 1
                content_chips = [("ALL", f"All {len(settings.mod_contents)}")]
                for value, label in (
                    ("MODELS", "Models"),
                    ("CLIPS", "Clips"),
                    ("MATERIALS", "Materials"),
                    ("BLENDS", "Blends"),
                    ("OTHER", "Other"),
                ):
                    count = content_counts.get(value.lower(), 0)
                    if count:
                        content_chips.append((value, f"{label} {count}"))
                contents = _section(
                    layout,
                    "Contents",
                    "FILE",
                    f"{len(settings.mod_content_rows)} shown",
                )
                _chips(contents, settings, "mod_content_filter", content_chips)
                contents.template_list(
                    "DMF_UL_mod_contents",
                    "",
                    settings,
                    "mod_content_rows",
                    settings,
                    "mod_content_index",
                    rows=6,
                )
                if not settings.mod_content_rows:
                    _hint(contents, "No files of this type in the package.", "INFO")

            actions = _section(layout, "Update and backport", "FILE_REFRESH")
            if selected.kind != "blend":
                row = actions.row(align=True)
                row.operator("dmf.port_mod", text="Update to latest", icon="FILE_REFRESH")
                row.prop(settings, "backport_experimental", text="Backport")
                if settings.backport_experimental:
                    actions.prop(settings, "mod_target_client", text="Target client")
                    actions.operator(
                        "dmf.backport_mod",
                        text="Backport to client (experimental)",
                        icon="LOOP_BACK",
                    )
            else:
                _hint(actions, "Blend projects are edited directly; update does not apply.", "INFO")
            _hint(
                actions,
                "Update transplants onto today's hero. Backport searches every VPK in the target build and uses the model's path, or the hero if the path moved.",
            )
        if settings.mod_report:
            layout.label(text=_short(settings.mod_report, 44), icon="TEXT")


class DMF_PT_components(Panel):
    bl_label = "Components"
    bl_idname = "DMF_PT_components"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout

        ui_popit.job(layout, settings)
        ui_popit.page(
            layout,
            settings,
            "Components",
            f"{len(settings.components)} found" if settings.components else "not scanned",
            "MODIFIER",
        )
        model = Path(settings.vmdl).stem if settings.vmdl else (Path(settings.extraction_dir).name if settings.extraction_dir else "no model")
        source = _section(layout, "Live components", "MESH_DATA", model)
        ui_popit.stat(
            source,
            "from",
            _short(settings.vmdl or settings.extraction_dir, 34) or "extract a model",
            "FILE_FOLDER",
        )
        source.operator("dmf.scan_components", text="Find components", icon="VIEWZOOM")
        if settings.components:
            head = source.split(factor=settings.list_name_width, align=True)
            head.label(text="Component")
            right = head.row(align=True)
            right.alignment = "RIGHT"
            right.label(text="Kind")
            source.template_list(
                "DMF_UL_components",
                "",
                settings,
                "components",
                settings,
                "component_index",
                rows=6,
            )
            source.prop(settings, "list_name_width", text="Name width", slider=True)
            for row in settings.components:
                _ = row
        else:
            _hint(source, "Extract a model first; its vmdl render meshes are listed here, hero or not.", "QUESTION")

        target = _section(layout, "Stage beside a mod", "MODIFIER", settings.component_slot or "no body group")
        target.prop(settings, "component_addon", text="Addon")
        row = target.row(align=True)
        row.prop(settings, "component_vmdl", text="vmdl")
        row.operator("dmf.pick_component_vmdl", text="", icon="FILEBROWSER")
        ui_popit.stat(
            target,
            "into",
            _short(settings.component_vmdl or settings.component_addon, 34) or "not set",
            "FILE",
        )
        target.prop(settings, "component_merge", text="Register in vmdl")
        target.prop(settings, "component_slot", text="Body group")
        _hint(
            target,
            "Each selected component DMX becomes a RenderMeshFile and a BodyGroupChoice; the existing body stays.",
            "INFO",
        )
        target.operator("dmf.stage_components", text="Stage selected", icon="IMPORT")
        if settings.component_note:
            _hint(target, settings.component_note, "INFO")
        if settings.component_manifest:
            target.label(text=_short(settings.component_manifest, 44), icon="TEXT")


CLASSES = (DMF_PT_setup_tools, DMF_PT_setup_toolchains, DMF_PT_mods, DMF_PT_components)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
