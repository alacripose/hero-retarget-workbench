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
    box = layout.box()
    row = box.row()
    row.label(text=title, icon=icon)
    if detail:
        row.label(text=_short(detail, 26))
    return box


def _hint(layout, text: str, icon: str = "INFO") -> None:
    if text:
        layout.label(text=_short(text, 48), icon=icon)


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
            "CSDK & clients",
            "PACKAGE",
            Path(settings.csdk_root).name if settings.csdk_root else "choose one",
        )
        csdk.prop(settings, "csdk_root", text="Active")
        row = csdk.row(align=True)
        row.operator("dmf.open_csdk_page", text="Get CSDK 13", icon="URL")
        row.operator("dmf.install_csdk", text="Install zip", icon="FILEBROWSER")
        csdk.prop(settings, "clients_folder", text="Clients")
        row = csdk.row(align=True)
        row.operator("dmf.refresh_clients", text="Find clients", icon="FILE_REFRESH")
        row.operator("dmf.add_client", text="Add folder", icon="FILE_FOLDER")
        if settings.clients:
            csdk.template_list(
                "DMF_UL_clients",
                "",
                settings,
                "clients",
                settings,
                "client_index",
                rows=3,
            )
            use = csdk.row(align=True)
            use.alignment = "RIGHT"
            use.operator("dmf.use_client", text="Use this client", icon="CHECKMARK")
        else:
            _hint(csdk, "Find clients, or install a downloaded Reduced CSDK zip.", "QUESTION")


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
        scan = _section(layout, "Scan folders", "FILE_FOLDER", f"{len(settings.scan_roots)} roots")
        for row in settings.scan_roots:
            line = scan.row(align=True)
            line.prop(row, "enabled", text="")
            line.label(text=_short(row.path, 36), icon="FILE_FOLDER")
            right = line.row(align=True)
            right.alignment = "RIGHT"
            if row.packages:
                right.label(text=f"{row.packages}" + (f" / {row.with_cloth} cloth" if row.with_cloth else ""))
        row = scan.row(align=True)
        row.operator("dmf.add_scan_root", text="Add folder", icon="ADD")
        row.operator("dmf.remove_scan_root", text="Remove", icon="REMOVE")
        dates = scan.row(align=True)
        dates.prop(settings, "scan_since", text="Since")
        dates.prop(settings, "scan_until", text="Until")
        scan.operator("dmf.scan_mods", text="Scan for mods", icon="VIEWZOOM")
        if settings.mod_note:
            _hint(scan, settings.mod_note, "INFO")

        packages = _section(layout, "Packages", "PACKAGE", f"{settings.mods_scanned} found")
        if settings.mods:
            packages.template_list(
                "DMF_UL_mods",
                "",
                settings,
                "mods",
                settings,
                "mod_index",
                rows=6,
            )
            row = packages.row(align=True)
            row.operator("dmf.port_mod", text="Update to latest", icon="FILE_REFRESH")
            row.prop(settings, "backport_experimental", text="Backport")
            if settings.backport_experimental:
                packages.prop(settings, "mod_target_client", text="Client")
                packages.operator(
                    "dmf.backport_mod",
                    text="Backport to client (experimental)",
                    icon="LOOP_BACK",
                )
            _hint(
                packages,
                "Update transplants onto today's hero. Backport searches every VPK in the target build and uses the model's path, or the hero if the path moved.",
            )
        else:
            _hint(packages, "Add a folder and scan for VPKs and unpacked addons.", "QUESTION")
        if settings.mod_report:
            packages.label(text=_short(settings.mod_report, 44), icon="TEXT")


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
        source = _section(layout, "Live components", "MESH_DATA", Path(settings.extraction_dir).name if settings.extraction_dir else "no extraction")
        source.operator("dmf.scan_components", text="Find components", icon="VIEWZOOM")
        if settings.components:
            source.template_list(
                "DMF_UL_components",
                "",
                settings,
                "components",
                settings,
                "component_index",
                rows=6,
            )
            for row in settings.components:
                _ = row
        else:
            _hint(source, "Extract a hero first; its guns, hats and attachments are listed here.", "QUESTION")

        target = _section(layout, "Stage beside a mod", "MODIFIER", settings.component_slot or "no body group")
        target.prop(settings, "component_addon", text="Addon")
        row = target.row(align=True)
        row.prop(settings, "component_vmdl", text="vmdl")
        row.operator("dmf.pick_component_vmdl", text="", icon="FILEBROWSER")
        target.prop(settings, "component_merge", text="Register in vmdl")
        target.prop(settings, "component_slot", text="Body group")
        _hint(
            target,
            "Each staged DMX becomes a RenderMeshFile and a BodyGroupChoice; the existing body stays.",
            "INFO",
        )
        target.operator("dmf.stage_components", text="Stage selected", icon="IMPORT")
        if settings.component_note:
            _hint(target, settings.component_note, "INFO")
        if settings.component_manifest:
            target.label(text=_short(settings.component_manifest, 44), icon="TEXT")


CLASSES = (DMF_PT_setup_tools, DMF_PT_mods, DMF_PT_components)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
