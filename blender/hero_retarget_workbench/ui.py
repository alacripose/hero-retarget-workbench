"""Native Blender sidebar for the hero retarget workbench.

The surface follows the Popit model the owner's references define: a page opens
under its named panel, states its build and next action once, and groups the
controls with space instead of nested cards. Advanced groups fold away and the
page is allowed a single message. Blender's own dark theme supplies colour; the
panel only decides what is worth showing.

The surface is Operate: native widgets, dense information, no wizard. The panel
does not claim a result. It shows the live stage, the bone map, the proof checks
and the exact refusal that blocks the handoff.
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy
from bpy.types import Panel
from forge import bonerules, paths, stageflow

from . import clipops, core, heropick, properties, rules, tailops, tailpreview, ui_popit, workbench


_STATUS_ICONS = {
    "INFO": "STATUS_INFO",
    "BUSY": "TIME",
    "OK": "CHECKMARK",
    "ERROR": "ERROR",
    "WARN": "STATUS_WARNING",
}

_CHECK_ICONS = {
    "pass": "CHECKMARK",
    "fail": "ERROR",
    "unchecked": "QUESTION",
    "absent": "BLANK1",
    "stale": "TIME",
    "refused": "CANCEL",
}

_STATE_LABELS = {
    "MAPPED": "mapped",
    "UNMATCHED": "unmatched",
    "EXTRA": "extra",
    "IGNORED": "ignored",
}


def _hero_label(settings) -> str:
    slug = settings.hero_slug
    if slug in ("", "NONE"):
        return "no model"
    title = heropick.title_for(slug)
    if title:
        return title
    if settings.hero_model_path:
        return Path(settings.hero_model_path).stem.replace("_", " ").title()
    return Path(slug).stem.replace("_", " ").title()


def _hero_state(settings) -> str:
    if settings.source_origin:
        if not settings.body_dmx:
            return "import model" if settings.extraction_dir else "choose body"
        if settings.target_body is None and settings.target_armature is None:
            return "import needed"
        return "imported"
    if not settings.build:
        return "not detected"
    if settings.hero_slug in ("", "NONE"):
        return "choose a hero"
    if not settings.body_dmx:
        return "import model" if settings.extraction_dir else "extract"
    if settings.target_body is None and settings.target_armature is None:
        return "import needed"
    return "imported"


def _chips(layout, settings, prop: str, values) -> None:
    """A filter as visible choices, not a dropdown that hides the active one."""
    ui_popit.chips(layout, settings, prop, values)


def _hero_picker(layout, settings) -> None:
    """Search, a real VPK folder, a short list and one confirm; no roster dropdown."""
    search = layout.row(align=True)
    search.prop(settings, "hero_query", text="", icon="VIEWZOOM")
    search.operator("dmf.refresh_heroes", text="", icon="FILE_REFRESH")
    current = next(
        (item[1] for item in properties.MODEL_ROOT_ITEMS if item[0] == settings.model_root),
        "All folders",
    )
    layout.operator("dmf.browse_folders", text=f"VPK folder: {current}", icon="FILE_FOLDER")
    try:
        shown = heropick.ensure(settings)
    except Exception:
        shown = len(settings.hero_rows)
    ui_popit.column_header(
        layout,
        settings.source_name_width,
        ("Model", "Folder"),
        (1.0,),
    )
    layout.template_list(
        "DMF_UL_heroes",
        "source",
        settings,
        "hero_rows",
        settings,
        "hero_index",
        rows=max(1, min(7, shown)),
    )
    ui_popit.name_width(layout, settings, "source_name_width")
    ui_popit.glyphs(
        layout,
        ["dmf.choose_hero"],
        enabled=bool(shown) and not settings.job_running,
        labels={"dmf.choose_hero": "Use model"},
    )
    if settings.hero_model_path:
        layout.label(text=settings.hero_model_path, icon="FILE")


def _mesh_state(settings) -> str:
    mesh = settings.custom_mesh
    if mesh is None:
        return "not set"
    return mesh.name


def _bind_state(settings) -> str:
    mesh = settings.custom_mesh
    armature = settings.target_armature
    if mesh is None or armature is None:
        return "not ready"
    for modifier in mesh.modifiers:
        if modifier.type == "ARMATURE" and modifier.object is armature:
            return "bound"
    if mesh.vertex_groups:
        return "weights ready"
    return "needs weights"


def _proof_gate(settings) -> str:
    if not settings.proof_checks:
        return "unchecked"
    tokens = {row.token for row in settings.proof_checks}
    if tokens <= {"pass"}:
        if settings.proof_status == "current":
            return "pass"
        return "refused" if settings.proof_status == "refused" else "stale"
    if any(token in ("fail", "stale", "refused", "absent") for token in tokens):
        return "fail"
    return "unchecked"


def _stage_state(settings) -> dict:
    """Plain answers about how far the port has got, for the next-step line."""
    folder = core.csdk_addon_folder(settings)
    staged = folder is not None and (folder / "stage.json").is_file()
    root = core.csdk_addon_root(settings)
    compiled = False
    if root is not None and folder is not None and settings.vmdl_relative.strip():
        compiled = (
            root
            / "game"
            / "citadel_addons"
            / settings.addon_name
            / Path(settings.vmdl_relative).with_suffix(".vmdl_c")
        ).is_file()
    armature = settings.target_armature
    mesh = settings.custom_mesh
    bound = _bind_state(settings) in ("bound", "weights ready")
    return {
        "setup": bool(root is not None and settings.deadlock_root and settings.s2v_cli),
        "build": bool(settings.build),
        "hero": settings.hero_slug not in ("", "NONE"),
        "extract": bool(settings.body_dmx),
        "import": armature is not None or settings.target_body is not None,
        "model": mesh is not None,
        "fit": mesh is not None and settings.axis_tick > 0,
        "parts": bool(settings.custom_collection is not None),
        "weights": bound,
        "proof": _proof_gate(settings) == "pass",
        "stage": staged,
        "compile": compiled,
    }


def _next_line(layout, settings) -> None:
    """The single hub line: what this workbench wants answered next."""
    state = _stage_state(settings)
    step = stageflow.next_step(state)
    answered, total = stageflow.progress(state)
    row = layout.row(align=True)
    row.scale_y = 1.1
    row.label(text=step.label, icon=step.icon)
    right = row.row(align=True)
    right.alignment = "RIGHT"
    right.label(text=f"{answered}/{total}")
    if step.detail:
        row = layout.row(align=True)
        row.scale_y = 0.8
        row.alignment = "RIGHT"
        row.label(text=step.detail)


def _section(layout, title: str, icon: str, detail: str = ""):
    """One grammar for every group: ui_popit.section, with the detail shortened."""
    return ui_popit.section(layout, title, icon, detail)


def _hint(layout, text: str, icon: str = "INFO", alert: bool = False, width: int | None = None) -> None:
    """The shared wrapped hint; width is measured, never a per-call guess."""
    ui_popit.hint(layout, text, icon, alert, width)


def _path_row(layout, settings, prop: str, label: str, button: str = "", icon: str = "FILEBROWSER") -> None:
    row = layout.row(align=True)
    row.prop(settings, prop, text=label)
    if button:
        row.operator(button, text="", icon=icon)


def _primary(layout, operator: str, text: str, icon: str, enabled: bool = True) -> None:
    row = layout.row(align=True)
    row.scale_y = 1.45
    row.enabled = enabled
    row.operator(operator, text=text, icon=icon)


def surface_name() -> str:
    """Which page surface register() produced; the addon module owns the value."""
    module = sys.modules.get(__package__ or "")
    return str(getattr(module, "SURFACE", "unregistered")) if module else "unregistered"


def surface_error() -> str:
    """Why the editor surface was declined, when this build could have had one."""
    module = sys.modules.get(__package__ or "")
    return str(getattr(module, "EDITOR_ERROR", "")) if module else ""


def _surface(layout) -> None:
    """The way out of the sidebar: open the page surface this build has."""
    module = sys.modules.get(__package__ or "")
    version = ".".join(
        str(part) for part in getattr(module, "bl_info", {}).get("version", ())
    )
    if version:
        layout.label(text=f"Hero Retarget Workbench {version}", icon="INFO")
    error = surface_error()
    if surface_name() == "editor":
        layout.operator("dmf.open_workbench", text="Open the Workbench editor", icon="WINDOW")
        if error:
            layout.label(text=f"Editor note: {error}", icon="INFO")
        return
    layout.operator("dmf.open_workbench", text="Open the Workbench sidebar", icon="VIEW3D")
    layout.label(
        text="This Blender build cannot register editor types; use the sidebar (N)",
        icon="INFO",
    )


def _job(layout, settings) -> None:
    """The shared job block: the bar while running, the last run's steps after."""
    ui_popit.job(layout, settings)


