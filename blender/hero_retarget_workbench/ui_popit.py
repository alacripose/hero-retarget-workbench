"""The shared surface grammar: what the Popit teaches, translated to Blender.

The Popit reference is one soft card with a bold title, uppercase micro-labels,
glyph-first rows, groups that fold away, and a single accent bubble for the
thing that needs attention. Blender's sidebar has no font sizes, colours or
dashed rules, so this module keeps the parts that survive the medium: the card
and title, the uppercase micro-label, the glyph row, the collapsible group and
the one-line bubble. Blender's own dark theme supplies the colour; nothing here
invents a palette.
"""
from __future__ import annotations

import textwrap

# The Popit names the thing being edited, its state, and the tools that act on
# it; these helpers keep each page to that shape.
def title(layout, name: str, detail: str = "", icon: str = "NONE", alert: bool = False):
    """The card a page opens with: one name, one state, nothing else."""
    box = layout.box()
    head = box.row(align=True)
    head.alert = alert
    head.scale_y = 1.15
    head.label(text=name, icon=icon)
    if detail:
        right = head.row(align=True)
        right.alignment = "RIGHT"
        right.label(text=detail)
    return box


def micro(layout, text: str, icon: str = "NONE") -> None:
    """An uppercase group label, the Popit's PROPERTIES / MOVEMENT line."""
    row = layout.row(align=True)
    row.scale_y = 0.85
    if icon == "NONE":
        row.label(text=text.upper())
    else:
        row.label(text=text.upper(), icon=icon)


def glyphs(layout, buttons, enabled: bool = True, labels: dict | None = None):
    """A row of actions where the icon carries the meaning.

    Three or more fill the row as bare glyphs, the way the Popit lays its tools
    out. One or two get their word as well, because a lone stretched icon in a
    sidebar reads as a missing label rather than as restraint.
    """
    row = layout.row(align=True)
    row.scale_y = 1.3 if len(buttons) > 2 else 1.15
    row.enabled = enabled
    for operator in buttons:
        text = "" if len(buttons) > 2 else (labels or {}).get(operator, "")
        row.operator(operator, text=text, icon=_icon(operator))
    return row


def bubble(layout, text: str, icon: str = "INFO", alert: bool = False, width: int = 30):
    """The one message a page is allowed. Short, and only when it matters."""
    box = layout.box()
    lines = textwrap.wrap(" ".join((text or "").split()), width=width, break_on_hyphens=False) or [""]
    for index, line in enumerate(lines[:2]):
        row = box.row(align=True)
        row.alert = alert
        row.label(text=line, icon=icon if index == 0 else "BLANK1")
    return box


_GLYPHS = {
    "dmf.detect_paths": "FILE_REFRESH",
    "dmf.detect": "FILE_REFRESH",
    "dmf.extract": "EXPORT",
    "dmf.import_hero": "ARMATURE_DATA",
    "dmf.import_custom": "IMPORT",
    "dmf.fit": "TRANSFORM_ORIGINS",
    "dmf.scan_parts": "FILE_REFRESH",
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
    "dmf.update_old_addon": "FILE_REFRESH",
}


def _icon(operator: str) -> str:
    return _GLYPHS.get(operator, "DOT")
