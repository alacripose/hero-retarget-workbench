"""The shared surface grammar: Apple's hierarchy, in Blender's native widgets.

One page title, one state and build line, flat labeled groups, text actions in
rows of two, folded advanced panels, and one message for the thing that needs
attention. Blender has no font sizes, colours or dashed rules, so the hierarchy
comes from order, spacing and the panel tree. Blender's own dark theme supplies
the colour; nothing here invents a palette.
"""
from __future__ import annotations

import re
import textwrap


def region_width(default: int = 420) -> int:
    """The width of the surface being drawn, in pixels, when Blender knows it."""
    try:
        import bpy

        region = bpy.context.region
        if region is not None and region.width:
            return max(220, int(region.width))
    except Exception:
        pass
    return default


def text_columns(width: int | None = None) -> int:
    """A readable line length for the width the panel has.

    Blender has no label wrapping. The old helpers wrapped every hint at 28 to
    36 characters and left half of a wide editor empty. This measures the
    surface, keeps a comfortable 65 to 78 character measure on wide surfaces,
    and lets a narrow sidebar use its full width. The 6.4px estimate is for
    Blender's default 11px interface font and is adjusted by the UI scale.
    """
    pixels = max(220, int(width if width is not None else region_width()))
    scale = 1.0
    try:
        import bpy

        scale = max(0.75, float(bpy.context.preferences.system.ui_scale))
    except Exception:
        pass
    usable = max(160, pixels - 44)
    columns = int(usable / (6.4 * scale))
    return max(28, min(78, columns))


def wrap_text(text: str, width: int | None = None) -> list[str]:
    """Wrap one paragraph to the surface width, never to a guessed fixed width."""
    flat = " ".join((text or "").split())
    return textwrap.wrap(
        flat,
        width=text_columns(width),
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]

# The Popit names the thing being edited, its state, and the tools that act on
# it; these helpers keep each page to that shape.
def title(layout, name: str, detail: str = "", icon: str = "NONE", alert: bool = False):
    """The card a page opens with: one name, one state, nothing else."""
    box = layout.box()
    head = box.row(align=True)
    head.alert = alert
    head.scale_y = 1.2
    head.label(text=name, icon=icon)
    if detail:
        if region_width() < 480:
            line = box.row(align=True)
            line.alignment = "RIGHT"
            line.label(text=detail)
        else:
            right = head.row(align=True)
            right.alignment = "RIGHT"
            right.label(text=detail)
    return box


def page(layout, settings, name: str, detail: str = "", icon: str = "NONE", alert: bool = False):
    """The page body under its panel title: state, builds, then controls.

    The page name lives in the panel header, which is the one title the view
    needs. Repeating it in a card made every page start with two headings; the
    card also turned the body into a box inside the panel. Only the compact
    state and build line remain here.
    """
    column = layout.column(align=True)
    if detail:
        state = column.row(align=True)
        state.alert = alert
        state.scale_y = 0.95
        if icon != "NONE":
            state.label(text="", icon=icon)
        state.label(text=detail)
    rows = []
    try:
        from . import core

        rows = core.marker_rows(settings)
    except Exception:
        pass
    if rows:
        # One compact build line, the way a native tool names its environment.
        # The three separate rows were half of the Setup page's text weight and
        # repeated on every page. The full paths and build dates live on Setup.
        labels = {"Extract": "Live", "Compile": "CSDK", "Backport": "Target"}
        parts = []
        for label, value, _marker in rows:
            match = re.search(r"\b(\d{3,})\b", value or "")
            build = match.group(1) if match else (value or "not set")
            parts.append(f"{labels.get(label, label)} {build}")
        chunks = [parts[:2], parts[2:]] if len(parts) > 2 else [parts]
        for index, chunk in enumerate(chunks):
            row = column.row(align=True)
            row.scale_y = 0.85
            row.label(text="   ".join(chunk), icon="INFO" if index == 0 else "BLANK1")
    kind = getattr(settings, "status_kind", "")
    if (
        region_width() < 650
        and getattr(settings, "status", "")
        and kind in {"WARN", "ERROR", "REFUSED"}
    ):
        icon = "ERROR" if kind in {"WARN", "ERROR", "REFUSED"} else "CHECKMARK" if kind == "OK" else "INFO"
        hint(
            column,
            settings.status,
            icon,
            alert=kind in {"WARN", "ERROR", "REFUSED"},
        )
    return column