class DMF_PT_main(Panel):
    bl_label = "Workbench"
    bl_idname = "DMF_PT_main"
    bl_description = "Port a custom mesh onto a live Deadlock hero with an explicit bone map and an Axis proof"
    bl_icon = "OUTLINER_OB_ARMATURE"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        page = ui_popit.title(
            layout,
            _hero_label(settings),
            settings.build or "no build",
            "OUTLINER_OB_ARMATURE",
            alert=settings.status_kind == "ERROR",
        )
        _next_line(page, settings)
        if settings.compare_active:
            page.label(text="Split compare active", icon="SPLIT_VERTICAL")
        ui_popit.bubble(
            layout,
            settings.status,
            _STATUS_ICONS.get(settings.status_kind, "STATUS_INFO"),
            alert=settings.status_kind == "ERROR",
        )
        _job(layout, settings)
        _surface(layout)


class DMF_PT_setup(Panel):
    bl_label = "Setup"
    bl_idname = "DMF_PT_setup"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout

        ui_popit.job(layout, settings)
        ready = bool(settings.deadlock_root and settings.s2v_cli and settings.csdk_root)
        ui_popit.page(
            layout,
            settings,
            "Setup",
            "ready" if ready else "paths missing",
            "CHECKMARK" if ready else "QUESTION",
            alert=not ready,
        )
        live = _section(layout, "Live game", "WORLD", settings.build or "not detected")
        live.prop(settings, "deadlock_root", text="Install")
        live.prop(settings, "s2v_cli", text="S2V CLI")
        gui_note = paths.s2v_gui_note(settings.s2v_cli)
        if gui_note:
            _hint(live, gui_note, "ERROR", alert=True)
        ui_popit.glyphs(live, ["dmf.detect_paths"], labels={"dmf.detect_paths": "Detect paths"})

        tools = _section(
            layout,
            "Compile toolchain",
            "TOOL_SETTINGS",
            core.tools_build(settings) or "no build",
        )
        tools.prop(settings, "csdk_root", text="Install")
        folder = core.csdk_addon_folder(settings)
        if folder is not None:
            tools.label(text=str(folder), icon="FILE_FOLDER")
        else:
            _hint(tools, "Set the CSDK folder that holds resourcecompiler.exe.", "QUESTION")
        ui_popit.stat(tools, "selected", Path(settings.csdk_root).name if settings.csdk_root else "not set", "TOOL_SETTINGS")
        tools.operator("dmf.refresh_clients", text="Find toolchains", icon="FILE_REFRESH")

        project = Path(settings.project_file) if settings.project_file else None
        workspace = _section(
            layout,
            "Mods & projects",
            "PACKAGE",
            f"{len(settings.scan_roots)} roots, {settings.mods_scanned} found",
        )
        if project is not None:
            workspace.label(text=str(project), icon="FILE_BLEND")
            workspace.label(
                text=str(Path(settings.project_root) if settings.project_root else project.parent),
                icon="FILE_FOLDER",
            )
            row = workspace.row(align=True)
            row.operator("dmf.open_project_folder", text="Open folder", icon="FILE_FOLDER")
            row.prop_enum(settings, "props_page", "MODS", text="Mods", icon="PACKAGE")
            workspace.operator(
                "dmf.use_project_source",
                text="Use project as source",
                icon="IMPORT",
            ).enabled = not settings.job_running
        else:
            _hint(workspace, "No project open.", "QUESTION")
            workspace.prop_enum(settings, "props_page", "MODS", text="Open Mods", icon="PACKAGE")


class DMF_PT_source(Panel):
    bl_label = "Source"
    bl_idname = "DMF_PT_source"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        ui_popit.job(layout, settings)
        hero = ui_popit.page(layout, settings, "Source", _hero_state(settings), "WORLD")
        _hero_picker(hero, settings)
        if settings.source_origin:
            ui_popit.stat(hero, "Source", settings.source_origin, "PACKAGE")
        ui_popit.glyphs(
            hero,
            ["dmf.detect", "dmf.extract"],
            enabled=not settings.job_running,
            labels={"dmf.detect": "Detect build", "dmf.extract": "Extract hero"},
        )
        _primary(hero, "dmf.import_hero", "Import model", "IMPORT", enabled=not settings.job_running)
        hero.prop(settings, "target_armature", text="Skeleton")
        hero.prop(settings, "target_body", text="Body")

        custom = ui_popit.title(layout, "Your model", _mesh_state(settings), "MESH_DATA")
        ui_popit.glyphs(
            custom,
            ["dmf.import_custom"],
            enabled=not settings.job_running,
            labels={"dmf.import_custom": "Import model"},
        )
        custom.prop(settings, "custom_mesh", text="Mesh")
        custom.prop(settings, "custom_armature", text="Rig")
        name_row = custom.row(align=True)
        name_row.prop(settings, "custom_name", text="Name")
        name_row.operator("dmf.apply_model_name", text="Apply", icon="SORTALPHA")
        custom.prop(settings, "axis_preset", text="Axis")
        custom.prop(settings, "fit_scale", text="Scale")
        custom.prop(settings, "fit_to_height", text="Match hero height")
        _primary(custom, "dmf.fit", "Fit to hero", "TRANSFORM_ORIGINS", enabled=not settings.job_running)


