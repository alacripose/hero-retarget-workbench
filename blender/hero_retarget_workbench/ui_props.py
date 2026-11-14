"""The properties-editor surface: one page at a time instead of a sidebar stack.

Blender addons cannot add a new editor type, so the closest real thing to a
viewport type of its own is a tab in the Properties editor. Every page here is a
mirror of the matching sidebar panel — the same draw body, the same operators —
but only the selected page's panels exist while it is selected.

The mirrors are subclasses, so nothing is duplicated: a fix in ``ui.py`` reaches
both surfaces. ``poll`` switches on ``scene.dmf.props_page``; children follow
their mirrored parent.

Not every page is migrated away from the N-panel: the sidebar stays registered
because it is where this addon is normally opened from, and because the page list
is the same set either way.
"""
from __future__ import annotations

import bpy
from bpy.types import Panel

from . import ui

ROOT = "DMF_PT_props_main"

# Which page each sidebar panel belongs to. Children follow the page of the panel
# they are parented to, so the mapping only names every panel once.
PAGE_BY_ID = {
    "DMF_PT_setup": "SETUP",
    "DMF_PT_source": "SOURCE",
    "DMF_PT_source_files": "SOURCE",
    "DMF_PT_update": "SETUP",
    "DMF_PT_parts": "PARTS",
    "DMF_PT_parts_materials": "PARTS",
    "DMF_PT_cloth": "CLOTH",
    "DMF_PT_skeleton": "SKELETON",
    "DMF_PT_skeleton_bones": "SKELETON",
    "DMF_PT_rules": "RULES",
    "DMF_PT_animations": "ANIMATIONS",
    "DMF_PT_compare": "COMPARE",
    "DMF_PT_weights": "WEIGHTS",
    "DMF_PT_weights_manual": "WEIGHTS",
    "DMF_PT_handoff": "HANDOFF",
    "DMF_PT_handoff_paths": "HANDOFF",
}

PAGES = (
    "SETUP",
    "SOURCE",
    "PARTS",
    "CLOTH",
    "SKELETON",
    "RULES",
    "ANIMATIONS",
    "COMPARE",
    "WEIGHTS",
    "HANDOFF",
)


def current_page(context) -> str:
    scene = getattr(context, "scene", None)
    settings = getattr(scene, "dmf", None) if scene is not None else None
    return getattr(settings, "props_page", "") if settings is not None else ""


def mirror_id(panel_idname: str) -> str:
    return "DMF_PT_props_" + panel_idname[len("DMF_PT_"):]


def _page_poll(panel, page: str):
    inherited = panel.__dict__.get("poll")

    def poll(cls, context):
        if current_page(context) != page:
            return False
        if inherited is None:
            return True
        function = getattr(inherited, "__func__", inherited)
        try:
            return bool(function(cls, context))
        except TypeError:
            return bool(function(context))

    return classmethod(poll)


def mirror(panel, page: str) -> type[Panel]:
    """A properties-editor twin of ``panel``, visible only on ``page``."""
    idname = mirror_id(panel.bl_idname)
    parent = ROOT
    source_parent = getattr(panel, "bl_parent_id", "") or ""
    if source_parent and source_parent != "DMF_PT_main":
        parent = mirror_id(source_parent)
    return type(
        idname,
        (panel,),
        {
            "bl_idname": idname,
            "bl_space_type": "PROPERTIES",
            "bl_region_type": "WINDOW",
            "bl_context": "scene",
            "bl_parent_id": parent,
            "bl_options": set(),
            "poll": _page_poll(panel, page),
        },
    )


class DMF_PT_props_main(Panel):
    bl_label = "Hero Retarget Workbench"
    bl_idname = ROOT
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    @classmethod
    def poll(cls, context):
        return getattr(getattr(context, "scene", None), "dmf", None) is not None

    def draw(self, context):
        settings = context.scene.dmf
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        header = layout.row(align=True)
        header.label(text="Page", icon="WINDOW")
        header.prop(settings, "props_page", text="")
        grid = layout.grid_flow(columns=2, even_columns=True, even_rows=True, align=True)
        for page in PAGES:
            grid.prop_enum(settings, "props_page", page)

        message = getattr(settings, "status", "")
        level = getattr(settings, "status_kind", "")
        if message:
            layout.label(
                text=message,
                icon={"ERROR": "ERROR", "WARN": "ERROR", "BUSY": "TIME"}.get(level, "INFO"),
            )


CLASSES = [DMF_PT_props_main] + [
    mirror(panel, PAGE_BY_ID[panel.bl_idname])
    for panel in ui.CLASSES
    if isinstance(panel, type)
    and issubclass(panel, Panel)
    and panel.bl_idname in PAGE_BY_ID
]


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
