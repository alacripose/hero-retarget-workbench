"""Native UI lists for the workbench.

Every list implements ``filter_items`` through ``_filter``, so the native header
Blender shows above it, the search field, the invert toggle, the A-Z button and
its reverse, changes the view. A list that returns a fixed selection
makes those controls look available while doing nothing.
"""
from __future__ import annotations

import bpy
from bpy.types import UIList
from forge import cloth as clothscan
from forge import uilist

_ICONS = {
    "MAPPED": "CHECKMARK",
    "UNMATCHED": "QUESTION",
    "EXTRA": "BONE_DATA",
    "IGNORED": "HIDE_ON",
}


def _short(value: str, limit: int = 28) -> str:
    text = " ".join((value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _filter(ui_list, texts, restrict=None):
    """The list header's search, invert and sort, as ``bitflag_filter_item`` flags."""
    flags, order = uilist.rows(
        texts,
        getattr(ui_list, "filter_name", "") or "",
        sort_alpha=bool(getattr(ui_list, "use_filter_sort_alpha", False)),
        reverse=bool(getattr(ui_list, "use_filter_sort_reverse", False)),
        invert=bool(getattr(ui_list, "use_filter_invert", False)),
        restrict=restrict,
    )
    bit = getattr(ui_list, "bitflag_filter_item", 1)
    return [bit if flag else 0 for flag in flags], order


def _bone_map_text(entry) -> str:
    return f"{entry.source} {entry.target} {entry.note} {entry.state}"


def _rules_text(entry) -> str:
    state = "extra" if entry.state == "EXTRA" else "ignore" if entry.state == "IGNORED" else "mapped"
    origin = "learned" if entry.origin == "learned" else "user"
    return f"{entry.source} {entry.target} {state} {origin}"


class DMF_UL_heroes(UIList):
    bl_idname = "DMF_UL_heroes"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        # The page's own search and kind filter already narrowed the rows; the
        # native header narrows them once more without a second source of truth.
        return _filter(self, [f"{row.title} {row.kind} {row.model}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        settings = getattr(context.scene, "dmf", None)
        chosen = settings is not None and settings.hero_slug == item.slug
        row = layout.row(align=True)
        row.label(
            text=_short(item.title, 28) or item.slug,
            icon="RADIOBUT_ON" if chosen else "RADIOBUT_OFF",
        )
        right = row.row(align=True)
        right.alignment = "RIGHT"
        folder = item.kind.rstrip("/").split("/")[-1] if item.kind else "models"
        right.label(text=_short(folder, 14))


class DMF_UL_model_folders(UIList):
    bl_idname = "DMF_UL_model_folders"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.label} {row.root} {row.description}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        settings = getattr(context.scene, "dmf", None)
        chosen = settings is not None and settings.model_root == item.root
        row = layout.row(align=True)
        row.label(
            text=_short(item.label, 24) or item.root,
            icon="RADIOBUT_ON" if chosen else "RADIOBUT_OFF",
        )
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=f"{item.count:,} models")


class DMF_UL_bone_map(UIList):
    bl_idname = "DMF_UL_bone_map"

    def filter_items(self, context, data, propname):
        settings = context.scene.dmf
        rows = getattr(data, propname)
        mode = settings.bone_filter
        # The state selector is a restriction; the header's search narrows it and
        # the A-Z button sorts what survives.
        restrict = None if mode == "ALL" else [row.state == mode for row in rows]
        return _filter(self, [_bone_map_text(row) for row in rows], restrict)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.source or "source", icon=_ICONS.get(item.state, "DOT"))
        row.label(text=item.target or "no target", icon="FORWARD")
        if item.note:
            row.label(text="", icon="INFO")


class DMF_UL_hierarchy(UIList):
    bl_idname = "DMF_UL_hierarchy"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.name} {row.parent}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        for _ in range(min(item.depth, 10)):
            row.label(text="", icon="BLANK1")
        row.label(
            text=_short(item.name, 26) or "bone",
            icon="BONE_DATA" if item.children else "DOT",
        )
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if item.parent:
            right.label(text=f"< {_short(item.parent, 14)}", icon="BLANK1")
        else:
            right.label(text="root", icon="BLANK1")