class DMF_PT_source_files(Panel):
    bl_label = "Files"
    bl_idname = "DMF_PT_source_files"
    bl_parent_id = "DMF_PT_source"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        if settings.source_origin:
            layout.label(text=f"Source: {settings.source_origin}", icon="PACKAGE")
        _path_row(layout, settings, "body_dmx", "Body DMX")
        _path_row(layout, settings, "vmdl", "Hero vmdl")
        layout.operator("dmf.pick_vmdl", text="Choose S2V vmdl", icon="FILEBROWSER")
        _path_row(layout, settings, "materials_dir", "Hero materials")
        _path_row(layout, settings, "custom_model", "Model file")
        _path_row(layout, settings, "custom_materials_dir", "Model materials")
        _hint(layout, "Blank uses the extraction folder.", "MATERIAL")


class DMF_PT_update(Panel):
    bl_label = "Update old addon"
    bl_idname = "DMF_PT_update"
    bl_parent_id = "DMF_PT_mods"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        box = layout.column(align=True)
        _path_row(box, settings, "old_vpk", "VPK / folder")
        box.operator("dmf.pick_old_vpk", text="Choose old addon", icon="FILEBROWSER")
        options = box.column(align=True)
        options.prop(settings, "update_model_policy", text="Old model")
        options.prop(settings, "update_preserve_cloth", text="Keep cloth/physics")
        options.prop(settings, "update_preserve_materials", text="Copy old materials")
        options.prop(settings, "update_addon_name", text="Updated addon")
        _primary(
            box,
            "dmf.update_old_addon",
            "Import, update & stage",
            "FILE_REFRESH",
            enabled=not settings.job_running and settings.hero_slug not in ("", "NONE"),
        )
        stage = box.row(align=True)
        stage.enabled = bool(settings.update_addon_name.strip()) and not settings.job_running
        stage.operator("dmf.stage_update", text="Stage update in CSDK", icon="FILE_FOLDER")
        _hint(
            box,
            "The update copies its content tree, including old material files, into the CSDK content addon shown in Setup. Edit those files there; Compile stays a separate step.",
            "INFO",
        )

        advanced = _section(layout, "Advanced", "OPTIONS")
        _path_row(advanced, settings, "update_old_vmdl", "Old vmdl")
        advanced.operator("dmf.pick_old_vmdl", text="Choose old vmdl", icon="FILEBROWSER")
        _path_row(advanced, settings, "update_output", "Output stage")
        advanced.prop(settings, "update_replace_output", text="Replace output folder")


class DMF_PT_parts(Panel):
    bl_label = "Parts"
    bl_idname = "DMF_PT_parts"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        ui_popit.job(layout, settings)
        collection_box = ui_popit.page(
            layout,
            settings,
            "Parts",
            f"{len(settings.parts)}" if settings.parts else "not scanned",
            "GROUP",
        )
        ui_popit.micro(collection_box, "Parts collection", "FILE_FOLDER")
        if bpy.data.collections:
            ui_popit.column_header(
                collection_box,
                settings.collection_name_width,
                ("Collection", "Meshes", "Objects"),
                (0.2, 0.2),
            )
            collection_box.template_list(
                "DMF_UL_collections",
                "parts_collections",
                bpy.data,
                "collections",
                settings,
                "collection_index",
                rows=min(len(bpy.data.collections), 5),
            )
            ui_popit.name_width(collection_box, settings, "collection_name_width")
            collection_box.operator(
                "dmf.use_collection",
                text="Use selected collection",
                icon="FILE_FOLDER",
            )
        else:
            _hint(collection_box, "No Blender collections in this file.", "QUESTION")
        ui_popit.glyphs(
            collection_box,
            ["dmf.use_active_collection", "dmf.scan_parts"],
            labels={"dmf.use_active_collection": "Use active", "dmf.scan_parts": "Scan parts"},
        )
        if not settings.parts:
            _hint(collection_box, "Choose a collection and scan it.", "QUESTION")
        else:
            ui_popit.column_header(
                collection_box,
                settings.parts_name_width,
                ("Part", "Verts", "Materials"),
                (0.2, 0.2),
            )
            row = collection_box.row(align=True)
            row.template_list(
                "DMF_UL_parts",
                "parts",
                settings,
                "parts",
                settings,
                "part_index",
                rows=4,
            )
            ui_popit.name_width(collection_box, settings, "parts_name_width")
            index = max(0, min(settings.part_index, len(settings.parts) - 1))
            part = settings.parts[index].object
            if part is not None:
                ui_popit.stat(collection_box, "part", part.name, "OBJECT_DATA")
                collection_box.operator("dmf.use_part", text="Use selected part", icon="OBJECT_DATA")
            else:
                _hint(collection_box, "Selected object is gone. Scan again.", "ERROR", alert=True)


class DMF_PT_parts_materials(Panel):
    bl_label = "Material slots"
    bl_idname = "DMF_PT_parts_materials"
    bl_parent_id = "DMF_PT_parts"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.label(
            text=f"{settings.source_material_count} source / {settings.material_count} part",
            icon="MATERIAL",
        )
        layout.prop(settings, "material_source", text="Source")
        ui_popit.glyphs(layout, ["dmf.scan_materials"], labels={"dmf.scan_materials": "Scan slots"})
        if settings.material_source is None:
            _hint(layout, "Set a source object, then scan its slots.", "QUESTION")
            return
        if settings.custom_mesh is None:
            _hint(layout, "Choose an active part before assigning slots.", "QUESTION")
            return
        ui_popit.micro(layout, "Source slots", "IMPORT")
        ui_popit.column_header(
            layout,
            settings.source_materials_name_width,
            ("Material", "Slot"),
            (1.0,),
        )
        layout.template_list(
            "DMF_UL_materials",
            "source_materials",
            settings,
            "source_materials",
            settings,
            "source_material_index",
            rows=3,
        )
        ui_popit.name_width(layout, settings, "source_materials_name_width")
        ui_popit.micro(layout, "Part slots", "MATERIAL")
        ui_popit.column_header(
            layout,
            settings.part_materials_name_width,
            ("Material", "Slot"),
            (1.0,),
        )
        layout.template_list(
            "DMF_UL_materials",
            "part_materials",
            settings,
            "part_materials",
            settings,
            "part_material_index",
            rows=3,
        )
        ui_popit.name_width(layout, settings, "part_materials_name_width")
        actions = layout.column(align=True)
        actions.operator("dmf.assign_material", text="Assign selected material", icon="FORWARD")
        actions.operator("dmf.append_material", text="Append as new slot", icon="ADD")
        actions.operator("dmf.clear_part_material", text="Clear selected slot", icon="REMOVE")


