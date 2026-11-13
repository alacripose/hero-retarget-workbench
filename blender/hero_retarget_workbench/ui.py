"""Native Blender sidebar for the hero retarget workbench.

The surface follows the Popit model the owner's references define: a page opens
with one card naming what it edits, its actions are glyphs, the deeper controls
fold away, and a page is allowed a single message. Blender's own dark theme
supplies colour; the panel only decides what is worth showing.

The surface is Operate: native widgets, dense information, no wizard. The panel
does not claim a result. It shows the live stage, the bone map, the proof checks
and the exact refusal that blocks the handoff.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import bpy
from bpy.types import Panel
from forge import bonerules, paths, stageflow

from . import core, rules, ui_popit, workbench


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


def _short(value: str, limit: int = 34) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _tail(value: str, limit: int = 46) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return "..." + text[-(limit - 3) :]


def _hero_label(settings) -> str:
    slug = settings.hero_slug
    if slug in ("", "NONE"):
        return "no hero"
    return slug.replace("_", " ").title()


def _hero_state(settings) -> str:
    if not settings.build:
        return "not detected"
    if settings.hero_slug in ("", "NONE"):
        return "choose a hero"
    if not settings.body_dmx:
        return "extract"
    if settings.target_body is None or settings.target_armature is None:
        return "import needed"
    return "imported"


def _mesh_state(settings) -> str:
    mesh = settings.custom_mesh
    if mesh is None:
        return "not set"
    return _short(mesh.name, 24)


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
        "import": armature is not None and settings.target_body is not None,
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
    row.label(text=_short(step.label, 32), icon=step.icon)
    right = row.row(align=True)
    right.alignment = "RIGHT"
    right.label(text=f"{answered}/{total}")
    if step.detail:
        row = layout.row(align=True)
        row.scale_y = 0.8
        row.alignment = "RIGHT"
        row.label(text=step.detail)


def _section(layout, title: str, icon: str, detail: str = ""):
    box = layout.box()
    header = box.row(align=True)
    header.scale_y = 0.9
    header.label(text=title.upper(), icon=icon)
    if detail:
        right = header.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=_short(detail, 26))
    return box


def _hint(layout, text: str, icon: str = "INFO", alert: bool = False, width: int = 36) -> None:
    """Reserved for a refusal or a state that blocks work; ordinary help lives in tooltips."""
    lines = textwrap.wrap(" ".join((text or "").split()), width=width, break_on_hyphens=False) or [""]
    for index, line in enumerate(lines[:2]):
        row = layout.row(align=True)
        row.alert = alert
        row.label(text=line, icon=icon if index == 0 else "BLANK1")


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


def _job(layout, settings) -> None:
    if not settings.job_running:
        return
    box = _section(layout, settings.job_label or "Working", "TIME", settings.job_kind.title())
    box.prop(settings, "job_progress", text=settings.job_message, slider=True)
    if settings.job_cancellable:
        box.operator("dmf.cancel_weight_job", text="Cancel after this chunk", icon="CANCEL")


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
            _short(settings.build, 20) or "no build",
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
            max_lines=4 if settings.status_kind == "ERROR" else 3,
        )
        _job(layout, settings)


class DMF_PT_setup(Panel):
    bl_label = "Setup"
    bl_idname = "DMF_PT_setup"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout

        live = _section(layout, "Live game", "WORLD", _short(settings.build, 24) or "not detected")
        live.prop(settings, "deadlock_root", text="Install")
        live.prop(settings, "s2v_cli", text="S2V CLI")
        gui_note = paths.s2v_gui_note(settings.s2v_cli)
        if gui_note:
            _hint(live, gui_note, "ERROR", alert=True, width=30)
        ui_popit.glyphs(live, ["dmf.detect_paths"], labels={"dmf.detect_paths": "Detect"})

        csdk = _section(layout, "CSDK13", "PACKAGE", "compiler")
        csdk.prop(settings, "csdk_root", text="Install")
        folder = core.csdk_addon_folder(settings)
        if folder is not None:
            csdk.label(text=_tail(str(folder), 46), icon="FILE_FOLDER")
        else:
            _hint(csdk, "Set the CSDK13 folder that holds resourcecompiler.exe.", "QUESTION", width=30)

        workspace = _section(layout, "Workspace", "FILE_FOLDER", "optional")
        workspace.prop(settings, "project_root", text="Folder")


class DMF_PT_source(Panel):
    bl_label = "Source"
    bl_idname = "DMF_PT_source"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        hero = ui_popit.title(layout, "Hero", _hero_state(settings), "WORLD")
        hero.prop(settings, "hero_slug", text="")
        ui_popit.glyphs(
            hero,
            ["dmf.detect", "dmf.extract", "dmf.import_hero"],
            enabled=not settings.job_running,
        )
        hero.prop(settings, "target_armature", text="Skeleton")
        hero.prop(settings, "target_body", text="Body")

        custom = ui_popit.title(layout, "Your model", _mesh_state(settings), "MESH_DATA")
        ui_popit.glyphs(
            custom,
            ["dmf.import_custom"],
            enabled=not settings.job_running,
            labels={"dmf.import_custom": "Import"},
        )
        custom.prop(settings, "custom_mesh", text="Mesh")
        custom.prop(settings, "custom_armature", text="Rig")
        name_row = custom.row(align=True)
        name_row.prop(settings, "custom_name", text="Name")
        name_row.operator("dmf.apply_model_name", text="", icon="SORTALPHA")
        fit = custom.row(align=True)
        fit.prop(settings, "axis_preset", text="")
        fit.prop(settings, "fit_scale", text="")
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
        _path_row(layout, settings, "body_dmx", "Body DMX")
        _path_row(layout, settings, "vmdl", "Hero vmdl")
        layout.operator("dmf.pick_vmdl", text="Choose S2V vmdl", icon="FILEBROWSER")
        _path_row(layout, settings, "materials_dir", "Hero materials")
        _path_row(layout, settings, "custom_model", "Model file")
        _path_row(layout, settings, "custom_materials_dir", "Model materials")
        _hint(
            layout,
            "Materials are content roots; their relative paths are preserved. Blank uses the extraction.",
            "MATERIAL",
            width=30,
        )


class DMF_PT_update(Panel):
    bl_label = "Update old addon"
    bl_idname = "DMF_PT_update"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        box = ui_popit.title(layout, "Old addon", settings.update_addon_name or "not set", "FILE_REFRESH")
        _path_row(box, settings, "old_vpk", "VPK / folder")
        box.operator("dmf.pick_old_vpk", text="Choose old addon", icon="FILEBROWSER")
        options = box.column(align=True)
        options.prop(settings, "update_model_policy", text="Old model")
        options.prop(settings, "update_preserve_cloth", text="Keep cloth/physics")
        options.prop(settings, "update_preserve_materials", text="Keep old materials")
        options.prop(settings, "update_addon_name", text="Updated addon")
        _primary(
            box,
            "dmf.update_old_addon",
            "Import & update",
            "FILE_REFRESH",
            enabled=not settings.job_running and settings.hero_slug not in ("", "NONE"),
        )

        advanced = _section(layout, "Advanced", "OPTIONS")
        _path_row(advanced, settings, "update_old_vmdl", "Old vmdl")
        advanced.operator("dmf.pick_old_vmdl", text="Choose old vmdl", icon="FILEBROWSER")
        _path_row(advanced, settings, "update_output", "Output stage")
        advanced.prop(settings, "update_replace_output", text="Replace output folder")


class DMF_PT_parts(Panel):
    bl_label = "Parts & Materials"
    bl_idname = "DMF_PT_parts"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        collection_box = ui_popit.title(
            layout,
            "Parts",
            f"{len(settings.parts)}" if settings.parts else "not scanned",
            "GROUP",
        )
        collection_box.prop(settings, "custom_collection", text="")
        ui_popit.glyphs(collection_box, ["dmf.scan_parts"], labels={"dmf.scan_parts": "Scan"})
        if not settings.parts:
            _hint(collection_box, "Choose a collection and scan it.", "QUESTION", width=28)
        else:
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
            index = max(0, min(settings.part_index, len(settings.parts) - 1))
            part = settings.parts[index].object
            if part is not None:
                collection_box.operator("dmf.use_part", text=f"Use part: {_short(part.name, 26)}", icon="OBJECT_DATA")
            else:
                _hint(collection_box, "Selected object is gone. Scan again.", "ERROR", alert=True, width=28)


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
            _hint(layout, "Set a source object, usually the hero body, then scan its slots.", "QUESTION", width=30)
            return
        if settings.custom_mesh is None:
            _hint(layout, "Choose an active part before assigning slots.", "QUESTION", width=30)
            return
        ui_popit.micro(layout, "Source slots", "IMPORT")
        layout.template_list(
            "DMF_UL_materials",
            "source_materials",
            settings,
            "source_materials",
            settings,
            "source_material_index",
            rows=3,
        )
        ui_popit.micro(layout, "Part slots", "MATERIAL")
        layout.template_list(
            "DMF_UL_materials",
            "part_materials",
            settings,
            "part_materials",
            settings,
            "part_material_index",
            rows=3,
        )
        actions = layout.column(align=True)
        actions.operator("dmf.assign_material", text="Assign selected material", icon="FORWARD")
        actions.operator("dmf.append_material", text="Append as new slot", icon="ADD")
        actions.operator("dmf.clear_part_material", text="Clear selected slot", icon="REMOVE")


class DMF_PT_rules(Panel):
    bl_label = "Mapping rules"
    bl_idname = "DMF_PT_rules"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        box = ui_popit.title(
            layout,
            "Rules",
            f"{len(settings.bone_rules)}" if settings.bone_rules else "none",
            "DRIVER",
        )
        ui_popit.glyphs(
            box,
            ["dmf.add_rule", "dmf.rule_from_row", "dmf.apply_rules", "dmf.learn_rules"],
            labels={
                "dmf.add_rule": "Add",
                "dmf.rule_from_row": "From row",
                "dmf.apply_rules": "Apply",
                "dmf.learn_rules": "Learn",
            },
        )

        if not settings.bone_rules:
            _hint(
                box,
                "Add a rule by hand, or write one from the selected bone-map row.",
                "QUESTION",
                width=30,
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
        edit.prop(rule, "state", text="Sets row")
        flags = box.row(align=True)
        flags.prop(rule, "regex", text="Regex")
        flags.prop(rule, "side_aware", text="Side")
        flags.prop(rule, "enabled", text="On")
        caught = rules.preview(settings, rule)
        if caught:
            box.label(text=f"{len(caught)} unanswered rows match", icon="CHECKMARK")
        else:
            _hint(box, "No unanswered row matches this pattern yet.", "INFO", width=30)
        _hint(box, bonerules.describe(rules.rule_of(rule)), "INFO", width=32)

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
        side = row.column(align=True)
        side.operator("dmf.remove_rule", text="", icon="REMOVE")
        side.operator("dmf.clear_rules", text="", icon="TRASH")


class DMF_PT_animations(Panel):
    bl_label = "Animations"
    bl_idname = "DMF_PT_animations"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        imported = sum(1 for row in settings.clips if row.state == "IMPORTED")
        box = ui_popit.title(
            layout,
            "Clips",
            f"{imported}/{len(settings.clips)}" if settings.clips else "not scanned",
            "ACTION",
        )
        ui_popit.glyphs(
            box,
            ["dmf.scan_clips", "dmf.import_clips", "dmf.cancel_clips"],
            labels={"dmf.scan_clips": "Scan", "dmf.import_clips": "Import all", "dmf.cancel_clips": "Stop"},
        )
        _path_row(box, settings, "clips_dir", "Folder")
        if not settings.clips:
            _hint(
                box,
                "Point at the S2V extraction's clip folder, then scan it.",
                "QUESTION",
                width=30,
            )
            return

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
        index = max(0, min(settings.clip_index, len(settings.clips) - 1))
        entry = settings.clips[index]
        detail = box.column(align=True)
        detail.label(text=_short(entry.name, 32), icon="FILE")
        meta = detail.row(align=True)
        meta.label(text=f"{entry.kind}{'_c' if entry.compiled else ''}")
        right = meta.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=f"{entry.size:,} bytes")
        if entry.action:
            detail.label(text=f"action {_short(entry.action, 28)}", icon="ACTION")
        if entry.exported:
            detail.label(text=_short(Path(entry.exported).name, 30), icon="EXPORT")

        actions = box.row(align=True)
        actions.operator("dmf.import_clip", text="Import", icon="IMPORT")
        actions.operator("dmf.preview_clip", text="Preview", icon="PLAY")
        actions.operator("dmf.export_clip", text="Write", icon="EXPORT")
        prefix = box.row(align=True)
        prefix.prop(settings, "clip_prefix", text="Prefix")
        prefix.operator("dmf.prefix_clips", text="", icon="SORTALPHA")
        box.operator("dmf.clear_clips", text="Clear imported actions", icon="TRASH")
        if settings.clip_note:
            _hint(box, settings.clip_note, "LOCKED", width=30)

        ui_popit.micro(box, "Write back", "EXPORT")
        _path_row(box, settings, "clip_export_dir", "Folder")
        write = box.row(align=True)
        write.operator("dmf.export_clips", text="Write all", icon="EXPORT")
        write.operator("dmf.cancel_clips", text="Stop", icon="CANCEL")
        written = sum(1 for row in settings.clips if row.state == "WRITTEN")
        if written:
            box.label(text=f"{written} clips written", icon="CHECKMARK")
        _hint(
            box,
            "Writes <folder>/anims/<clip>.dmx. The extraction's own clips are never overwritten, "
            "and the vnmclip beside each clip is left as it is.",
            "INFO",
            width=34,
        )


class DMF_PT_compare(Panel):
    bl_label = "Compare"
    bl_idname = "DMF_PT_compare"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        box = ui_popit.title(layout, "Split view", "both rigs" if settings.compare_active else "off", "SPLIT_VERTICAL")
        ui_popit.glyphs(
            box,
            ["dmf.compare_split", "dmf.compare_clear"],
            labels={"dmf.compare_split": "Split", "dmf.compare_clear": "Clear"},
        )
        box.prop(settings, "compare_action", text="Action")
        box.operator("dmf.apply_compare_action", text="Apply to both rigs", icon="ACTION")


class DMF_PT_skeleton(Panel):
    bl_label = "Skeleton"
    bl_idname = "DMF_PT_skeleton"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        top = layout.row(align=True)
        top.operator("dmf.scan_bones", text="Scan bone map", icon="FILE_REFRESH")
        top.prop(settings, "bone_filter", text="")
        if settings.bone_rules:
            _hint(
                layout,
                "Scan matches names, then applies your rules; rows you set yourself stay as they are.",
                "INFO",
                width=34,
            )

        pose = _section(layout, "Ref pose", "ARMATURE_DATA", settings.pose_stance or "not read")
        controls = pose.row(align=True)
        controls.prop(settings, "pose_preview", text="Show", toggle=True)
        controls.operator("dmf.pose_preview", text="", icon="PLAY")
        controls.operator("dmf.pose_clear", text="", icon="LOOP_BACK")
        if settings.pose_preview_error:
            _hint(pose, settings.pose_preview_error, "ERROR", alert=True, width=30)
        elif not settings.pose_preview:
            _hint(pose, "Poses the custom rig in the hero's stance; the rest pose is not edited.", "INFO", width=30)

        if not settings.bone_map:
            _hint(layout, "No rows yet. Scan the custom rig or add a row.", "QUESTION", width=30)
            return
        index = max(0, min(settings.bone_map_index, len(settings.bone_map) - 1))
        entry = settings.bone_map[index]
        edit = ui_popit.title(
            layout,
            _short(entry.source, 22) or "row",
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
            _hint(edit, entry.note, "INFO", width=30)
        glyph = edit.row(align=True)
        glyph.operator("dmf.rename_bones", text="", icon="SORTALPHA")
        glyph.operator("dmf.mark_extra", text="", icon="BONE_DATA")
        glyph.operator("dmf.ignore_entry", text="", icon="HIDE_ON")
        glyph.operator("dmf.clear_target", text="", icon="X")
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
        side = row.column(align=True)
        side.operator("dmf.add_bone_entry", text="", icon="ADD")
        side.operator("dmf.remove_bone_entry", text="", icon="REMOVE")

        mapped = bool(settings.show_bone_map and settings.target_armature is not None)
        visual = _section(
            layout,
            "Bone map",
            "VIEW3D",
            f"{settings.bone_map_plane.lower()} {len(settings.hierarchy)}" if mapped else "off",
        )
        controls = visual.row(align=True)
        controls.prop(settings, "show_bone_map", text="Show", toggle=True)
        controls.prop(settings, "bone_map_plane", text="")
        controls.prop(settings, "bone_map_labels", text="", icon="FONT_DATA")
        ui_popit.glyphs(
            visual,
            ["dmf.pick_bone_map", "dmf.refresh_hierarchy"],
            labels={"dmf.pick_bone_map": "Pick", "dmf.refresh_hierarchy": "Read"},
        )
        if settings.bone_map_error:
            _hint(visual, f"Map draw failed: {settings.bone_map_error}", "ERROR", alert=True, width=30)
        elif settings.hierarchy:
            chosen = settings.hierarchy[max(0, min(settings.hierarchy_index, len(settings.hierarchy) - 1))]
            summary = visual.row(align=True)
            summary.label(text=_short(chosen.name, 22), icon="BONE_DATA")
            right = summary.row(align=True)
            right.alignment = "RIGHT"
            right.label(text=f"{chosen.children} children" if chosen.children else "leaf")
            chain = workbench.bone_chain(settings, chosen.name)
            if chain:
                _hint(visual, " <- ".join(reversed(chain)), "FILE_PARENT", width=40)



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
            layout.template_list(
                "DMF_UL_hierarchy",
                "hierarchy",
                settings,
                "hierarchy",
                settings,
                "hierarchy_index",
                rows=6,
            )
        else:
            layout.operator("dmf.refresh_hierarchy", text="Read bone list", icon="FILE_REFRESH")

        align = layout.row(align=True)
        align.operator("dmf.align_bone", text="", icon="SNAP_ON")
        align.operator("dmf.align_all_bones", text="", icon="ARROW_LEFTRIGHT")
        align.operator("dmf.copy_pose", text="", icon="COPYDOWN")
        nudge = layout.row(align=True)
        nudge.prop(settings, "nudge_axis", text="")
        nudge.prop(settings, "nudge_amount", text="")
        nudge.prop(settings, "nudge_rotate", text="Rotate")
        minus = nudge.operator("dmf.nudge_bone", text="", icon="REMOVE")
        minus.direction = -1
        plus = nudge.operator("dmf.nudge_bone", text="", icon="ADD")
        plus.direction = 1
        _hint(layout, "Rest alignment changes the bind pose; rebind if the mesh is already weighted.", "INFO", width=30)


class DMF_PT_weights(Panel):
    bl_label = "Weights & Proof"
    bl_idname = "DMF_PT_weights"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        _hint(layout, "Solver maps your groups, samples the hero surface, uses envelopes outside it. No DATA_TRANSFER.", "MOD_VERTEX_WEIGHT")

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
            _hint(layout, "Unmapped: " + _short(settings.unmatched, 44), "STATUS_WARNING", alert=True, width=30)

        gate = _proof_gate(settings)
        proof = ui_popit.title(layout, "Axis proof", gate, _CHECK_ICONS.get(gate, "QUESTION"), alert=gate == "fail")
        if settings.proof_checks:
            for check in settings.proof_checks:
                row = proof.row(align=True)
                row.alert = check.token in ("fail", "stale", "refused")
                row.label(text=f"{check.name}", icon=_CHECK_ICONS.get(check.token, "QUESTION"))
                right = row.row(align=True)
                right.alignment = "RIGHT"
                right.label(text=check.token)
        else:
            _hint(proof, "No proof minted yet.", "QUESTION", width=28)
        if settings.proof_digest:
            proof.label(text="BLAKE3 " + _short(settings.proof_digest, 20), icon="LOCKED")
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
        row = manual.row(align=True)
        row.operator("dmf.select_unweighted", text="", icon="RESTRICT_SELECT_OFF")
        row.operator("dmf.assign_active_bone", text="", icon="BRUSH_DATA")
        row.operator("dmf.smooth_active_group", text="", icon="MOD_SMOOTH")
        row.operator("dmf.mirror_weights", text="", icon="ARROW_LEFTRIGHT")
        row = manual.row(align=True)
        row.operator("dmf.normalize_weights", text="", icon="NORMALIZE_FCURVES")
        row.operator("dmf.limit_influences", text="", icon="FULLSCREEN_ENTER")
        row.operator("dmf.remove_zero_weights", text="", icon="TRASH")

        layout.separator()
        layout.prop(settings, "proof_presenter", text="Presenter")
        layout.prop(settings, "proof_ticket", text="Ticket")
        if settings.proof_claim:
            _hint(layout, settings.proof_claim, "FILE", width=30)
        if settings.proof_tick:
            layout.label(text=f"Tick {settings.proof_tick}", icon="TIME")


class DMF_PT_handoff(Panel):
    bl_label = "CSDK Addon"
    bl_idname = "DMF_PT_handoff"
    bl_parent_id = "DMF_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Deadlock"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
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
        addon = ui_popit.title(layout, settings.addon_name or "addon", state, icon)
        addon.prop(settings, "addon_name", text="Name")
        if folder is not None:
            addon.label(text=_tail(str(folder), 44), icon="FILE_FOLDER")
        else:
            _hint(addon, "No addon folder: set CSDK13 in Setup and a name.", "QUESTION", width=30)
        if settings.body_dmx and not settings.vmdl:
            _hint(addon, "No S2V vmdl set; choose it under Files.", "STATUS_WARNING", alert=True, width=30)

        built = [row for row in settings.lod_levels if row.object is not None]
        if built:
            stale = settings.lod_tick != settings.axis_tick
            line = addon.row(align=True)
            line.label(text=f"{len(built)} LOD meshes", icon="MOD_DECIM")
            right = line.row(align=True)
            right.alignment = "RIGHT"
            right.label(text="rebuild" if stale else "current")

        glyph = addon.row(align=True)
        glyph.operator("dmf.build_lods", text="", icon="MOD_DECIM")
        glyph.operator("dmf.export_stage", text="Export & stage", icon="EXPORT")
        glyph.operator("dmf.compile", text="Compile", icon="PLAY")
        addon.enabled = not settings.job_running


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
            _hint(lod, "Weights or fit changed; rebuild so the LODs match.", "STATUS_WARNING", alert=True, width=30)


CLASSES = (
    DMF_PT_main,
    DMF_PT_setup,
    DMF_PT_source,
    DMF_PT_source_files,
    DMF_PT_parts,
    DMF_PT_parts_materials,
    DMF_PT_skeleton,
    DMF_PT_skeleton_bones,
    DMF_PT_rules,
    DMF_PT_animations,
    DMF_PT_compare,
    DMF_PT_weights,
    DMF_PT_weights_manual,
    DMF_PT_handoff,
    DMF_PT_handoff_paths,
    DMF_PT_update,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