class DMF_UL_parts(UIList):
    bl_idname = "DMF_UL_parts"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [row.object.name if row.object is not None else "missing part" for row in rows],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        obj = item.object
        if obj is None:
            row.label(text="missing part", icon="ERROR")
            return
        row.label(text=_short(obj.name), icon="MESH_DATA")
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=f"{len(obj.data.vertices):,}v / {len(obj.data.materials)}m")


class DMF_UL_materials(UIList):
    bl_idname = "DMF_UL_materials"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.label} {row.material.name if row.material else ''} {row.slot_index}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        material = item.material
        row.label(text=_short(item.label or (material.name if material else "empty slot")), icon="MATERIAL" if material else "BLANK1")
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=f"[{item.slot_index}]")


class DMF_UL_hero_parts(UIList):
    bl_idname = "DMF_UL_hero_parts"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.object.name if row.object else 'missing part'} "
                f"{'cloth' if row.object and clothscan.is_cloth(row.object.name) else ''}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        obj = item.object
        if obj is None:
            row.label(text="missing part", icon="ERROR")
            return
        row.label(text=_short(obj.name, 24), icon="MESH_DATA")
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if clothscan.is_cloth(obj.name):
            right.label(text="cloth")
        right.label(text=f"{len(obj.data.vertices):,}v")


class DMF_UL_cloth_chains(UIList):
    bl_idname = "DMF_UL_cloth_chains"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.name} {row.root} {row.side} {'cloth' if clothscan.is_cloth(row.name) else ''}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        icon = "MOD_CLOTH" if clothscan.is_cloth(item.name) else "BONE_DATA"
        built = item.target_mesh is not None
        row.label(
            text=_short(item.name, 24) or "chain",
            icon="CHECKMARK" if built else icon,
        )
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if built:
            right.label(text="cloth")
        right.label(text=f"{item.count}")


class DMF_UL_rules(UIList):
    bl_idname = "DMF_UL_bone_rules"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [_rules_text(row) for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="", emboss=False, icon="CHECKBOX_HLT" if item.enabled else "CHECKBOX_DEHLT")
        pattern = item.source or "pattern"
        target = item.target or "no target"
        if item.regex:
            row.label(text=_short(f"{pattern} -> {target}", 21), icon="DRIVER")
        elif "#" in pattern:
            row.label(text=_short(f"{pattern} -> {target} {item.delta:+d}", 21), icon="SORT_NUMERIC")
        elif pattern.strip().endswith("*"):
            row.label(text=_short(f"{pattern} -> {target or 'extra'}", 21), icon="FILE_FONT")
        else:
            stem = target.rsplit("_", 1)[0] if target.rsplit("_", 1)[-1] in ("L", "R") else target
            row.label(text=_short(f"{pattern}* -> {stem or '?'}*", 21), icon="LINKED")
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if item.state == "EXTRA":
            right.label(text="extra")
        elif item.state == "IGNORED":
            right.label(text="ignore")
        elif item.origin == "learned":
            right.label(text="learned")


class DMF_UL_clips(UIList):
    bl_idname = "DMF_UL_clips"

    _ICONS = {
        "EDITABLE": "ACTION",
        "IMPORTED": "CHECKMARK",
        "WRITTEN": "EXPORT",
        "FAILED": "ERROR",
        "OPAQUE": "LOCKED",
    }

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        wanted = getattr(getattr(context.scene, "dmf", None), "clip_ag_filter", "ALL")
        return _filter(
            self,
            [
                f"{row.label} {row.name} {row.kind} {'compiled' if row.compiled else ''} "
                f"{row.ag} {row.state} {row.action} {row.source_hero}"
                for row in rows
            ],
            restrict=None if wanted == "ALL" else [row.ag == wanted for row in rows],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=_short(item.label or item.name, 26), icon=self._ICONS.get(item.state, "ACTION"))
        right = row.row(align=True)
        right.alignment = "RIGHT"
        tag = item.kind if item.kind != "dmx" else ("dmx_c" if item.compiled else "dmx")
        right.label(text=f"{item.ag.lower()} {tag}" if item.ag != "UNKNOWN" else tag)
        if item.action and item.action != item.label:
            right.label(text="", icon="ACTION")
        if item.export_bytes:
            right.label(text="", icon="EXPORT")