class DMF_PT_cloth(Panel):
    bl_label = "Cloth"
    bl_idname = "DMF_PT_cloth"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        ui_popit.job(layout, settings)
        chains = len(settings.cloth_chains)
        box = ui_popit.page(
            layout,
            settings,
            "Cloth",
            f"{chains} chains" if chains else "not scanned",
            "MOD_CLOTH",
        )
        ui_popit.glyphs(
            box,
            ["dmf.import_hero_parts", "dmf.scan_cloth"],
            labels={"dmf.import_hero_parts": "Import parts", "dmf.scan_cloth": "Scan chains"},
        )
        ui_popit.micro(box, "Chains from", "MOD_CLOTH")
        _chips(box, settings, "cloth_source", (("HERO", "Hero"), ("CUSTOM", "Custom rig")))
        if settings.cloth_source == "CUSTOM":
            if settings.custom_armature is None:
                _hint(box, "Choose your model's rig first.", "QUESTION")
            else:
                box.label(
                    text=f"{settings.custom_armature.name}: {len(settings.custom_armature.data.bones)} bones",
                    icon="ARMATURE_DATA",
                )

        if settings.hero_parts:
            ui_popit.micro(box, "Hero meshes", "MESH_DATA")
            ui_popit.column_header(
                box,
                settings.hero_parts_name_width,
                ("Part", "Type", "Verts"),
                (0.25, 0.2),
            )
            row = box.row(align=True)
            row.template_list(
                "DMF_UL_hero_parts",
                "",
                settings,
                "hero_parts",
                settings,
                "hero_part_index",
                rows=3,
            )
            row.label(text=f"{len(settings.hero_parts)}", icon="OBJECT_DATA")
            ui_popit.name_width(box, settings, "hero_parts_name_width")
        else:
            _hint(box, "Import the hero to bring in hair, jacket and the rest.", "QUESTION")

        built_rows = [row for row in settings.cloth_chains if row.target_mesh is not None]
        if built_rows:
            parts: dict[str, list] = {}
            for row in built_rows:
                parts.setdefault(row.target_mesh.name, []).append(row)
            ui_popit.micro(box, "Cloth parts", "MOD_CLOTH")
            for mesh_name, rows in parts.items():
                chains = ", ".join(row.name for row in rows)
                box.label(text=f"{mesh_name}: {chains}", icon="MESH_DATA")
                pins = ", ".join(f"{row.pin_group} {row.pin_count}" for row in rows)
                box.label(text=f"{rows[0].cloth_modifier} | {pins}", icon="GROUP_VERTEX")
        if settings.cloth_build_skipped:
            _hint(box, settings.cloth_build_skipped, "ERROR")

        if settings.cloth_chains:
            ui_popit.micro(box, "Bone chains", "MOD_CLOTH")
            ui_popit.column_header(
                box,
                settings.cloth_name_width,
                ("Chain", "Type", "Bones"),
                (0.25, 0.2),
            )
            row = box.row(align=True)
            row.template_list(
                "DMF_UL_cloth_chains",
                "",
                settings,
                "cloth_chains",
                settings,
                "cloth_index",
                rows=4,
            )
            ui_popit.name_width(box, settings, "cloth_name_width")
            index = max(0, min(settings.cloth_index, len(settings.cloth_chains) - 1))
            chain = settings.cloth_chains[index]
            box.label(
                text=f"{chain.count} bones, from {chain.root}"
                + (f" ({chain.source.lower()})" if chain.source == "CUSTOM" else ""),
                icon="BONE_DATA",
            )
            if chain.bones:
                _hint(box, chain.bones, "ARMATURE_DATA")
            if chain.source == "CUSTOM":
                edit = box.column(align=True)
                edit.prop(chain, "source_mesh", text="Mesh")
                if settings.target_armature is not None:
                    edit.prop_search(
                        chain,
                        "parent",
                        settings.target_armature.data,
                        "bones",
                        text="New parent",
                    )
                else:
                    edit.prop(chain, "parent", text="New parent")
                if chain.joined:
                    box.label(text=f"{chain.joined} bones joined to the hero", icon="CHECKMARK")
                _hint(
                    box,
                    "Join copies this chain into the hero armature; the vnmskel stays out of the pack.",
                    "INFO",
                )
            actions = ["dmf.build_chain_cloth", "dmf.build_all_cloth"]
            labels = {"dmf.build_chain_cloth": "Build cloth", "dmf.build_all_cloth": "Build all"}
            if chain.source == "CUSTOM":
                actions.insert(0, "dmf.join_cloth_chain")
                labels["dmf.join_cloth_chain"] = "Join to hero"
            ui_popit.glyphs(box, actions, labels=labels)
            proxy = box.row(align=True)
            proxy.operator("dmf.mark_cloth_proxy", text="Mark Source 2 proxy", icon="MOD_PHYSICS")
            if chain.proxy:
                box.label(text="CLOTHPROXY + cloth_enable", icon="CHECKMARK")
            if chain.target_mesh is not None:
                box.label(
                    text=f"{chain.target_mesh.name}: {chain.pin_group}, {chain.cloth_modifier}",
                    icon="CHECKMARK",
                )
            else:
                _hint(
                    box,
                    "Build writes chain vertex groups, a root pin group, and a cloth modifier on the hero mesh.",
                    "INFO",
                )


class DMF_PT_rules(Panel):
    bl_label = "Rules"
    bl_idname = "DMF_PT_rules"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        box = ui_popit.page(
            layout,
            settings,
            "Rules",
            f"{len(settings.bone_rules)}" if settings.bone_rules else "none",
            "DRIVER",
        )
        ui_popit.glyphs(
            box,
            ["dmf.add_rule", "dmf.rule_from_row", "dmf.apply_rules", "dmf.learn_rules"],
            labels={
                "dmf.add_rule": "Add rule",
                "dmf.rule_from_row": "From selection",
                "dmf.apply_rules": "Apply rules",
                "dmf.learn_rules": "Learn rules",
            },
        )

        if not settings.bone_rules:
            _hint(
                box,
                "Add a rule by hand, or write one from the selected bone-map row.",
                "QUESTION",
            )
            return

        # The editor sits above the list: a sidebar that has to be scrolled to
        # reach the fields is how a rule panel becomes a list nobody edits.
        index = max(0, min(settings.bone_rule_index, len(settings.bone_rules) - 1))
        rule = settings.bone_rules[index]
        ui_popit.micro(box, "Rule", "DRIVER")
        edit = box.column(align=True)
        edit.prop(rule, "source", text="Pattern")
        edit.prop(rule, "target", text="Target")
        if "#" in rule.source:
            edit.prop(rule, "delta", text="Number")
        edit.prop(rule, "state", text="Sets row")
        flags = box.row(align=True)
        flags.prop(rule, "regex", text="Regex")
        flags.prop(rule, "side_aware", text="Side")
        flags.prop(rule, "enabled", text="On")
        caught = rules.preview(settings, rule)
        if caught:
            box.label(text=f"{len(caught)} unanswered rows match", icon="CHECKMARK")
        else:
            _hint(box, "No unanswered row matches this pattern yet.", "INFO")
        _hint(box, bonerules.describe(rules.rule_of(rule)), "INFO")

        ui_popit.column_header(
            box,
            settings.rules_name_width,
            ("Rule", "State"),
            (1.0,),
        )
        row = box.row()
        row.template_list(
            "DMF_UL_bone_rules",
            "",
            settings,
            "bone_rules",
            settings,
            "bone_rule_index",
            rows=3,
        )
        buttons = box.row(align=True)
        buttons.enabled = bool(settings.bone_rules)
        remove = buttons.row(align=True)
        remove.alert = True
        remove.operator("dmf.remove_rule", text="Remove", icon="REMOVE")
        buttons.operator("dmf.clear_rules", text="Clear rules", icon="TRASH")
        ui_popit.name_width(box, settings, "rules_name_width")


