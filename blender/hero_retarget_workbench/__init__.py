"""Hero Retarget Workbench: Blender 5.4 sidebar addon."""
from __future__ import annotations

import sys
from pathlib import Path

import bpy

_PACKAGE = Path(__file__).resolve().parent
if (_PACKAGE / "forge" / "__init__.py").is_file():
    _CORE_ROOT = _PACKAGE
else:
    _CORE_ROOT = _PACKAGE.parents[1]
if (_CORE_ROOT / "forge").is_dir() and str(_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CORE_ROOT))
if (_PACKAGE / "_vendor").is_dir() and str(_PACKAGE / "_vendor") not in sys.path:
    sys.path.append(str(_PACKAGE / "_vendor"))

bl_info = {
    "name": "Hero Retarget Workbench",
    "author": "ala",
    "version": (0, 2, 4),
    "blender": (5, 4, 0),
    "location": "View3D > Sidebar > Deadlock",
    "description": "Fit and retarget a custom model onto a live Deadlock hero, then stage the unchanged S2V vmdl for CSDK13",
    "category": "Import-Export",
}

from . import jobs, operators, properties, ui, ui_lists, weights, workbench  # noqa: E402


def register() -> None:
    properties.register()
    workbench.register()
    operators.register()
    ui_lists.register()
    ui.register()


def unregister() -> None:
    ui.unregister()
    ui_lists.unregister()
    operators.unregister()
    workbench.unregister()
    weights.unregister()
    jobs.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
