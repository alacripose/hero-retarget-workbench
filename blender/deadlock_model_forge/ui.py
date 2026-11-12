"""Native Blender sidebar for the forge workbench.

The surface is Operate: native widgets, dense information, no wizard. The panel
does not claim a result. It shows the live stage, the bone map, the proof checks
and the exact refusal that blocks the handoff.
"""
from __future__ import annotations

import textwrap

import bpy
from bpy.types import Panel


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


def _section(layout, title: str, icon: str, detail: str = ""):
    box = layout.box()
    header = box.row(align=True)
    header.label(text=title, icon=icon)
    if detail:
        right = header.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=_short(detail, 26))
    return box


def _wrapped(layout, text: str, icon: str = "INFO", alert: bool = False, width: int = 36) -> None:
    lines = textwrap.wrap(text, width=width, break_on_hyphens=False) or [""]
    for index, line in enumerate(lines):
        row = layout.row(align=True)
        row.alert = alert
        row.label(text=line, icon=icon if index == 0 else "BLANK1")


def _hint(layout, text: str, icon: str = "INFO", alert: bool = False) -> None:
    _wrapped(layout, text, icon, alert=alert)


def _path_row(layout, settings, prop: str, label: str, button: str = "", icon: str = "FILEBROWSER") -> None:
    row = layout.row(align=True)
    row.prop(settings, prop, text=label)
    if button:
        row.operator(button, text="", icon=icon)


