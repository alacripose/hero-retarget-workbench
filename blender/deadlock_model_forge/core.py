"""Bridge between Blender settings and the forge core."""
from __future__ import annotations

import sys
from pathlib import Path

import bpy


def _ensure_vendor() -> None:
    vendor = Path(__file__).resolve().parent / "_vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.append(str(vendor))


_ensure_vendor()


def addon_root() -> Path:
    return Path(__file__).resolve().parent


def bundled_core() -> bool:
    return (addon_root() / "forge" / "__init__.py").is_file()


def checkout_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_import_root(root: Path) -> None:
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)


def _import_root(settings) -> Path:
    if bundled_core():
        _ensure_import_root(addon_root())
        return addon_root()
    candidate = Path(settings.project_root).expanduser() if settings.project_root else checkout_root()
    if not (candidate / "forge").is_dir():
        raise RuntimeError(f"Forge core not found at {candidate} (forge-core-missing)")
    _ensure_import_root(candidate)
    return candidate


def workspace_root() -> Path:
    try:
        location = bpy.utils.user_resource("DATAFILES", path="deadlock_model_forge", create=True)
        if location:
            return Path(location)
    except Exception:
        pass
    return Path.home() / "Documents" / "deadlock-model-forge"


def project_root(settings) -> Path:
    if settings.project_root:
        candidate = Path(settings.project_root).expanduser()
    elif bundled_core():
        candidate = workspace_root()
    else:
        candidate = checkout_root()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeError(f"Workspace folder cannot be created at {candidate}: {error}") from error
    return candidate


def core(settings):
    _import_root(settings)
    from forge import compile, live, paths, stage

    return {"compile": compile, "live": live, "paths": paths, "stage": stage}


def env(settings):
    module = core(settings)
    detected = module["paths"].detect()
    if detected.game_root:
        settings.build = f"{detected.build} {detected.version_date}".strip()
    return detected


def fresh_scene(scene_name: str | None = None):
    """Return a scene ID that survives PulseSrcOps' export-time undo step."""
    try:
        return bpy.context.scene
    except Exception:
        pass
    scenes = bpy.data.scenes
    if scene_name:
        found = scenes.get(scene_name)
        if found is not None:
            return found
    return scenes[0] if len(scenes) else None


def set_status(settings, message: str, kind: str = "INFO") -> None:
    # Re-fetch the group from the live scene. PulseSrcOps pushes an undo step
    # while exporting, which can invalidate a PropertyGroup reference held by an
    # operator that is unwinding an error.
    scene = fresh_scene()
    target = scene.dmf if scene is not None else settings
    target.status = message
    target.status_kind = kind


def selected_meshes(context) -> list[bpy.types.Object]:
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def selected_armatures(context) -> list[bpy.types.Object]:
    return [obj for obj in context.selected_objects if obj.type == "ARMATURE"]


def active_or_first_mesh(context) -> bpy.types.Object | None:
    active = context.active_object
    if active and active.type == "MESH":
        return active
    meshes = selected_meshes(context)
    return meshes[0] if meshes else None


def active_or_first_armature(context) -> bpy.types.Object | None:
    active = context.active_object
    if active and active.type == "ARMATURE":
        return active
    arms = selected_armatures(context)
    return arms[0] if arms else None


def select_only(context, objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        context.view_layer.objects.active = objects[0]


def world_bounds(objects: list[bpy.types.Object]) -> tuple[float, float]:
    low = None
    high = None
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ __import__("mathutils").Vector(corner)
            if low is None:
                low = point.copy()
                high = point.copy()
            else:
                for index in range(3):
                    low[index] = min(low[index], point[index])
                    high[index] = max(high[index], point[index])
    if low is None or high is None:
        return 0.0, 0.0
    return low.z, high.z
