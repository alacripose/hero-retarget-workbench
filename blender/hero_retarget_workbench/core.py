"""Bridge between Blender settings and the forge core."""
from __future__ import annotations

import json
import os
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
        location = bpy.utils.user_resource("DATAFILES", path="hero_retarget_workbench", create=True)
        if location:
            return Path(location)
    except Exception:
        pass
    return Path.home() / "Documents" / "hero-retarget-workbench"


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
    if bundled_core():
        # Import the addon's own bundle. A previously enabled addon can leave a
        # top-level ``forge`` module in sys.modules; reusing it would mix the old
        # path contract with this addon's Setup fields.
        from .forge import backport, compile, components, installs, live, migrate, oldmods, paths, provision, stage
    else:
        _import_root(settings)
        from forge import backport, compile, components, installs, live, migrate, oldmods, paths, provision, stage

    return {
        "compile": compile,
        "live": live,
        "migrate": migrate,
        "paths": paths,
        "stage": stage,
        "oldmods": oldmods,
        "installs": installs,
        "provision": provision,
        "backport": backport,
        "components": components,
    }


def detect_environment(settings, module=None):
    """Detect with the user's scene paths ahead of environment and Steam fallbacks.

    Scene paths are Blender paths: ``//tools`` is relative to the saved .blend,
    and a raw Path() would look for a literal ``//`` folder. They are resolved
    here once, so every page and every operator sees the same file.
    """
    module = module or core(settings)
    tool_roots = []
    try:
        workspace = workspace_root()
        tool_roots.extend([workspace / "tools", workspace])
    except Exception:
        pass
    if settings.tools_folder:
        tool_roots.append(Path(bpy.path.abspath(settings.tools_folder)))
    if settings.project_root:
        tool_roots.append(Path(bpy.path.abspath(settings.project_root)) / "tools")
    return module["paths"].detect(
        deadlock_root=bpy.path.abspath(settings.deadlock_root) if settings.deadlock_root else None,
        s2v_cli=bpy.path.abspath(settings.s2v_cli) if settings.s2v_cli else None,
        csdk_root=bpy.path.abspath(settings.csdk_root) if settings.csdk_root else None,
        tool_roots=tool_roots,
    )


def is_csdk_install(path) -> bool:
    """True when the folder is a CSDK13 install, not an older stage folder."""
    root = Path(path)
    return (root / "game" / "bin" / "win64" / "resourcecompiler.exe").is_file() or (
        (root / "content" / "citadel_addons").is_dir() and (root / "game" / "citadel").is_dir()
    )


def csdk_addon_root(settings) -> Path | None:
    """The CSDK13 install that holds this addon.

    A configured Install root wins only when it is a CSDK13 install; a
    leftover stage folder is ignored so the addon cannot land where the
    compiler and modeldoc never look.
    """
    configured = Path(bpy.path.abspath(settings.stage_dir)) if settings.stage_dir else None
    if configured is not None and is_csdk_install(configured):
        return configured
    setup = Path(bpy.path.abspath(settings.csdk_root)) if settings.csdk_root else None
    if setup is not None and is_csdk_install(setup):
        return setup
    return configured


def csdk_addon_folder(settings) -> Path | None:
    """The installed content addon folder, content/citadel_addons/<addon>."""
    root = csdk_addon_root(settings)
    name = (settings.addon_name or "").strip().strip("/\\")
    if root is None or not name or "/" in name or "\\" in name:
        return None
    return root / "content" / "citadel_addons" / name