def _draw_ik(layout, settings) -> None:
    """Source 2 IK targets: list, constrain, bake, then export the clip."""
    count = len(settings.ik_bones)
    box = ui_popit.title(
        layout,
        "Targets",
        (f"{count} target" if count == 1 else f"{count} targets") if count else "not scanned",
        "CONSTRAINT",
    )
    ui_popit.glyphs(
        box,
        ["dmf.scan_ik", "dmf.apply_ik", "dmf.bake_ik", "dmf.clear_ik"],
        labels={
            "dmf.scan_ik": "Find",
            "dmf.apply_ik": "Constrain",
            "dmf.bake_ik": "Bake",
            "dmf.clear_ik": "Clear",
        },
    )
    if settings.ik_bones:
        index = max(0, min(settings.ik_index, len(settings.ik_bones) - 1))
        ui_popit.micro(box, "Targets")
        ui_popit.column_header(
            box,
            settings.ik_name_width,
            ("Target", "Follows"),
            (1.0,),
        )
        box.template_list(
            "DMF_UL_ik",
            "",
            settings,
            "ik_bones",
            settings,
            "ik_index",
            rows=4,
        )
        ui_popit.name_width(box, settings, "ik_name_width")
        box.prop(
            settings.ik_bones[index],
            "target",
            text="Follows",
        )
    message = settings.ik_note or (
        "Constrain follows the real limb; Bake writes visual keys and removes only these constraints."
    )
    ui_popit.bubble(box, message, "INFO")


def _draw_tail(layout, settings) -> None:
    """Pick a tail source, then add its tail to every imported hero clip."""
    options = settings.tail_options
    live = sum(1 for option in options if option.source == "LIVE")
    box = ui_popit.title(
        layout,
        "Tail sources",
        f"{len(options)} sources" if options else "not scanned",
        "ARMATURE_DATA",
    )
    ui_popit.glyphs(
        box,
        ["dmf.scan_tails", "dmf.preview_tail"],
        enabled=not settings.job_running,
        labels={"dmf.scan_tails": "Scan tails", "dmf.preview_tail": "Frame rig"},
    )
    _path_row(box, settings, "tail_scan_dir", "Extra folder")

    if options:
        index = max(0, min(settings.tail_option_index, len(options) - 1))
        selected = options[index]
        chosen = box.box()
        chosen.alert = True
        chosen.label(text=selected.label, icon="BONE_DATA")
        chosen.label(
            text=f"{selected.count} bones · {selected.source.lower()} · {selected.chain}",
            icon="BLANK1",
        )
        chosen.operator("dmf.load_tail_option", text="Use this tail rig", icon="ARMATURE_DATA")

        ui_popit.micro(box, f"Tail sources · {live} live" if live else "Tail sources")
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
        for tile_index, option in enumerate(options):
            tile = grid.box()
            tile.alert = tile_index == settings.tail_option_index
            icon = tailpreview.icon(option.preview)
            if icon:
                tile.template_icon(icon_value=icon, scale=2.2)
            else:
                tile.label(text="", icon="BONE_DATA")
            choice = tile.operator(
                "dmf.load_tail_option",
                text=option.label,
                icon="BONE_DATA",
            )
            choice.index = tile_index
            tile.label(text=f"{option.count} bones · {option.source.lower()}", icon="BLANK1")

    box.prop(settings, "tail_weight", text="Tail influence", slider=True)
    imported = [
        row for row in settings.clips
        if row.action and row.state in ("IMPORTED", "WRITTEN")
    ]
    hero = clipops.hero_source(settings)
    primary = box.row(align=True)
    primary.scale_y = 1.5
    primary.enabled = bool(options) and not settings.job_running and not tailops.auto_running()
    primary.operator(
        "dmf.build_tail_animation",
        text=f"Add tail and compile {len(imported)} clips" if imported else "Add tail and compile all clips",
        icon="ACTION",
    )
    box.prop(settings, "tail_bare_only")
    box.operator(
        "dmf.publish_tail_anims",
        text="Export tail only" if settings.tail_bare_only else "Compile already-tailed clips",
        icon="FILE_REFRESH",
    )
    _hint(
        box,
        "Adds the selected tail to imported clips, writes each DMX, and compiles against the hero skeleton. The vnmskel stays out of the pack.",
        "INFO",
    )
    if not imported:
        _hint(
            box,
            f"The importer adds {hero or 'this hero'}'s clips when you press the action.",
            "QUESTION",
        )

    box.prop(settings, "tail_manual", text="Manual channel map")
    if settings.tail_manual:
        ui_popit.micro(box, "Pair or write one clip")
        box.prop(settings, "tail_armature", text="Tail rig")
        pair = box.row(align=True)
        pair.operator("dmf.scan_tail", text="Pair hero tail bones", icon="LINKED")
        if settings.tail_bones:
            index = max(0, min(settings.tail_index, len(settings.tail_bones) - 1))
            row = settings.tail_bones[index]
            ui_popit.column_header(
                box,
                settings.tail_name_width,
                ("Hero bone", "Tail bone"),
                (1.0,),
            )
            box.template_list(
                "DMF_UL_tail",
                "",
                settings,
                "tail_bones",
                settings,
                "tail_index",
                rows=4,
            )
            ui_popit.name_width(box, settings, "tail_name_width")
            if settings.tail_armature is not None:
                box.prop_search(
                    row,
                    "target",
                    settings.tail_armature.data,
                    "bones",
                    text="Tail bone",
                )
            else:
                box.prop(row, "target", text="Tail bone")
        box.prop(settings, "tail_clip", text="Source clip")
        write = box.column(align=True)
        write.operator("dmf.blend_tail", text="Write selected clip to tail", icon="PLAY")
        write.operator(
            "dmf.blend_tail_all",
            text=f"Write every {hero} clip to tail" if hero else "Write every clip for this hero to tail",
            icon="ACTION",
        )

    message = settings.tail_note or settings.tail_option_note
    if message:
        ui_popit.bubble(box, message, "INFO")