def section(layout, name: str, icon: str = "NONE", detail: str = "", alert: bool = False):
    """A flat group inside a page, separated by space instead of another card.

    The page already supplies the outer card. Boxing every group inside it made
    a stack of boxes inside a box, which is the visual weight the owner rejected.
    """
    layout.separator(factor=0.55)
    column = layout.column(align=True)
    head = column.row(align=True)
    head.alert = alert
    head.scale_y = 1.0
    head.label(text=name, icon=icon)
    if detail:
        if region_width() < 480:
            line = column.row(align=True)
            line.alignment = "RIGHT"
            line.label(text=detail)
        else:
            right = head.row(align=True)
            right.alignment = "RIGHT"
            right.label(text=detail)
    body = column.column(align=True)
    return body


def stat(layout, label: str, value: str, icon: str = "BLANK1") -> None:
    """One muted fact: the label on the left, the value against the right edge."""
    row = layout.row(align=True)
    row.scale_y = 0.9
    row.label(text=label, icon=icon)
    if region_width() < 390 and len(value) > 28:
        line = layout.row(align=True)
        line.alignment = "RIGHT"
        line.label(text=value, icon="BLANK1")
    else:
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=value)


def micro(layout, text: str, icon: str = "NONE") -> None:
    """A small group label inside a card, in readable sentence case."""
    row = layout.row(align=True)
    row.scale_y = 0.95
    if icon == "NONE":
        row.label(text=text)
    else:
        row.label(text=text, icon=icon)


def chips(layout, settings, prop: str, values) -> None:
    """Filter choices as one button per label, never a label column.

    ``grid_flow`` inherits the panel's property split and moves the first
    chip's text into the property-name column, leaving an empty button. A
    plain row of enum buttons keeps every label inside its own button.
    """
    split = layout.use_property_split
    layout.use_property_split = False
    column = layout.column(align=True)
    column.use_property_split = False
    columns = 2 if len(values) == 4 else max(1, min(3, len(values)))
    for start in range(0, len(values), columns):
        row = column.row(align=True)
        row.use_property_split = False
        row.scale_y = 1.1
        for value, label in values[start:start + columns]:
            row.prop_enum(settings, prop, value, text=label)
    layout.use_property_split = split


def columns(layout, name_width: float, details: tuple[float, ...] = (1.0,)):
    """Split one row into category cells: the name first, then the details.

    ``name_width`` is the share of the row the name gets. The detail weights
    divide what remains, so a header and its UIList rows can call this with the
    same values and line up. Blender has no draggable column separators, so the
    caller pairs this with its own name-width slider.
    """
    width = max(0.05, min(0.95, float(name_width)))
    weights = [width]
    remaining = max(0.0, 1.0 - width)
    total = sum(max(0.0, float(weight)) for weight in details) or 1.0
    weights.extend(remaining * max(0.0, float(weight)) / total for weight in details)
    cells = []
    current = layout
    left = 1.0
    for weight in weights[:-1]:
        split = current.split(factor=weight / left, align=True)
        cells.append(split.row(align=True))
        current = split.row(align=True)
        left -= weight
    cells.append(current.row(align=True))
    return cells


def column_header(layout, name_width: float, labels: tuple[str, ...], details: tuple[float, ...]) -> None:
    """A category header aligned to the same split as its list rows."""
    cells = columns(layout, name_width, details)
    for cell, label in zip(cells, labels):
        cell.label(text=label)


def name_width(layout, settings, prop: str) -> None:
    """The one width control a category list needs."""
    factor = 0.38 if region_width() < 480 else 0.26
    row = layout.split(factor=factor, align=True)
    row.scale_y = 0.85
    row.label(text="Name width")
    row.prop(settings, prop, text="", slider=True)


