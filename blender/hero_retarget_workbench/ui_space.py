"""The Workbench as its own editor type, with its own page strip.

Blender 5.4.0 Alpha (daily build 2026-11-13) refuses this: registering a
``bpy.types.Space`` subclass answers ``Space does not support registration`` and
``Panel.bl_space_type`` has no ``CUSTOM``. Custom space types are PR 165087, and
the official patch builds of that PR accept the registration.

The surface is one editor, not a tab in somebody else's editor:

* ``DMF_ST_workbench`` holds the page panels in its WINDOW region;
* ``DMF_ST_workbench_pages`` is a narrow companion area, split off to the left
  of the Workbench when it opens, whose only panel is the page strip. Blender
  does not let an add-on put a panel in a space's NAVIGATION_BAR, so the strip
  gets its own real area instead of being squeezed into the page body: that is
  what made 0.8.0 worse than the old Properties tab.

On a build without custom spaces the add-on does not degrade into the Properties
editor: it opens the 3D viewport sidebar, which is the only surface the released
builds can host, and says so in the status line.
"""
from __future__ import annotations

import bpy
from bpy.types import Header, Operator, Panel, Space

from . import core, ui_props

SPACE_IDNAME = "DMF_ST_workbench"
HEADER_IDNAME = "DMF_HT_workbench"
ROOT_IDNAME = "DMF_PT_space_main"
PAGES_SPACE_IDNAME = "DMF_ST_workbench_pages"
PAGES_HEADER_IDNAME = "DMF_HT_workbench_pages"
PAGES_PANEL_IDNAME = "DMF_PT_space_pages"
PREFIX = "space"
_REGISTERED: list[type] = []
# Why register() declined, when this build could have hosted the editor. The
# panel shows it, so a failed editor is never a silent Properties fallback.
EDITOR_ERROR = ""


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
    layout.label(text="Workbench", icon="ARMATURE_DATA")
    layout.prop(settings, "props_page", text="")
    layout.separator_spacer()
    _status_line(layout, settings)


def _root_draw(self, context) -> None:
    settings = context.scene.dmf
    layout = self.layout
    layout.use_property_split = False
    layout.use_property_decorate = False
    _status_line(layout, settings)


def _pages_draw(self, context) -> None:
    settings = context.scene.dmf
    layout = self.layout
    layout.use_property_split = False
    layout.use_property_decorate = False
    current = getattr(settings, "props_page", "SETUP")
    strip = layout.column(align=True)
    for page in ui_props.PAGES:
        icon = ui_props.PAGE_ICONS.get(page, "DOT")
        try:
            strip.prop_enum(settings, "props_page", page, text="", icon=icon)
        except TypeError:
            strip.prop_enum(settings, "props_page", page, text="")
        if page == current:
            strip.separator(factor=0.2)


def _pages_header_draw(self, context) -> None:
    self.layout.label(text="Pages", icon="WINDOW")


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
    pages_space = type(
        PAGES_SPACE_IDNAME,
        (Space,),
        {
            "bl_idname": PAGES_SPACE_IDNAME,
            "bl_label": "Workbench Pages",
            "bl_icon": "WINDOW",
            "bl_description": "The Workbench page strip",
        },
    )
    pages_header = type(
        PAGES_HEADER_IDNAME,
        (Header,),
        {
            "bl_idname": PAGES_HEADER_IDNAME,
            "bl_space_type": "CUSTOM",
            "bl_space_idname": PAGES_SPACE_IDNAME,
            "bl_region_type": "HEADER",
            "draw": _pages_header_draw,
        },
    )
    pages_panel = type(
        PAGES_PANEL_IDNAME,
        (Panel,),
        {
            "bl_idname": PAGES_PANEL_IDNAME,
            "bl_label": "Pages",
            "bl_space_type": "CUSTOM",
            "bl_space_idname": PAGES_SPACE_IDNAME,
            "bl_region_type": "WINDOW",
            "bl_options": set(),
            "poll": classmethod(
                lambda cls, context: getattr(getattr(context, "scene", None), "dmf", None)
                is not None
            ),
            "draw": _pages_draw,
        },
    )
    for cls in (space, header, root, pages_space, pages_header, pages_panel):
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
    return [space, header, root, pages_space, pages_header, pages_panel, *mirrors]


