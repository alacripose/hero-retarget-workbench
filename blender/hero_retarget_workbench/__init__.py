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
    "version": (0, 7, 0),
    "blender": (5, 4, 0),
    "location": "View3D > Sidebar > Deadlock; Properties > Scene > Hero Retarget Workbench",
    "description": "Fit and retarget a custom model onto a live Deadlock hero, then install the unchanged S2V vmdl as a CSDK13 addon",
    "category": "Import-Export",
}

# Which surface the page panels went to after register(): "editor" when this
# Blender can register an add-on space type, "properties" otherwise. Probes and
# the panel read this instead of assuming one build's capability.
SURFACE = "unregistered"

from . import (  # noqa: E402
    clipops,
    cloth_ops,
    hierarchy_view,
    jobs,
    operators,
    poseview,
    properties,
    rules,
    ui,
    ui_lists,
    ui_props,
    ui_space,
    weights,
    workbench,
)


def register() -> None:
    global SURFACE
    properties.register()
    hierarchy_view.register()
    workbench.register()
    rules.register()
    poseview.register()
    clipops.register()
    operators.register()
    cloth_ops.register()
    ui_lists.register()
    ui.register()
    ui_space.register_operators()
    # The page surface is the add-on's own editor when this Blender can register
    # one, and the Properties editor tab when it cannot. Same panels either way.
    if ui_space.register():
        SURFACE = "editor"
    else:
        ui_props.register()
        SURFACE = "properties"


def unregister() -> None:
    global SURFACE
    SURFACE = "unregistered"
    ui_props.unregister()
    ui_space.unregister()
    ui_space.unregister_operators()
    ui.unregister()
    ui_lists.unregister()
    cloth_ops.unregister()
    operators.unregister()
    clipops.unregister()
    poseview.unregister()
    rules.unregister()
    workbench.unregister()
    hierarchy_view.unregister()
    weights.unregister()
    jobs.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