def glyphs(layout, buttons, enabled: bool = True, labels: dict | None = None):
    """Actions in rows of two, with words.

    A four-icon strip made the user decode the tool before using it. Apple's
    guidance is to use text when a short label is clearer than a symbol, and to
    keep adjacent text buttons to a pair. Four actions become a stable 2 by 2
    block instead of a toolbar of unknown glyphs.
    """
    labels = labels or {}
    if len(buttons) == 1:
        row = layout.row(align=True)
        row.scale_y = 1.18
        row.enabled = enabled
        operator = buttons[0]
        row.operator(operator, text=labels.get(operator, ""), icon=_icon(operator))
        return row
    if len(buttons) == 2:
        row = layout.row(align=True)
        row.scale_y = 1.18
        row.enabled = enabled
        for operator in buttons:
            row.operator(operator, text=labels.get(operator, ""), icon=_icon(operator))
        return row
    grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
    grid.scale_y = 1.18
    grid.enabled = enabled
    for operator in buttons:
        grid.operator(operator, text=labels.get(operator, ""), icon=_icon(operator))
    return grid


def hint(layout, text: str, icon: str = "INFO", alert: bool = False, width: int | None = None) -> None:
    """Wrapped explanatory text that uses the width it is given."""
    lines = wrap_text(text, width)
    column = layout.column(align=True)
    for index, line in enumerate(lines):
        row = column.row(align=True)
        row.alert = alert
        row.scale_y = 0.92
        row.label(text=line, icon=icon if index == 0 else "BLANK1")


def bubble(layout, text: str, icon: str = "INFO", alert: bool = False):
    """The one status message a page is allowed, wrapped to the surface."""
    box = layout.box()
    lines = wrap_text(text)
    for index, line in enumerate(lines):
        row = box.row(align=True)
        row.alert = alert
        row.scale_y = 0.92
        row.label(text=line, icon=icon if index == 0 else "BLANK1")
    return box


def _job_stages(settings):
    """The named steps a background job reported, in the order it named them."""
    if getattr(settings, "job_kind", "") != "BACKGROUND":
        return []
    return list(getattr(settings, "job_stages", ()) or ())


def _stage_row(box, stage):
    """One named step: its label, state and the bar for that stage."""
    row = box.row(align=True)
    row.scale_y = 0.9
    icon = {
        "DONE": "CHECKMARK",
        "FAILED": "ERROR",
        "RUNNING": "TIME",
    }.get(stage.state, "BLANK1")
    row.label(text=stage.label or stage.key, icon=icon)
    if stage.state == "RUNNING":
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=f"{int(stage.progress * 100)}%")
    box.prop(
        stage,
        "progress",
        text=stage.message or stage.state.lower(),
        slider=True,
    )


def job(layout, settings):
    """Progress for the running job, or the last run's steps once it finished.

    A page whose button starts background work must show that work moving; the
    Popit allows one message, so the bar carries the current step and the last
    three steps stay under it. After the job the named steps stay as a compact
    card, which is the verbosity asked for without a console-only trail.
    """
    running = bool(getattr(settings, "job_running", False))
    log = [line for line in (getattr(settings, "job_log", "") or "").splitlines() if line]
    state = getattr(settings, "job_state", "")
    stage_rows = _job_stages(settings)
    if not running and not log:
        return None
    if not running and not stage_rows:
        # Jobs without named stages keep the one-line history row; a failed
        # job still keeps the last line of its log under it.
        row = layout.row(align=True)
        row.alert = state == "FAILED"
        row.scale_y = 1.0
        row.label(
            text=getattr(settings, "job_label", "") or "Last run",
            icon="ERROR" if state == "FAILED" else "CHECKMARK",
        )
        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=state.lower() or "finished")
        right.operator("dmf.clear_job", text="", icon="X")
        if state == "FAILED" and log:
            hint(layout, log[-1], "ERROR", alert=True)
        return row
    box = layout.box()
    head = box.row(align=True)
    head.alert = state == "FAILED"
    head.label(
        text=getattr(settings, "job_label", "") or ("Working" if running else "Last run"),
        icon="TIME" if running else ("ERROR" if state == "FAILED" else "CHECKMARK"),
    )
    right = head.row(align=True)
    right.alignment = "RIGHT"
    if running:
        right.label(text=f"{int(getattr(settings, 'job_progress', 0.0) * 100)}%")
    else:
        right.label(text=state.lower() or "finished")
        right.operator("dmf.clear_job", text="", icon="X")
    if running:
        box.prop(
            settings,
            "job_progress",
            text=getattr(settings, "job_message", ""),
            slider=True,
        )
    for stage in stage_rows:
        _stage_row(box, stage)
    if running or state == "FAILED":
        for line in log[-2:]:
            row = box.row(align=True)
            row.scale_y = 0.85
            row.label(text=line, icon="BLANK1" if line != log[-1] else "FORWARD")
    if running and getattr(settings, "job_kind", "") == "BACKGROUND":
        box.operator("dmf.cancel_job", text="Cancel job", icon="CANCEL")
    elif running and getattr(settings, "job_cancellable", False):
        box.operator("dmf.cancel_weight_job", text="Cancel after this chunk", icon="CANCEL")
    return box