class DMF_UL_ik(UIList):
    bl_idname = "DMF_UL_ik"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.bone} {row.target} {row.state}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = float(getattr(context.scene.dmf, "list_name_width", 0.5))
        split = layout.split(factor=width, align=True)
        left = split.row(align=True)
        left.label(
            text=item.bone or "IK target",
            icon="BONE_DATA" if item.state == "READY" else "CONSTRAINT",
        )
        right = split.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=item.target or "choose a limb")
        if item.constraints:
            right.label(text="", icon="CHECKMARK")


class DMF_UL_tail(UIList):
    bl_idname = "DMF_UL_tail"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.source} {row.target} {row.state}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = float(getattr(context.scene.dmf, "list_name_width", 0.5))
        split = layout.split(factor=width, align=True)
        left = split.row(align=True)
        left.label(text=item.source or "hero tail", icon="BONE_DATA")
        right = split.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=item.target or "choose a tail bone")
        if item.state == "MATCHED":
            right.label(text="", icon="CHECKMARK")


class DMF_UL_scan_roots(UIList):
    bl_idname = "DMF_UL_scan_roots"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.path} {row.note}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="", emboss=False)
        name = item.path.rstrip("/\\").split("\\")[-1].split("/")[-1] or item.path or "folder"
        row.label(text=_short(name, 20), icon="FILE_FOLDER")
        right = row.row(align=True)
        right.alignment = "RIGHT"
        if item.packages:
            right.label(text=f"{item.packages}")
            if item.folders:
                right.label(text="", icon="FILE_FOLDER")
            if item.vpks:
                right.label(text="", icon="PACKAGE")
            if item.blends:
                right.label(text="", icon="FILE_BLEND")
        elif item.note:
            right.label(text="missing", icon="ERROR")


class DMF_UL_mod_contents(UIList):
    bl_idname = "DMF_UL_mod_contents"

    _ICONS = {
        "models": "MESH_DATA",
        "clips": "ACTION",
        "materials": "MATERIAL",
        "blends": "FILE_BLEND",
        "other": "FILE",
    }

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.label} {row.category}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=_short(item.label, 34), icon=self._ICONS.get(item.category, "FILE"))
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=item.category)


class DMF_UL_mods(UIList):
    bl_idname = "DMF_UL_mods"

    _ICONS = {"vpk": "PACKAGE", "addon": "FILE_FOLDER", "blend": "FILE_BLEND"}

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.addon} {row.hero} {row.kind} {row.modified} {row.sections} {row.note} {row.path}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(
            text=_short(item.addon or "package", 26),
            icon=self._ICONS.get(item.kind, "PACKAGE"),
        )
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=item.modified or "unknown")


class DMF_UL_clients(UIList):
    bl_idname = "DMF_UL_clients"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [f"{row.label} {row.kind} {row.engine} {row.build} {row.path}" for row in rows],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = float(getattr(context.scene.dmf, "list_name_width", 0.5))
        split = layout.split(factor=width, align=True)
        if item.active:
            icon = "CHECKMARK"
        elif item.tool_active:
            icon = "TOOL_SETTINGS"
        elif item.can_compile:
            icon = "SETTINGS"
        else:
            icon = "PACKAGE"
        left = split.row(align=True)
        left.label(text=item.label or "install", icon=icon)
        right = split.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=_short(item.build or item.kind or "install", 20))


class DMF_UL_components(UIList):
    bl_idname = "DMF_UL_components"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.name} {row.relative} {row.kind} {row.bytes}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = float(getattr(context.scene.dmf, "list_name_width", 0.5))
        split = layout.split(factor=width, align=True)
        left = split.row(align=True)
        left.prop(
            item,
            "selected",
            text="",
            emboss=False,
            icon="CHECKBOX_HLT" if item.selected else "CHECKBOX_DEHLT",
        )
        left.label(text=item.name, icon="MESH_DATA" if item.kind == "dmx" else "FILE")
        right = split.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=item.kind)
        right.label(text=f"{item.bytes // 1024}k")


CLASSES = (
    DMF_UL_model_folders,
    DMF_UL_scan_roots,
    DMF_UL_mod_contents,
    DMF_UL_heroes,
    DMF_UL_bone_map,
    DMF_UL_mods,
    DMF_UL_clients,
    DMF_UL_components,
    DMF_UL_hierarchy,
    DMF_UL_parts,
    DMF_UL_materials,
    DMF_UL_hero_parts,
    DMF_UL_cloth_chains,
    DMF_UL_rules,
    DMF_UL_clips,
    DMF_UL_ik,
    DMF_UL_tail,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