class DMF_PT_animations(Panel):
    bl_label = "Animations"
    bl_idname = "DMF_PT_animations"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        ui_popit.job(layout, settings)
        layout.label(text="Animation tools are incomplete.", icon="INFO")
        imported = sum(1 for row in settings.clips if row.state == "IMPORTED")
        box = ui_popit.page(
            layout,
            settings,
            "Animations",
            f"{imported}/{len(settings.clips)}" if settings.clips else "not scanned",
            "ACTION",
        )
        ui_popit.glyphs(
            box,
            ["dmf.scan_clips", "dmf.import_clips", "dmf.bake_clips", "dmf.cancel_clips"],
            labels={
                "dmf.scan_clips": "Scan",
                "dmf.import_clips": "Import all",
                "dmf.bake_clips": "Bake + write",
                "dmf.cancel_clips": "Stop",
            },
        )
        _path_row(box, settings, "clips_dir", "Folder (optional)")
        ui_popit.stat(
            box,
            "from",
            settings.clip_auto_note or settings.clips_dir or settings.extraction_dir
            or "scan a hero",
            "FILE_FOLDER",
        )
        ui_popit.stat(box, "write to", settings.clip_export_dir or "not set", "EXPORT")
        ui_popit.micro(box, "Graph", "FILTER")
        _chips(box, settings, "clip_ag_filter", (
            ("ALL", "All"), ("AG1", "AG1"), ("AG2", "AG2"), ("UNKNOWN", "Unknown"),
        ))
        if settings.clip_auto_note:
            box.label(text=settings.clip_auto_note, icon="FILE_FOLDER")
        if settings.clip_vnmskel:
            box.label(text=Path(settings.clip_vnmskel).name, icon="ARMATURE_DATA")
        if not settings.clips:
            _hint(
                box,
                "Extract a hero, then scan. Clip folders and the vnmskel are found automatically.",
                "QUESTION",
            )
            return

        ui_popit.column_header(
            box,
            settings.clips_name_width,
            ("Clip", "Graph", "File"),
            (0.2, 0.28),
        )
        row = box.row()
        row.template_list(
            "DMF_UL_clips",
            "",
            settings,
            "clips",
            settings,
            "clip_index",
            rows=6,
        )
        ui_popit.name_width(box, settings, "clips_name_width")
        index = max(0, min(settings.clip_index, len(settings.clips) - 1))
        entry = settings.clips[index]
        detail = box.column(align=True)
        detail.label(text=entry.name, icon="FILE")
        if entry.source_hero:
            detail.label(text=f"from {entry.source_hero}", icon="FILE_FOLDER")
        meta = detail.row(align=True)
        meta.label(text=f"{entry.kind}{'_c' if entry.compiled else ''}")
        meta.label(text=entry.ag)
        right = meta.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=f"{entry.size:,} bytes")
        if entry.action:
            detail.label(text=f"action {entry.action}", icon="ACTION")
        if entry.exported:
            detail.label(text=Path(entry.exported).name, icon="EXPORT")

        ui_popit.glyphs(
            box,
            ["dmf.import_clip", "dmf.preview_clip", "dmf.export_clip", "dmf.bake_clip"],
            labels={
                "dmf.import_clip": "Import",
                "dmf.preview_clip": "Preview",
                "dmf.export_clip": "Write",
                "dmf.bake_clip": "Bake",
            },
        )
        prefix = box.row(align=True)
        prefix.prop(settings, "clip_prefix", text="Prefix")
        prefix.operator("dmf.prefix_clips", text="Apply", icon="SORTALPHA")
        box.operator("dmf.clear_clips", text="Clear imported actions", icon="TRASH")
        if settings.clip_note:
            _hint(box, settings.clip_note, "LOCKED")




class DMF_PT_compare(Panel):
    bl_label = "Compare"
    bl_idname = "DMF_PT_compare"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        box = ui_popit.page(layout, settings, "Compare", "both rigs" if settings.compare_active else "off", "SPLIT_VERTICAL")
        ui_popit.glyphs(
            box,
            ["dmf.compare_split", "dmf.compare_clear"],
            labels={"dmf.compare_split": "Split", "dmf.compare_clear": "Clear"},
        )
        box.prop_search(settings, "compare_action", bpy.data, "actions", text="Action")
        box.operator("dmf.apply_compare_action", text="Apply to both rigs", icon="ACTION")


class DMF_PT_skeleton(Panel):
    bl_label = "Skeleton"
    bl_idname = "DMF_PT_skeleton"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        ui_popit.job(layout, settings)
        mapped = sum(1 for row in settings.bone_map if row.state == "MAPPED")
        top = ui_popit.page(
            layout,
            settings,
            "Skeleton",
            f"{mapped}/{len(settings.bone_map)}" if settings.bone_map else "not scanned",
            "BONE_DATA",
        )
        ui_popit.glyphs(top, ["dmf.scan_bones"], labels={"dmf.scan_bones": "Scan bones"})
        ui_popit.micro(top, "Show", "FILTER")
        _chips(top, settings, "bone_filter", (
            ("ALL", "All"), ("UNMATCHED", "Unmatched"), ("MAPPED", "Mapped"),
            ("EXTRA", "Extra"), ("IGNORED", "Ignored"),
        ))
        if settings.bone_rules:
            _hint(layout, "Scan applies your rules to unmatched names.", "INFO")
        if settings.rule_fill_running:
            filling = layout.row(align=True)
            filling.label(
                text=f"Rules {settings.rule_fill_done}/{settings.rule_fill_total}",
                icon="TIME",
            )
            filling.operator("dmf.stop_rules", text="Stop", icon="CANCEL")

        pose = _section(layout, "Ref pose", "ARMATURE_DATA", settings.pose_stance or "no stance")
        ui_popit.glyphs(
            pose,
            ["dmf.pose_preview", "dmf.pose_clear"],
            labels={"dmf.pose_preview": "Preview pose", "dmf.pose_clear": "Clear"},
        )
        if settings.pose_preview_error:
            _hint(pose, settings.pose_preview_error, "ERROR", alert=True)
        elif not settings.pose_preview:
            _hint(pose, "Previews the hero stance; the rest pose stays unchanged.", "INFO")

        if not settings.bone_map:
            _hint(layout, "No rows yet. Scan the custom rig or add a row.", "QUESTION")
            return
        index = max(0, min(settings.bone_map_index, len(settings.bone_map) - 1))
        entry = settings.bone_map[index]
        edit = ui_popit.title(
            layout,
            entry.source or "row",
            _STATE_LABELS.get(entry.state, entry.state),
            "BONE_DATA",
            alert=entry.state == "UNMATCHED",
        )
        edit.prop(entry, "source", text="Source")
        if settings.target_armature is not None:
            edit.prop_search(entry, "target", settings.target_armature.data, "bones", text="Target")
        else:
            edit.prop(entry, "target", text="Target")
        edit.prop(entry, "state", text="State")
        if entry.note:
            _hint(edit, entry.note, "INFO")
        ui_popit.glyphs(
            edit,
            ["dmf.rename_bones", "dmf.mark_extra", "dmf.ignore_entry", "dmf.clear_target"],
            labels={
                "dmf.rename_bones": "Rename",
                "dmf.mark_extra": "Mark extra",
                "dmf.ignore_entry": "Ignore",
                "dmf.clear_target": "Clear target",
            },
        )
        ui_popit.column_header(
            layout,
            settings.bone_name_width,
            ("Source", "Target", "State"),
            (0.35, 0.25),
        )
        row = layout.row()
        row.template_list(
            "DMF_UL_bone_map",
            "",
            settings,
            "bone_map",
            settings,
            "bone_map_index",
            rows=5,
        )
        buttons = layout.row(align=True)
        buttons.operator("dmf.add_bone_entry", text="Add row", icon="ADD")
        remove = buttons.row(align=True)
        remove.alert = True
        remove.operator("dmf.remove_bone_entry", text="Remove row", icon="REMOVE")
        ui_popit.name_width(layout, settings, "bone_name_width")

        mapped = bool(settings.show_bone_map and settings.target_armature is not None)
        visual = _section(
            layout,
            "Bone map",
            "VIEW3D",
            f"{settings.bone_map_plane.lower()} {len(settings.hierarchy)}" if mapped else "off",
        )
        controls = visual.row(align=True)
        controls.prop(settings, "show_bone_map", text="Show", toggle=True)
        controls.prop(settings, "bone_map_plane", text="Plane")
        controls.prop(settings, "bone_map_labels", text="Labels", icon="FONT_DATA")
        ui_popit.glyphs(
            visual,
            ["dmf.pick_bone_map", "dmf.refresh_hierarchy"],
            labels={"dmf.pick_bone_map": "Pick", "dmf.refresh_hierarchy": "Read"},
        )
        if settings.bone_map_error:
            _hint(visual, f"Map draw failed: {settings.bone_map_error}", "ERROR", alert=True)
        elif settings.hierarchy:
            chosen = settings.hierarchy[max(0, min(settings.hierarchy_index, len(settings.hierarchy) - 1))]
            summary = visual.row(align=True)
            summary.label(text=chosen.name, icon="BONE_DATA")
            right = summary.row(align=True)
            right.alignment = "RIGHT"
            right.label(text=f"{chosen.children} children" if chosen.children else "leaf")
            chain = workbench.bone_chain(settings, chosen.name)
            if chain:
                _hint(visual, " <- ".join(reversed(chain)), "FILE_PARENT")



