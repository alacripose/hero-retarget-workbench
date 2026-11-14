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
    """Whether this build can host an add-on space type.

    The panel enum is the cheap answer, but a build that accepts a Space
    subclass may not list ``CUSTOM`` there until a space exists. Registering a
    throwaway space is the real test, and keeps a working PR build from being
    mistaken for stock and losing its editor (the 0.8.3 regression).
    """
    try:
        items = bpy.types.Panel.bl_rna.properties["bl_space_type"].enum_items
        if supports(item.identifier for item in items):
            return True
    except Exception:
        pass
    probe = type(
        "DMF_ST_capability_probe",
        (Space,),
        {
            "bl_idname": "DMF_ST_capability_probe",
            "bl_label": "Workbench capability probe",
        },
    )
    try:
        bpy.utils.register_class(probe)
        bpy.utils.unregister_class(probe)
        return True
    except Exception:
        return False


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
    strip = layout.column(align=True)
    for page in ui_props.PAGES:
        icon = ui_props.PAGE_ICONS.get(page, "DOT")
        label = page.replace("_", " ").title()
        try:
            strip.prop_enum(settings, "props_page", page, text=label, icon=icon)
        except TypeError:
            strip.prop_enum(settings, "props_page", page, text=label)


def _pages_header_draw(self, context) -> None:
    self.layout.label(text="Pages", icon="WINDOW")


def editor_space_classes() -> list[type]:
    """The editor, its header and root: without these there is no view."""
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
    # The root must stay: a page panel with an empty parent id draws nothing in
    # a custom space, which is exactly the empty view 0.8.7 shipped.
    return [space, header, root]


def pages_space_classes() -> list[type]:
    """The page panel in the Workbench's own expandable sidebar (UI region).

    A custom space has a real UI region - the black strip that expands out - and
    it accepts an add-on panel there. That is where the pages belong; 0.8.1-0.8.4
    split a second area beside the editor instead, which is the regression the
    owner called out.
    """
    pages_panel = type(
        PAGES_PANEL_IDNAME,
        (Panel,),
        {
            "bl_idname": PAGES_PANEL_IDNAME,
            "bl_label": "Pages",
            "bl_category": "Workbench",
            "bl_space_type": "CUSTOM",
            "bl_space_idname": SPACE_IDNAME,
            "bl_region_type": "UI",
            "bl_options": set(),
            "poll": classmethod(
                lambda cls, context: getattr(getattr(context, "scene", None), "dmf", None)
                is not None
            ),
            "draw": _pages_draw,
        },
    )
    ui_props.materialize(pages_panel)
    return [pages_panel]


def page_mirror_classes() -> list[type]:
    return [
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


def editor_classes() -> list[type]:
    """Every class the editor would like, or [] when the build cannot host it."""
    if not custom_space_supported():
        return []
    return [*editor_space_classes(), *pages_space_classes(), *page_mirror_classes()]


def _register_each(classes: list[type]) -> list[str]:
    """Register what this build accepts and keep the reasons for the rest."""
    failures: list[str] = []
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
            _REGISTERED.append(cls)
        except Exception as error:
            failures.append(f"{cls.__name__}: {type(error).__name__}: {error}")
    return failures


def register() -> bool:
    """Register the editor surface; False means the caller must fall back.

    The editor, header and root are required. Page mirrors and the companion
    strip are best effort: a build that refuses one panel must still get its
    view. 0.8.3 registered all classes as one block and lost the whole editor
    when the strip's space/header registration failed on the owner's build.
    """
    global EDITOR_ERROR
    if not custom_space_supported():
        return False
    failures = _register_each(editor_space_classes())
    if failures:
        EDITOR_ERROR = "; ".join(failures)
        print(f"DMF editor surface declined: {EDITOR_ERROR}", flush=True)
        unregister()
        return False
    optional = _register_each([*pages_space_classes(), *page_mirror_classes()])
    EDITOR_ERROR = ("; ".join(optional) if optional else "")
    if optional:
        print(f"DMF editor optional classes skipped: {EDITOR_ERROR}", flush=True)
    try:
        bpy.app.timers.register(_ensure_sidebar, persistent=True)
    except (ValueError, TypeError):
        pass
    return True


def unregister() -> None:
    try:
        bpy.app.timers.unregister(_ensure_sidebar)
    except (ValueError, TypeError):
        pass
    while _REGISTERED:
        bpy.utils.unregister_class(_REGISTERED.pop())


def _ensure_sidebar() -> float:
    """Open the Workbench sidebar once, from a timer rather than from draw.

    Setting ``show_region_ui`` inside a panel's draw re-lays the area during the
    draw and can leave the first frame without the page panel; the timer is also
    the only hook that runs when the space is created from the editor-type menu
    instead of our operator.
    """
    for window in bpy.context.window_manager.windows:
        if not window:
            continue
        for area in window.screen.areas:
            if area.type != "CUSTOM" or area.ui_type != SPACE_IDNAME:
                continue
            space = area.spaces.active
            if hasattr(space, "show_region_ui") and not space.show_region_ui:
                space.show_region_ui = True
                area.tag_redraw()
    return 1.0


def _open_editor(context, area) -> bool:
    """Make this area the Workbench and open its own page sidebar."""
    try:
        area.type = "CUSTOM"
        area.ui_type = SPACE_IDNAME
    except (TypeError, RuntimeError) as error:
        print(f"DMF editor switch declined: {error}", flush=True)
        return False
    space = area.spaces.active
    if hasattr(space, "show_region_ui"):
        space.show_region_ui = True
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
        if _REGISTERED:
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
