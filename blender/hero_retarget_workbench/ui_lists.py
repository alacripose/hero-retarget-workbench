"""Native UI lists for the workbench."""
from __future__ import annotations

import bpy
from bpy.types import UIList

_ICONS = {
    "MAPPED": "CHECKMARK",
    "UNMATCHED": "QUESTION",
    "EXTRA": "BONE_DATA",
    "IGNORED": "HIDE_ON",
}


def _short(value: str, limit: int = 28) -> str:
    text = " ".join((value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


class DMF_UL_bone_map(UIList):
    bl_idname = "DMF_UL_bone_map"

    def filter_items(self, context, data, propname):
        settings = context.scene.dmf
        rows = getattr(data, propname)
        mode = settings.bone_filter
        if mode == "ALL":
            return [], []
        flags = [self.bitflag_filter_item if row.state == mode else 0 for row in rows]
        return flags, []

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.source or "source", icon=_ICONS.get(item.state, "DOT"))
        row.label(text=item.target or "no target", icon="FORWARD")
        if item.note:
            row.label(text="", icon="INFO")


class DMF_UL_hierarchy(UIList):
    bl_idname = "DMF_UL_hierarchy"

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

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        material = item.material
        row.label(text=_short(item.label or (material.name if material else "empty slot")), icon="MATERIAL" if material else "BLANK1")
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=f"[{item.slot_index}]")


class DMF_UL_rules(UIList):
    bl_idname = "DMF_UL_bone_rules"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="", emboss=False, icon="CHECKBOX_HLT" if item.enabled else "CHECKBOX_DEHLT")
        pattern = item.source or "pattern"
        target = item.target or "no target"
        if item.regex:
            row.label(text=_short(f"{pattern} -> {target}", 21), icon="DRIVER")
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
        "FAILED": "ERROR",
        "OPAQUE": "LOCKED",
    }

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=_short(item.label or item.name, 26), icon=self._ICONS.get(item.state, "ACTION"))
        right = row.row(align=True)
        right.alignment = "RIGHT"
        tag = item.kind if item.kind != "dmx" else ("dmx_c" if item.compiled else "dmx")
        right.label(text=tag)
        if item.action and item.action != item.label:
            right.label(text="", icon="ACTION")


CLASSES = (
    DMF_UL_bone_map,
    DMF_UL_hierarchy,
    DMF_UL_parts,
    DMF_UL_materials,
    DMF_UL_rules,
    DMF_UL_clips,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