def bind_staged_source(
    settings,
    installed: str | Path,
    *,
    addon: str = "",
    package: str | Path | None = None,
    kind: str = "addon",
    label: str = "",
    stage_root: str | Path | None = None,
) -> dict[str, str]:
    """Point the Source page at a staged addon instead of the live extraction.

    A staged old mod is a normal content tree: its vmdl, body DMX, compiled
    materials, and recovered source materials all live below one CSDK content
    folder.  Binding those fields is what lets Import, Build LODs, Export &
    stage, and Compile run on it without a separate old-mod path.
    """
    installed = Path(installed).resolve()
    manifest_path = installed / "stage.json"
    manifest: dict = {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}

    relative = str(manifest.get("vmdl") or "").replace("\\", "/").strip("/")
    vmdl = installed / relative if relative else None
    if vmdl is None or not vmdl.is_file():
        candidates = sorted(
            path for path in installed.rglob("*.vmdl") if path.is_file()
        )
        if not candidates:
            raise RuntimeError(f"staged-source-has-no-vmdl: {installed}")
        vmdl = candidates[0]
    try:
        relative = vmdl.relative_to(installed).as_posix()
    except ValueError:
        raise RuntimeError(f"staged-source-vmdl-outside-addon: {vmdl}") from None

    module = core(settings)
    dmx = sorted(path for path in installed.rglob("*.dmx") if path.is_file())
    body = None
    try:
        body = module["live"].body_for_hero_folder(vmdl, dmx) if dmx else None
    except Exception:
        body = None
    if body is None:
        candidates = []
        for entry in manifest.get("model_files") or ():
            candidate = installed / str(entry).replace("\\", "/")
            if candidate.is_file():
                candidates.append(candidate)
        if candidates:
            body = max(candidates, key=lambda path: path.stat().st_size)

    # The staged body is the old model to edit; the live body is the skeleton
    # and body-group target.  Import Hero must load the live body, or the old
    # decompiled skeleton becomes the target and the live matchmaking groups
    # are lost.  The old body goes into the custom-model field instead.
    live_body = None
    live_root = Path(str(manifest.get("new_root") or "")) if manifest.get("new_root") else None
    live_vmdl_relative = str(manifest.get("new_vmdl") or "").replace("\\", "/")
    if live_root is not None and live_vmdl_relative:
        live_vmdl = live_root / live_vmdl_relative
        if live_vmdl.is_file():
            live_dmx = sorted(live_vmdl.parent.glob("*.dmx"))
            try:
                live_body = module["live"].body_for_hero_folder(live_vmdl, live_dmx) if live_dmx else None
            except Exception:
                live_body = None

    settings.extraction_dir = str(installed)
    settings.vmdl = str(vmdl)
    settings.vmdl_relative = relative
    material_target = str(manifest.get("material_target_dir") or "").replace("\\", "/").strip("/")
    material_root = installed / material_target if material_target else installed
    if not material_root.is_dir():
        material_root = installed
    settings.materials_dir = str(material_root)
    settings.custom_materials_dir = str(material_root)
    if stage_root is not None:
        settings.stage_dir = str(stage_root)
    if addon or manifest.get("addon"):
        settings.addon_name = addon or str(manifest.get("addon"))
    if body is not None:
        settings.custom_model = str(body)
        try:
            settings.target_dmx_relative = body.relative_to(installed).as_posix()
        except ValueError:
            settings.target_dmx_relative = body.name
        settings.body_dmx = str(live_body if live_body is not None else body)
    else:
        settings.body_dmx = ""
        settings.custom_model = ""
        settings.target_dmx_relative = ""
    # A staged old model is a new source.  The LOD slots are replaced from the
    # current custom collection, not from the previous source's built LODs.
    settings.generate_lods = True
    settings.lod_count = 0
    settings.live_lods = False
    if package is not None:
        settings.old_vpk = str(package)
        settings.mod_source_package = str(package)
    if addon:
        settings.mod_source_addon = addon
    settings.mod_source_kind = kind or "addon"
    settings.source_origin = label or f"staged {settings.addon_name or installed.name}"
    settings.material_count = int(manifest.get("materials") or 0) + int(
        manifest.get("material_sources") or 0
    )
    return {
        "vmdl": str(vmdl),
        "vmdl_relative": relative,
        "body_dmx": str(body) if body is not None else "",
        "model_file": str(body) if body is not None else "",
        "live_body_dmx": str(live_body) if live_body is not None else "",
    }


def _steam_build(root) -> str:
    """ClientVersion and VersionDate from a tree's own steam.inf, or an empty string."""
    base = Path(root) if root else None
    if base is None:
        return ""
    candidates = [base] if base.name.lower() == "game" else [base / "game", base]
    for game in candidates:
        for info in sorted(game.glob("*/steam.inf")):
            values: dict[str, str] = {}
            try:
                for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        values[key.strip()] = value.strip()
            except OSError:
                continue
            label = f"{values.get('ClientVersion', '')} {values.get('VersionDate', '')}".strip()
            if label:
                return label
    return ""


def _norm(path) -> str:
    return os.path.normcase(os.path.normpath(str(path))) if path else ""


def client_row(settings, path):
    """The detected install row for a selected path, or None."""
    wanted = _norm(path)
    if not wanted:
        return None
    for row in getattr(settings, "clients", ()):
        if _norm(row.path) == wanted:
            return row
    return None


def client_label(settings, path) -> str:
    """The install's own label when it is in the list, else its folder name."""
    row = client_row(settings, path)
    if row is not None and row.label:
        return row.label
    return Path(path).name if path else "not set"


def client_build(settings, path) -> str:
    """The selected install's recorded build, or its own steam.inf when unrecorded."""
    row = client_row(settings, path)
    if row is not None and row.build:
        return row.build
    return _steam_build(path)


def source_build(settings) -> str:
    """The build of the install models are extracted from."""
    return client_build(settings, settings.deadlock_root) or str(getattr(settings, "build", "") or "")


def tools_build(settings) -> str:
    """The build of the install the compiler and packer run from."""
    return client_build(settings, settings.csdk_root)


def marker_rows(settings) -> list[tuple[str, str, str]]:
    """The clients a page's inputs and output follow, as marker rows.

    Extraction and compilation are always named. A backport target is named only
    when it is a different install from the extraction client, because two rows
    repeating the same build is noise rather than information.
    """
    extraction = getattr(settings, "deadlock_root", "")
    compile_root = getattr(settings, "csdk_root", "")
    backport = getattr(settings, "mod_target_client", "")
    rows = []
    for label, icon, path in (
        ("Extract", "IMPORT", extraction),
        ("Compile", "TOOL_SETTINGS", compile_root),
    ):
        if path:
            rows.append((label, f"{client_label(settings, path)} · {client_build(settings, path) or 'no build'}", icon))
        else:
            rows.append((label, "not set", icon))
    if backport and _norm(backport) != _norm(extraction):
        rows.append(
            (
                "Backport",
                f"{client_label(settings, backport)} · {client_build(settings, backport) or 'no build'}",
                "LOOP_BACK",
            )
        )
    return rows


def env(settings):
    detected = detect_environment(settings)
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