class DMF_PT_skeleton_bones(Panel):
    bl_label = "Bone list & alignment"
    bl_idname = "DMF_PT_skeleton_bones"
    bl_parent_id = "DMF_PT_skeleton"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        if settings.hierarchy:
            layout.operator("dmf.select_hierarchy_bone", text="Select bone", icon="RESTRICT_SELECT_OFF")
            ui_popit.column_header(
                layout,
                settings.hierarchy_name_width,
                ("Bone", "Parent", "Children"),
                (0.3, 0.4),
            )
            layout.template_list(
                "DMF_UL_hierarchy",
                "hierarchy",
                settings,
                "hierarchy",
                settings,
                "hierarchy_index",
                rows=6,
            )
            ui_popit.name_width(layout, settings, "hierarchy_name_width")
        else:
            layout.operator("dmf.refresh_hierarchy", text="Read bone list", icon="FILE_REFRESH")

        ui_popit.glyphs(
            layout,
            ["dmf.align_bone", "dmf.align_all_bones", "dmf.copy_pose"],
            labels={
                "dmf.align_bone": "Align",
                "dmf.align_all_bones": "Align all",
                "dmf.copy_pose": "Copy pose",
            },
        )
        nudge = layout.column(align=True)
        nudge.prop(settings, "nudge_axis", text="Axis")
        nudge.prop(settings, "nudge_amount", text="Amount")
        nudge.prop(settings, "nudge_rotate", text="Rotate")
        step = layout.row(align=True)
        minus = step.operator("dmf.nudge_bone", text="- Step", icon="REMOVE")
        minus.direction = -1
        plus = step.operator("dmf.nudge_bone", text="+ Step", icon="ADD")
        plus.direction = 1
        _hint(layout, "Alignment changes the bind pose. Rebind weighted meshes.", "INFO")


class DMF_PT_weights(Panel):
    bl_label = "Weights"
    bl_idname = "DMF_PT_weights"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        ui_popit.job(layout, settings)
        ui_popit.page(layout, settings, "Weights", settings.weight_mode.title(), "MOD_VERTEX_WEIGHT")

        layout.prop(settings, "weight_mode", text="Method")
        options = layout.column(align=True)
        options.enabled = not settings.job_running
        options.prop(settings, "max_distance", text="Surface reach")
        options.prop(settings, "max_influences", text="Max influences")
        options.prop(settings, "extra_policy", text="Extra bones")
        _primary(
            layout,
            "dmf.retarget",
            "Solve & bind",
            "MOD_ARMATURE",
            enabled=not settings.job_running and settings.custom_mesh is not None and settings.target_armature is not None,
        )
        if settings.unmatched:
            _hint(layout, "Unmapped: " + settings.unmatched, "STATUS_WARNING", alert=True)

        gate = _proof_gate(settings)
        proof = ui_popit.section(
            layout,
            "Axis proof",
            _CHECK_ICONS.get(gate, "QUESTION"),
            gate,
            alert=gate == "fail",
        )
        if settings.proof_checks:
            for check in settings.proof_checks:
                row = proof.row(align=True)
                row.alert = check.token in ("fail", "stale", "refused")
                row.label(text=f"{check.name}", icon=_CHECK_ICONS.get(check.token, "QUESTION"))
                right = row.row(align=True)
                right.alignment = "RIGHT"
                right.label(text=check.token)
        else:
            _hint(proof, "No proof minted yet.", "QUESTION")
        if settings.proof_digest:
            ui_popit.stat(proof, "BLAKE3", settings.proof_digest, "LOCKED")
        ui_popit.glyphs(
            proof,
            ["dmf.mint_proof", "dmf.verify_proof"],
            labels={"dmf.mint_proof": "Mint", "dmf.verify_proof": "Verify"},
        )


class DMF_PT_weights_manual(Panel):
    bl_label = "Solver detail & weight tools"
    bl_idname = "DMF_PT_weights_manual"
    bl_parent_id = "DMF_PT_weights"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        options = layout.column(align=True)
        options.enabled = not settings.job_running
        options.prop(settings, "falloff", text="Falloff")
        options.prop(settings, "surface_samples", text="Surface samples")
        if settings.target_armature is not None:
            options.prop_search(settings, "fallback_bone", settings.target_armature.data, "bones", text="Fold fallback")
        else:
            options.prop(settings, "fallback_bone", text="Fold fallback")
        options.prop(settings, "protected_groups", text="Protect groups")
        options.prop(settings, "clear_existing", text="Clear old groups")

        layout.separator()
        ui_popit.micro(layout, "Weight tools", "BRUSH_DATA")
        manual = layout.column(align=True)
        manual.prop(settings, "manual_weight", text="Assign weight")
        ui_popit.glyphs(
            manual,
            [
                "dmf.select_unweighted",
                "dmf.assign_active_bone",
                "dmf.smooth_active_group",
                "dmf.mirror_weights",
                "dmf.normalize_weights",
                "dmf.limit_influences",
                "dmf.remove_zero_weights",
            ],
            labels={
                "dmf.select_unweighted": "Unweighted",
                "dmf.assign_active_bone": "Assign",
                "dmf.smooth_active_group": "Smooth",
                "dmf.mirror_weights": "Mirror",
                "dmf.normalize_weights": "Normalize",
                "dmf.limit_influences": "Limit",
                "dmf.remove_zero_weights": "Clear zero",
            },
        )

        layout.separator()
        layout.prop(settings, "proof_presenter", text="Presenter")
        layout.prop(settings, "proof_ticket", text="Ticket")
        if settings.proof_claim:
            _hint(layout, settings.proof_claim, "FILE")
        if settings.proof_tick:
            layout.label(text=f"Tick {settings.proof_tick}", icon="TIME")


