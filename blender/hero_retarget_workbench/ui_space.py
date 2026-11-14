"""The Workbench as its own editor type, on builds that can register one.

Blender 5.4.0 Alpha (daily build 2026-11-13) refuses this: registering a
``bpy.types.Space`` subclass answers ``Space does not support registration`` and
``Panel.bl_space_type`` has no ``CUSTOM``. Custom space types are PR 165087, and
the official patch builds of that PR accept the registration.

So the page surface has two homes and one page set:

* this module registers a real editor — ``DMF_ST_workbench`` with a header and
  the page panels in its WINDOW region — when the running build supports it;
* ``ui_props`` registers the same page panels in the Properties editor, which is
  what every released Blender can do.

``__init__`` asks for the editor first and falls back to the Properties tab only
when the build declines, so the same addon works on both. Neither branch hides an
error: the editor branch re-raises from the build if any class fails after the
space itself registered.
"""
from __future__ import annotations

import bpy
from bpy.types import Header, Operator, Panel, Space

from . import core, ui_props

SPACE_IDNAME = "DMF_ST_workbench"
HEADER_IDNAME = "DMF_HT_workbench"
ROOT_IDNAME = "DMF_PT_space_main"
PREFIX = "space"
_REGISTERED: list[type] = []


def supports(values) -> bool:
    """Whether a panel space-type enum names the custom space host."""
    return "CUSTOM" in {str(value) for value in values}


def custom_space_supported() -> bool:
    try:
        items = bpy.types.Panel.bl_rna.properties["bl_space_type"].enum_items
    except Exception:
        return False
    return supports(item.identifier for item in items)


def _status_line(layout, settings) -> None:
    message = getattr(settings, "status", "")
    if message:
        layout.label(text=message, icon=ui_props.status_icon(settings))


def _header_draw(self, context) -> None:
    layout = self.layout
    settings = context.scene.dmf
    try:
        layout.template_header()
    except (AttributeError, TypeError, RuntimeError):
        # A build without the template still gets the page box and the status.
        pass
    layout.prop(settings, "props_page", text="")
    layout.separator_spacer()
    _status_line(layout, settings)


def _root_draw(self, context) -> None:
    settings = context.scene.dmf
    layout = self.layout
    layout.use_property_split = False
    layout.use_property_decorate = False
    ui_props.draw_page_selector(layout, settings)
    _status_line(layout, settings)


def editor_classes() -> list[type]:
    """The editor and its pages, or an empty list when the build cannot."""
    if not custom_space_supported():
        return []
    space = type(
        SPACE_IDNAME,
        (Space,),
        {
            "bl_idname": SPACE_IDNAME,
            "bl_label": "Hero Retarget Workbench",
            "bl_icon": "ARMATURE_DATA",
            "bl_description": "Port a custom model onto a live Deadlock hero",
        },
    )
    header = type(
        HEADER_IDNAME,
        (Header,),
        {
            "bl_idname": HEADER_IDNAME,
            "bl_space_type": "CUSTOM",
            "bl_space_idname": SPACE_IDNAME,
            "bl_region_type": "HEADER",
            "draw": _header_draw,
        },
    )
    root = type(
        ROOT_IDNAME,
        (Panel,),
        {
            "bl_idname": ROOT_IDNAME,
            "bl_label": "Hero Retarget Workbench",
            "bl_space_type": "CUSTOM",
            "bl_space_idname": SPACE_IDNAME,
            "bl_region_type": "WINDOW",
            "bl_options": set(),
            "poll": classmethod(
                lambda cls, context: getattr(getattr(context, "scene", None), "dmf", None)
                is not None
            ),
            "draw": _root_draw,
        },
    )
    for cls in (space, header, root):
        ui_props.materialize(cls)
    mirrors = [
        ui_props.mirror(
            panel,
            ui_props.PAGE_BY_ID[panel.bl_idname],
            space_type="CUSTOM",
            prefix=PREFIX,
            space_idname=SPACE_IDNAME,
            root_idname=ROOT_IDNAME,
        )
        for panel in ui_props.page_panels()
    ]
    return [space, header, root, *mirrors]


def register() -> bool:
    """Register the editor surface; False means the caller must fall back."""
    classes = editor_classes()
    if not classes:
        return False
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
            _REGISTERED.append(cls)
    except Exception as error:
        print(f"DMF editor surface declined: {type(error).__name__}: {error}", flush=True)
        unregister()
        return False
    return True


def unregister() -> None:
    while _REGISTERED:
        bpy.utils.unregister_class(_REGISTERED.pop())


class DMF_OT_open_workbench(Operator):
    bl_idname = "dmf.open_workbench"
    bl_label = "Open Workbench Surface"
    bl_description = (
        "Switch this area to the Workbench's own editor when the build has one, "
        "otherwise to the Properties editor's Workbench tab"
    )

    def execute(self, context):
        area = context.area
        if area is None:
            self.report({"ERROR"}, "Run this from an area, not the status bar")
            return {"CANCELLED"}
        if _REGISTERED and custom_space_supported():
            try:
                # A custom space is a subtype of the CUSTOM host: the area takes
                # the host type first, then names which registered space it is.
                area.type = "CUSTOM"
                area.ui_type = SPACE_IDNAME
                return {"FINISHED"}
            except (TypeError, RuntimeError) as error:
                core.set_status(context.scene.dmf, f"Editor switch failed: {error}", "WARN")
        area.type = "PROPERTIES"
        space = area.spaces.active
        if hasattr(space, "context"):
            space.context = "SCENE"
        core.set_status(
            context.scene.dmf,
            "This Blender build has no custom editor types; showing the Properties tab",
            "WARN",
        )
        return {"FINISHED"}


CLASSES = (DMF_OT_open_workbench,)


def register_operators() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister_operators() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