def _primary(layout, operator: str, text: str, icon: str, enabled: bool = True) -> None:
    row = layout.row(align=True)
    row.scale_y = 1.2
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
    bl_label = "Deadlock Model Forge"
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

        header = layout.box()
        header.label(text="Live hero to compiler handoff", icon="OUTLINER_OB_ARMATURE")
        meta = header.row(align=True)
        meta.label(text=_short(settings.build, 24) or "build not detected", icon="INFO")
        live = meta.row(align=True)
        live.alignment = "RIGHT"
        live.label(text=_hero_label(settings), icon="WORLD")
        header.separator()
        _wrapped(
            header,
            settings.status,
            _STATUS_ICONS.get(settings.status_kind, "STATUS_INFO"),
            alert=settings.status_kind == "ERROR",
            width=34,
        )
        if settings.compare_active:
            header.label(text="Split compare active", icon="SPLIT_VERTICAL")
        _job(layout, settings)


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

        hero = _section(layout, "Hero source", "WORLD", _hero_state(settings))
        if not settings.build:
            _hint(hero, "Detect the live build to list every hero through S2V.")
        hero.prop(settings, "hero_slug", text="Hero")
        actions = hero.row(align=True)
        actions.enabled = not settings.job_running
        actions.operator("dmf.detect", text="Detect build", icon="FILE_REFRESH")
        actions.operator("dmf.extract", text="Extract hero", icon="EXPORT")
        _path_row(hero, settings, "body_dmx", "Body DMX")
        hero.operator("dmf.import_hero", text="Import hero skeleton", icon="ARMATURE_DATA")
        _path_row(hero, settings, "vmdl", "Hero vmdl")
        hero.operator("dmf.pick_vmdl", text="Choose S2V vmdl", icon="FILEBROWSER")
        _path_row(hero, settings, "materials_dir", "Hero materials")
        _hint(
            hero,
            "Content root with models/**/materials/*.vmat and their texture images; paths are preserved. Leave blank to use the extraction.",
            "MATERIAL",
        )
        hero.separator()
        hero.prop(settings, "target_armature", text="Hero skeleton")
        hero.prop(settings, "target_body", text="Hero body")

        custom = _section(layout, "Your model", "MESH_DATA", _mesh_state(settings))
        _path_row(custom, settings, "custom_model", "Model file")
        custom.operator("dmf.import_custom", text="Import model", icon="IMPORT")
        _path_row(custom, settings, "custom_materials_dir", "Custom materials")
        _hint(
            custom,
            "Content root with your model's materials/*.vmat and textures at the same relative paths it references. Copied after the hero materials.",
            "MATERIAL",
        )
        custom.separator()
        custom.prop(settings, "custom_mesh", text="Mesh")
        custom.prop(settings, "custom_armature", text="Rig (optional)")
        custom.prop(settings, "axis_preset", text="Fit transform")
        custom.prop(settings, "fit_scale", text="Scale")
        custom.prop(settings, "fit_to_height", text="Match hero height")
        _primary(custom, "dmf.fit", "Fit to hero", "TRANSFORM_ORIGINS", enabled=not settings.job_running)


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
        _hint(layout, "Hero body and custom mesh get separate local views. Both are driven by the same target rig when bound.", "SPLIT_VERTICAL")
        row = layout.row(align=True)
        row.operator("dmf.compare_split", text="Split compare", icon="SPLIT_VERTICAL")
        row.operator("dmf.compare_clear", text="Clear views", icon="FULLSCREEN_EXIT")
        layout.prop(settings, "compare_action", text="Action")
        layout.operator("dmf.apply_compare_action", text="Apply action to both rigs", icon="ACTION")


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
        _hint(layout, "Exact and declared aliases are matched. An unmatched weighted group is a decision, not a guess.", "BONE_DATA")

        top = layout.row(align=True)
        top.operator("dmf.scan_bones", text="Scan bone map", icon="FILE_REFRESH")
        top.prop(settings, "bone_filter", text="")
        row = layout.row()
        row.template_list(
            "DMF_UL_bone_map",
            "",
            settings,
            "bone_map",
            settings,
            "bone_map_index",
            rows=7,
        )
        side = row.column(align=True)
        side.operator("dmf.add_bone_entry", text="", icon="ADD")
        side.operator("dmf.remove_bone_entry", text="", icon="REMOVE")

        if not settings.bone_map:
            _hint(layout, "No rows yet. Scan the custom rig or add a row manually.", "QUESTION")
            return
        index = max(0, min(settings.bone_map_index, len(settings.bone_map) - 1))
        entry = settings.bone_map[index]
        edit = layout.box()
        edit.label(text=f"Row {index + 1}: {_STATE_LABELS.get(entry.state, entry.state)}", icon="PROPERTIES")
        edit.prop(entry, "source", text="Source")
        if settings.target_armature is not None:
            edit.prop_search(entry, "target", settings.target_armature.data, "bones", text="Target")
        else:
            edit.prop(entry, "target", text="Target")
        edit.prop(entry, "state", text="State")
        if entry.note:
            _hint(edit, entry.note, "INFO")
        actions = edit.row(align=True)
        actions.operator("dmf.rename_bones", text="Rename", icon="SORTALPHA")
        actions.operator("dmf.mark_extra", text="Extra", icon="BONE_DATA")
        actions.operator("dmf.ignore_entry", text="Ignore", icon="HIDE_ON")
        actions.operator("dmf.clear_target", text="Clear", icon="X")

        layout.separator()
        layout.label(text="Manual alignment", icon="CON_ROTLIKE")
        align = layout.row(align=True)
        align.operator("dmf.align_bone", text="Align rest", icon="SNAP_ON")
        align.operator("dmf.align_all_bones", text="Align all", icon="ARROW_LEFTRIGHT")
        align.operator("dmf.copy_pose", text="Copy pose", icon="COPYDOWN")
        nudge = layout.row(align=True)
        nudge.prop(settings, "nudge_axis", text="")
        nudge.prop(settings, "nudge_amount", text="")
        nudge.prop(settings, "nudge_rotate", text="Rotate")
        minus = nudge.operator("dmf.nudge_bone", text="-", icon="REMOVE")
        minus.direction = -1
        plus = nudge.operator("dmf.nudge_bone", text="+", icon="ADD")
        plus.direction = 1
        _hint(layout, "Rest alignment changes the bind pose; rebind if the mesh already has weights.", "INFO")


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
        _hint(layout, "The solver maps your groups, samples the hero surface when close, and uses bone envelopes outside the body. It does not call DATA_TRANSFER.", "MOD_VERTEX_WEIGHT")

        layout.prop(settings, "weight_mode", text="Method")
        options = layout.column(align=True)
        options.enabled = not settings.job_running
        options.prop(settings, "max_distance", text="Surface reach")
        options.prop(settings, "falloff", text="Falloff")
        options.prop(settings, "max_influences", text="Max influences")
        options.prop(settings, "surface_samples", text="Surface samples")
        options.prop(settings, "extra_policy", text="Extra bones")
        if settings.target_armature is not None:
            options.prop_search(settings, "fallback_bone", settings.target_armature.data, "bones", text="Fold fallback")
        else:
            options.prop(settings, "fallback_bone", text="Fold fallback")
        options.prop(settings, "protected_groups", text="Protect groups")
        options.prop(settings, "clear_existing", text="Clear old groups")
        _primary(
            layout,
            "dmf.retarget",
            "Solve & bind",
            "MOD_ARMATURE",
            enabled=not settings.job_running and settings.custom_mesh is not None and settings.target_armature is not None,
        )
        if settings.unmatched:
            note = layout.row()
            note.alert = True
            note.label(text="Unmapped: " + _short(settings.unmatched, 52), icon="STATUS_WARNING")

        layout.separator()
        layout.label(text="Manual weight tools", icon="BRUSH_DATA")
        manual = layout.column(align=True)
        manual.prop(settings, "manual_weight", text="Assign weight")
        row = manual.row(align=True)
        row.operator("dmf.select_unweighted", text="Select unweighted", icon="RESTRICT_SELECT_OFF")
        row.operator("dmf.assign_active_bone", text="Assign active", icon="BRUSH_DATA")
        row = manual.row(align=True)
        row.operator("dmf.smooth_active_group", text="Smooth active", icon="MOD_SMOOTH")
        row.operator("dmf.mirror_weights", text="Mirror L/R", icon="ARROW_LEFTRIGHT")
        row = manual.row(align=True)
        row.operator("dmf.normalize_weights", text="Normalize", icon="NORMALIZE_FCURVES")
        row.operator("dmf.limit_influences", text="Limit influences", icon="FULLSCREEN_ENTER")
        manual.operator("dmf.remove_zero_weights", text="Remove zero weights", icon="TRASH")

        layout.separator()
        box = _section(layout, "Axis proof", "CHECKMARK", settings.proof_status)
        box.label(text=f"Procedural gate: {_proof_gate(settings)}", icon=_CHECK_ICONS.get(_proof_gate(settings), "QUESTION"))
        if settings.proof_checks:
            for check in settings.proof_checks:
                check_row = box.row(align=True)
                check_row.alert = check.token in ("fail", "stale", "refused")
                check_row.label(text=f"{check.name}: {check.token}", icon=_CHECK_ICONS.get(check.token, "QUESTION"))
                if check.detail:
                    _hint(box, _short(check.detail, 84), "BLANK1")
        else:
            _hint(box, "No proof minted. Bind the model or run Mint Axis Proof.", "QUESTION")
        if settings.proof_claim:
            _hint(box, settings.proof_claim, "FILE")
        if settings.proof_digest:
            box.label(text="BLAKE3 " + _short(settings.proof_digest, 22), icon="LOCKED")
        if settings.proof_tick:
            box.label(text=f"Tick {settings.proof_tick}", icon="TIME")
        proof_row = box.row(align=True)
        proof_row.operator("dmf.mint_proof", text="Mint proof", icon="CHECKMARK")
        proof_row.operator("dmf.verify_proof", text="Verify", icon="FILE_REFRESH")
        box.prop(settings, "proof_presenter", text="Presenter")
        box.prop(settings, "proof_ticket", text="Ticket")
        _hint(box, "Export refuses when the proof is stale, unchecked, or any named check fails.", "LOCKED")

        layout.operator("dmf.copy_materials", text="Replace with hero materials", icon="MATERIAL")


