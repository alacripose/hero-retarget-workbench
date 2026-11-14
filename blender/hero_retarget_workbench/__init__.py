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
    "version": (0, 8, 11),
    "blender": (5, 4, 0),
    "location": "Workbench editor (PR 165087 builds); View3D > Sidebar > Deadlock elsewhere",
    "description": "Fit and retarget a custom model onto a live Deadlock hero, then install the unchanged S2V vmdl as a CSDK13 addon",
    "category": "Import-Export",
}

# Which surface the page panels went to after register(): "editor" when this
# Blender can register an add-on space type, "sidebar" otherwise. Probes and the
# panel read this instead of assuming one build's capability.
SURFACE = "unregistered"
# Empty unless this Blender could register an editor and the registration failed.
EDITOR_ERROR = ""

from . import (  # noqa: E402
    clipops,
    cloth_ops,
    hierarchy_view,
    jobs,
    operators,
    pipeline_ops,
    poseview,
    properties,
    rules,
    ui,
    ui_lists,
    ui_mods,
    ui_props,
    ui_space,
    weights,
    workbench,
)


def _release_stale_classes() -> None:
    """Unregister this addon's classes left behind by an enabled copy.

    Blender's Install re-enables the module in the same process. When an older
    copy is still enabled, its classes are still registered, and the new
    register() dies on ``register_class(...): already registered as a subclass
    'DMF_BoneEntry'`` - the owner's report. Release anything named DMF_ first;
    classes the old module owned can still be unregistered by their RNA class.
    """
    stale = [name for name in dir(bpy.types) if name.startswith("DMF_")]
    for name in stale:
        cls = getattr(bpy.types, name, None)
        if cls is None:
            continue
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, TypeError):
            continue


def register() -> None:
    global SURFACE, EDITOR_ERROR
    _release_stale_classes()
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
    ui_mods.register()
    pipeline_ops.register()
    ui_space.register_operators()
    # The page surface is the add-on's own editor when this Blender can register
    # one. Released builds can only host the sidebar, and the add-on says so:
    # 0.8.0's Properties fallback squeezed the pages into the Scene tab.
    if ui_space.register():
        SURFACE = "editor"
        EDITOR_ERROR = ui_space.EDITOR_ERROR
    else:
        SURFACE = "sidebar"
        EDITOR_ERROR = ui_space.EDITOR_ERROR
    _report_surface()


def _report_surface() -> None:
    """Say which surface this copy got, and why if it did not get the editor.

    The owner kept hitting an editor-less install with no visible reason; the
    answer belongs in the console and in one file under the user config, not
    only on a panel nobody opened yet.
    """
    message = f"DMF surface={SURFACE} error={EDITOR_ERROR or '-'}"
    print(message, flush=True)
    try:
        import json

        directory = Path(bpy.utils.user_resource("CONFIG", path="dmf", create=True))
        report = directory / "surface.json"
        report.write_text(
            json.dumps(
                {
                    "surface": SURFACE,
                    "error": EDITOR_ERROR,
                    "version": ".".join(str(part) for part in bl_info["version"]),
                    "file": __file__,
                    "blender": bpy.app.version_string,
                    "space_registered": "DMF_ST_workbench" in dir(bpy.types),
                    "pages_registered": "DMF_ST_workbench_pages" in dir(bpy.types),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"DMF surface report: {report}", flush=True)
    except Exception as error:
        print(f"DMF surface report failed: {type(error).__name__}: {error}", flush=True)


def unregister() -> None:
    global SURFACE, EDITOR_ERROR
    SURFACE = "unregistered"
    EDITOR_ERROR = ""
    ui_props.unregister()
    ui_space.unregister()
    ui_space.unregister_operators()
    pipeline_ops.unregister()
    ui_mods.unregister()
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