_GLYPHS = {
    "dmf.detect_paths": "FILE_REFRESH",
    "dmf.detect": "FILE_REFRESH",
    "dmf.extract": "EXPORT",
    "dmf.import_hero": "MESH_DATA",
    "dmf.import_custom": "IMPORT",
    "dmf.fit": "TRANSFORM_ORIGINS",
    "dmf.scan_parts": "FILE_REFRESH",
    "dmf.use_active_collection": "GROUP",
    "dmf.choose_hero": "CHECKMARK",
    "dmf.refresh_heroes": "FILE_REFRESH",
    "dmf.scan_bones": "FILE_REFRESH",
    "dmf.compare_split": "SPLIT_VERTICAL",
    "dmf.compare_clear": "FULLSCREEN_EXIT",
    "dmf.retarget": "MOD_ARMATURE",
    "dmf.mint_proof": "CHECKMARK",
    "dmf.verify_proof": "FILE_REFRESH",
    "dmf.build_lods": "MOD_DECIM",
    "dmf.clear_lods": "TRASH",
    "dmf.export_stage": "EXPORT",
    "dmf.compile": "PLAY",
    "dmf.refresh_hierarchy": "FILE_REFRESH",
    "dmf.pick_bone_map": "MOUSE_LMB",
    "dmf.select_hierarchy_bone": "RESTRICT_SELECT_OFF",
    "dmf.hero_hierarchy_rig": "ARMATURE_DATA",
    "dmf.update_old_addon": "FILE_REFRESH",
    "dmf.add_rule": "ADD",
    "dmf.rule_from_row": "DUPLICATE",
    "dmf.apply_rules": "ARROW_LEFTRIGHT",
    "dmf.learn_rules": "FILE_REFRESH",
    "dmf.remove_rule": "REMOVE",
    "dmf.clear_rules": "TRASH",
    "dmf.apply_model_name": "SORTALPHA",
    "dmf.pose_preview": "PLAY",
    "dmf.pose_clear": "LOOP_BACK",
    "dmf.scan_clips": "FILE_REFRESH",
    "dmf.scan_tails": "FILE_REFRESH",
    "dmf.load_tail_option": "ARMATURE_DATA",
    "dmf.preview_tail": "VIEWZOOM",
    "dmf.scan_tail": "FILE_REFRESH",
    "dmf.scan_ik": "FILE_REFRESH",
    "dmf.apply_ik": "CONSTRAINT",
    "dmf.bake_ik": "ACTION",
    "dmf.clear_ik": "X",
    "dmf.blend_tail": "PLAY",
    "dmf.blend_tail_all": "ACTION",
    "dmf.import_clip": "IMPORT",
    "dmf.import_clips": "IMPORT",
    "dmf.cancel_clips": "CANCEL",
    "dmf.prefix_clips": "SORTALPHA",
    "dmf.clear_clips": "TRASH",
    "dmf.preview_clip": "PLAY",
}


def _icon(operator: str) -> str:
    return _GLYPHS.get(operator, "DOT")