class DMF_PT_handoff(Panel):
    bl_label = "Compiler Handoff"
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
        handoff = _section(layout, "Stage", "PACKAGE", "staged" if settings.stage_dir else "not staged")
        if settings.body_dmx and not settings.vmdl:
            _hint(handoff, "No S2V vmdl is set. Choose it below if the extraction did not write one.", "STATUS_WARNING", alert=True)
        handoff.prop(settings, "addon_name", text="Addon")
        _path_row(handoff, settings, "stage_dir", "Stage folder")
        handoff.label(text="Inside the content tree", icon="FILE")
        handoff.prop(settings, "vmdl_relative", text="vmdl path")
        handoff.prop(settings, "target_dmx_relative", text="DMX path")
        handoff.prop(settings, "generate_lods", text="Generate LODs")
        lod = handoff.column(align=True)
        lod.enabled = settings.generate_lods
        lod.prop(settings, "lod_count", text="LOD count (0 = hero)")
        lod.prop(settings, "lod_decimate", text="Decimate per LOD")
        _hint(handoff, "The S2V vmdl is copied unchanged. Compile uses a temporary CSDK content folder, removes it, and keeps only compiled files under <stage>/compiled.", "LOCKED")
        _primary(handoff, "dmf.export_stage", "Export & stage", "EXPORT", enabled=not settings.job_running)
        _primary(handoff, "dmf.compile", "Compile with CSDK13", "PLAY", enabled=not settings.job_running)


CLASSES = (DMF_PT_main, DMF_PT_source, DMF_PT_compare, DMF_PT_skeleton, DMF_PT_weights, DMF_PT_handoff)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
