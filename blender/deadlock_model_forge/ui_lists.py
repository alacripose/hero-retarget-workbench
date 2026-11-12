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


CLASSES = (DMF_UL_bone_map,)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
