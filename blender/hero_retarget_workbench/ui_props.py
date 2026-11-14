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

import sys

import bpy
from bpy.types import Panel

from . import ui, ui_mods


def materialize(cls):
    """Publish a dynamically created class in its module.

    Blender resolves a registered panel back to its Python class by module and
    name, so a class made with ``type()`` that is not an attribute of its module
    draws as a struct with no Python class ("unable to get Python class for RNA
    struct"). Every class this addon creates at runtime goes through here.
    """
    cls.__module__ = __name__
    setattr(sys.modules[__name__], cls.__name__, cls)
    return cls

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
    "DMF_PT_setup_tools": "SETUP",
    "DMF_PT_mods": "MODS",
    "DMF_PT_components": "COMPONENTS",
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
    "MODS",
    "COMPONENTS",
)

# Small icon buttons, the way the Properties editor's own tabs read, instead of a
# text grid. The dropdown stays for discoverability and for keyboard users.
PAGE_ICONS = {
    "SETUP": "SETTINGS",
    "SOURCE": "IMPORT",
    "PARTS": "MESH_DATA",
    "CLOTH": "MOD_CLOTH",
    "SKELETON": "ARMATURE_DATA",
    "RULES": "FILTER",
    "ANIMATIONS": "ACTION",
    "COMPARE": "SPLIT_VERTICAL",
    "WEIGHTS": "MOD_VERTEX_WEIGHT",
    "HANDOFF": "EXPORT",
    "MODS": "PACKAGE",
    "COMPONENTS": "MODIFIER",
}


def draw_page_rail(layout, settings) -> None:
    """The page strip: one small icon button per page, stacked on the left.

    The Properties editor puts its tabs in a narrow column against the left edge
    of the area; an add-on cannot register that region for its own space, so this
    is the same control (icon-only, one page at a time, selected page depressed)
    drawn as the first thing in the page area.
    """
    rail = layout.column(align=True)
    for page in PAGES:
        row = rail.row(align=True)
        row.alignment = "LEFT"
        row.prop_enum(settings, "props_page", page, text="", icon=PAGE_ICONS.get(page, "DOT"))
    layout.separator(factor=0.4)


def status_icon(settings) -> str:
    level = getattr(settings, "status_kind", "")
    return {"ERROR": "ERROR", "WARN": "ERROR", "BUSY": "TIME"}.get(level, "INFO")


def draw_page_selector(layout, settings) -> None:
    """The header row: the page enum for quick jumping and the icon rail below."""
    header = layout.row(align=True)
    header.label(text="Page", icon="WINDOW")
    header.prop(settings, "props_page", text="")
    draw_page_rail(layout, settings)


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


def mirror(
    panel,
    page: str,
    space_type: str = "PROPERTIES",
    prefix: str = "props",
    space_idname: str = "",
    root_idname: str = ROOT,
) -> type[Panel]:
    """A twin of ``panel`` in another space, visible only on ``page``.

    The space is a parameter because the same page set serves two surfaces: the
    Properties editor (always available) and the add-on's own editor type (only
    on builds with custom space registration). The draw body is inherited either
    way, so a page cannot differ between them.
    """
    suffix = panel.bl_idname[len("DMF_PT_"):]
    idname = f"DMF_PT_{prefix}_{suffix}"
    parent = root_idname
    source_parent = getattr(panel, "bl_parent_id", "") or ""
    if source_parent and source_parent != "DMF_PT_main":
        parent = f"DMF_PT_{prefix}_{source_parent[len('DMF_PT_'):]}"
    attributes = {
        "bl_idname": idname,
        "bl_space_type": space_type,
        "bl_region_type": "WINDOW",
        "bl_parent_id": parent,
        "bl_options": set(),
        "poll": _page_poll(panel, page),
    }
    if space_type == "PROPERTIES":
        attributes["bl_context"] = "scene"
    if space_idname:
        attributes["bl_space_idname"] = space_idname
    return materialize(type(idname, (panel,), attributes))


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
        draw_page_rail(layout, settings)
        editor = ui.surface_name() == "editor"
        layout.operator(
            "dmf.open_workbench",
            text="Open the Workbench editor" if editor else "Open the Workbench page",
            icon="WINDOW" if editor else "PROPERTIES",
        )
        if not editor:
            layout.label(
                text="This Blender build cannot register editor types; pages open here",
                icon="INFO",
            )
        error = ui.surface_error()
        if error:
            layout.label(text=f"Editor type failed: {error}", icon="ERROR")

        message = getattr(settings, "status", "")
        if message:
            layout.label(text=message, icon=status_icon(settings))


def page_panels() -> list[type[Panel]]:
    """Every sidebar panel that belongs to a page, in registration order."""
    return [
        panel
        for panel in (*ui.CLASSES, *ui_mods.CLASSES)
        if isinstance(panel, type)
        and issubclass(panel, Panel)
        and panel.bl_idname in PAGE_BY_ID
    ]


CLASSES = [DMF_PT_props_main] + [
    mirror(panel, PAGE_BY_ID[panel.bl_idname]) for panel in page_panels()
]
_REGISTERED: list[type] = []


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
        _REGISTERED.append(cls)


def unregister() -> None:
    while _REGISTERED:
        bpy.utils.unregister_class(_REGISTERED.pop())