def register() -> bool:
    """Register the editor surface; False means the caller must fall back."""
    global EDITOR_ERROR
    classes = editor_classes()
    if not classes:
        return False
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
            _REGISTERED.append(cls)
    except Exception as error:
        EDITOR_ERROR = f"{type(error).__name__}: {error}"
        print(f"DMF editor surface declined: {EDITOR_ERROR}", flush=True)
        unregister()
        return False
    EDITOR_ERROR = ""
    return True


def unregister() -> None:
    while _REGISTERED:
        bpy.utils.unregister_class(_REGISTERED.pop())


def _open_editor(context, area) -> bool:
    """Put the pages strip on the left and the Workbench editor beside it."""
    screen = context.screen
    if screen is None:
        return False
    existing = [
        candidate
        for candidate in screen.areas
        if candidate.type == "CUSTOM" and candidate.ui_type == SPACE_IDNAME
    ]
    if existing:
        # Already open somewhere in this screen: just name this area.
        area.type = "CUSTOM"
        area.ui_type = SPACE_IDNAME
        return True
    before = {candidate.as_pointer() for candidate in screen.areas}
    # A fixed share of the area is wrong at both ends: 7% of the Properties
    # column is 15 px and clips the icons, 7% of a maximised viewport is 130 px of
    # empty strip. Aim at a strip's width in pixels and clamp the share.
    share = min(0.3, max(0.02, 46.0 / max(float(area.width), 1.0)))
    try:
        with context.temp_override(window=context.window, screen=screen, area=area):
            split = bpy.ops.screen.area_split(direction="VERTICAL", factor=share)
    except (TypeError, RuntimeError) as error:
        print(f"DMF page-strip split declined: {error}", flush=True)
        return False
    if split != {"FINISHED"}:
        return False
    fresh = next(
        (candidate for candidate in screen.areas if candidate.as_pointer() not in before),
        None,
    )
    if fresh is None:
        return False
    left, right = (area, fresh) if area.x <= fresh.x else (fresh, area)
    try:
        left.type = "CUSTOM"
        left.ui_type = PAGES_SPACE_IDNAME
        right.type = "CUSTOM"
        right.ui_type = SPACE_IDNAME
    except (TypeError, RuntimeError) as error:
        print(f"DMF editor switch declined after the split: {error}", flush=True)
        return False
    try:
        left.spaces.active.show_region_header = False
    except (AttributeError, TypeError):
        pass
    return True


class DMF_OT_open_workbench(Operator):
    bl_idname = "dmf.open_workbench"
    bl_label = "Open Workbench Surface"
    bl_description = (
        "Open the Workbench in its own editor area, with the page strip on the "
        "left; on builds without custom editor types, open the 3D viewport sidebar"
    )

    def execute(self, context):
        area = context.area
        if area is None:
            self.report({"ERROR"}, "Run this from an area, not the status bar")
            return {"CANCELLED"}
        if _REGISTERED and custom_space_supported():
            if _open_editor(context, area):
                core.set_status(context.scene.dmf, "", "INFO")
                return {"FINISHED"}
            try:
                area.type = "CUSTOM"
                area.ui_type = SPACE_IDNAME
            except (TypeError, RuntimeError) as error:
                core.set_status(context.scene.dmf, f"Editor switch failed: {error}", "WARN")
                return {"CANCELLED"}
            core.set_status(
                context.scene.dmf,
                "Opened the editor without its page strip (the area split was declined)",
                "WARN",
            )
            return {"FINISHED"}
        if area.type != "VIEW_3D":
            area.type = "VIEW_3D"
        space = area.spaces.active
        if hasattr(space, "show_region_ui"):
            space.show_region_ui = True
        core.set_status(
            context.scene.dmf,
            "This Blender build cannot register editor types; open the Deadlock "
            "sidebar (N) instead",
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