class DMF_PT_handoff(Panel):
    bl_label = "Release"
    bl_idname = "DMF_PT_handoff"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = set()

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        ui_popit.job(layout, settings)
        root = core.csdk_addon_root(settings)
        folder = core.csdk_addon_folder(settings)
        staged = folder is not None and (folder / "stage.json").is_file()
        compiled = False
        if root is not None and folder is not None and settings.vmdl_relative.strip():
            compiled = (
                root
                / "game"
                / "citadel_addons"
                / settings.addon_name
                / Path(settings.vmdl_relative).with_suffix(".vmdl_c")
            ).is_file()

        state = "compiled" if compiled else "staged" if staged else "not staged"
        icon = "CHECKMARK" if compiled else "PACKAGE" if staged else "QUESTION"
        addon = ui_popit.page(layout, settings, "Release", state, icon)
        addon.prop(settings, "addon_name", text="Name")
        if folder is not None:
            addon.label(text=str(folder), icon="FILE_FOLDER")
        else:
            _hint(addon, "No addon folder: set CSDK13 in Setup and a name.", "QUESTION")
        if settings.body_dmx and not settings.vmdl:
            _hint(addon, "No S2V vmdl set; choose it under Files.", "STATUS_WARNING", alert=True)

        built = [row for row in settings.lod_levels if row.object is not None]
        if built:
            stale = settings.lod_tick != settings.axis_tick
            line = addon.row(align=True)
            line.label(text=f"{len(built)} LOD meshes", icon="MOD_DECIM")
            right = line.row(align=True)
            right.alignment = "RIGHT"
            right.label(text="rebuild" if stale else "current")

        addon.enabled = not settings.job_running
        actions = addon.row(align=True)
        actions.operator("dmf.build_lods", text="Build LODs", icon="MOD_DECIM")
        actions.operator("dmf.export_stage", text="Export & stage", icon="EXPORT")
        _primary(addon, "dmf.compile", "Compile", "PLAY", enabled=not settings.job_running)
        _hint(
            addon,
            "This is the only compile button. Release packs what it produces.",
            "INFO",
        )


class DMF_PT_handoff_paths(Panel):
    bl_label = "Content paths & LOD build"
    bl_idname = "DMF_PT_handoff_paths"
    bl_parent_id = "DMF_PT_handoff"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        _path_row(layout, settings, "stage_dir", "Install root")
        layout.prop(settings, "vmdl_relative", text="vmdl")
        layout.prop(settings, "target_dmx_relative", text="DMX")

        lod = _section(layout, "LOD build", "MOD_DECIM", f"{len(settings.lod_levels)}")
        lod.prop(settings, "live_lods", text="Use built LODs")
        lod.prop(settings, "generate_lods", text="Replace LOD slots")
        options = lod.column(align=True)
        options.enabled = settings.generate_lods
        options.prop(settings, "lod_count", text="Count (0 = hero)")
        options.prop(settings, "lod_decimate", text="Decimate %")
        ui_popit.glyphs(
            lod,
            ["dmf.build_lods", "dmf.clear_lods"],
            labels={"dmf.build_lods": "Build", "dmf.clear_lods": "Clear"},
        )
        for row in [row for row in settings.lod_levels if row.object is not None]:
            line = lod.row(align=True)
            line.label(text=f"L{row.level}", icon="MESH_DATA")
            right = line.row(align=True)
            right.alignment = "RIGHT"
            right.label(text=f"{row.vertices:,}v")
        if settings.lod_levels and settings.lod_tick != settings.axis_tick:
            _hint(lod, "Weights or fit changed; rebuild so the LODs match.", "STATUS_WARNING", alert=True)


class DMF_PT_release(Panel):
    bl_label = "Pack & install"
    bl_idname = "DMF_PT_release"
    bl_parent_id = "DMF_PT_handoff"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        pak = Path(bpy.path.abspath(settings.release_pak)) if settings.release_pak else None
        packed = pak is not None and pak.is_file()
        chain = _section(
            layout,
            "Build chain",
            "PLAY",
            "pak ready" if packed else "no pak",
        )
        buttons = chain.column(align=True)
        buttons.operator("dmf.write_model", icon="ARMATURE_DATA", text="Write model from armature")
        buttons.operator("dmf.pack_vpk", icon="PACKAGE", text="Pack VPK")
        buttons.operator("dmf.install_pak", icon="IMPORT", text="Install into addon slot")
        buttons.operator("dmf.launch_game", icon="PLAY", text="Launch game")

        if settings.release_note:
            ui_popit.bubble(layout, settings.release_note, "CHECKMARK")


def _draw_write(layout, settings) -> None:
    """Write the imported clips back as Model 22 DMX, and say where they go."""
    ui_popit.stat(layout, "clips", f"{len(settings.clips)} found", "ACTION")
    _path_row(layout, settings, "clip_export_dir", "Folder")
    write = layout.row(align=True)
    write.operator("dmf.export_clips", text="Write all", icon="EXPORT")
    write.operator("dmf.cancel_clips", text="Stop", icon="CANCEL")
    written = sum(1 for row in settings.clips if row.state == "WRITTEN")
    if written:
        layout.label(text=f"{written} clips written", icon="CHECKMARK")
    _hint(
        layout,
        "Writes Model 22 DMX clips with visual keys and the original frame range. Pack the clip, not the vnmskel.",
        "INFO",
    )


class DMF_PT_animation_ik(Panel):
    bl_label = "IK"
    bl_idname = "DMF_PT_animation_ik"
    bl_parent_id = "DMF_PT_animations"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        _draw_ik(self.layout, context.scene.dmf)


class DMF_PT_animation_tail(Panel):
    bl_label = "Tail"
    bl_idname = "DMF_PT_animation_tail"
    bl_parent_id = "DMF_PT_animations"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        _draw_tail(self.layout, context.scene.dmf)


class DMF_PT_animation_write(Panel):
    bl_label = "Write back"
    bl_idname = "DMF_PT_animation_write"
    bl_parent_id = "DMF_PT_animations"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        _draw_write(layout, settings)


class DMF_PT_release_slot(Panel):
    bl_label = "Addon slot"
    bl_idname = "DMF_PT_release_slot"
    bl_parent_id = "DMF_PT_release"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        slot_box = ui_popit.section(layout, "Addon slot", "FILEBROWSER")
        slot_box.prop(settings, "release_slot_number")
        slot_box.prop(settings, "release_pak")
        try:
            from . import release

            env = core.env(settings)
            if env.game_dir is not None:
                ui_popit.stat(slot_box, "game", str(env.game_dir), "DISK_DRIVE")
            slot = release.slot(settings)
            ceiling, mounted = release.slot_ceiling(settings, slot.parent)
            ui_popit.stat(slot_box, "writes", slot.name, "FILEBROWSER")
            ui_popit.stat(slot_box, "pak numbers", f"1..{ceiling}, citadel mounts {mounted}", "INFO")
        except Exception as error:
            slot_box.label(text=str(error), icon="ERROR")


CLASSES = (
    DMF_PT_main,
    DMF_PT_setup,
    DMF_PT_source,
    DMF_PT_source_files,
    DMF_PT_parts,
    DMF_PT_parts_materials,
    DMF_PT_cloth,
    DMF_PT_skeleton,
    DMF_PT_skeleton_bones,
    DMF_PT_rules,
    DMF_PT_animations,
    DMF_PT_animation_ik,
    DMF_PT_animation_tail,
    DMF_PT_animation_write,
    DMF_PT_compare,
    DMF_PT_weights,
    DMF_PT_weights_manual,
    DMF_PT_handoff,
    DMF_PT_handoff_paths,
    DMF_PT_release,
    DMF_PT_release_slot,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
