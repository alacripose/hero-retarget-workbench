"""Invoke CSDK13's resourcecompiler on the staged, unchanged vmdl."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .fileio import copy_tree
from .paths import Environment


class CompileError(RuntimeError):
    pass


@dataclass
class CompileResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    log: Path
    content_addon: Path | None = None
    output: Path | None = None
    compiled_files: list[Path] = field(default_factory=list)
    material_files: list[Path] = field(default_factory=list)
    material_errors: list[str] = field(default_factory=list)
    build_addon: Path | None = None
    game_addon: Path | None = None


def _run(env: Environment, command: list[str], log_path: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(env.csdk_root / "content") if env.csdk_root else None,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "$ " + " ".join(command) + "\n\n" + result.stdout + ("\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )
    return result


def compile_vmdl(env: Environment, vmdl: Path, *, log_path: Path, timeout: int = 1800) -> CompileResult:
    """Compile an absolute vmdl path. Prefer compile_stage for a real addon."""
    if env.resourcecompiler is None or not env.resourcecompiler.is_file():
        raise CompileError("resourcecompiler-missing: choose the CSDK13 root in the addon Setup panel")
    if env.csdk_gameinfo is None:
        raise CompileError("csdk-gameinfo-missing: CSDK13 game/citadel/gameinfo.gi was not found")
    if not vmdl.is_file():
        raise CompileError(f"vmdl-missing: {vmdl}")
    # resourcecompiler's -game wants the directory that contains gameinfo.gi,
    # unlike Source 2 Viewer, which wants the gameinfo.gi file itself.
    command = [
        str(env.resourcecompiler),
        "-nop4",
        "-f",
        "-game",
        str(env.csdk_gameinfo.parent),
        "-i",
        str(vmdl.resolve()),
    ]
    result = _run(env, command, log_path, timeout)
    return CompileResult(command, result.returncode, result.stdout, result.stderr, log_path)


def _addon_folder(addon_name: str) -> str:
    """Return the addon folder name, refusing anything that could leave the tree."""
    name = addon_name.strip().replace("\\", "/").strip("/")
    if not name or "/" in name or name in {".", ".."}:
        raise CompileError(f"addon-name-invalid: {addon_name!r}")
    return name


def _compiled_paths(addon_root: Path) -> list[Path]:
    if not addon_root.is_dir():
        return []
    return [
        path
        for path in sorted(addon_root.rglob("*"))
        if path.is_file() and path.name.endswith("_c")
    ]


def stage_content(env: Environment, stage_root: Path, addon_name: str) -> Path:
    """Copy a staged addon into the selected CSDK content tree without compiling.

    The content addon is the editable tree: materials and their source files sit
    there for the user to open in the selected CSDK.  An existing addon is
    merged, so files this stage does not own survive a second update.
    """
    if env.csdk_root is None:
        raise CompileError("csdk-missing: choose the CSDK13 root in the addon Setup panel")
    addon = _addon_folder(addon_name)
    source = Path(stage_root) / "content" / "citadel_addons" / addon
    if not source.is_dir():
        raise CompileError(f"stage-content-missing: {source}")
    content_addon = env.csdk_root / "content" / "citadel_addons" / addon
    if content_addon.resolve() != source.resolve():
        copy_tree(source, content_addon)
    return content_addon


def compile_stage(
    env: Environment,
    stage_root: Path,
    addon_name: str,
    *,
    log_path: Path,
    timeout: int = 1800,
) -> CompileResult:
    """Compile the addon in place inside the CSDK13 tree.

    ``resourcecompiler`` resolves content from the SDK's ``content`` directory,
    so the stage lives at ``<csdk>/content/citadel_addons/<addon>`` and is
    compiled from there. The compiled ``_c`` files stay in
    ``<csdk>/game/citadel_addons/<addon>``: that is the addon folder modeldoc
    opens and the folder a VPK is packed from. Nothing is copied into a
    temporary build folder and nothing is deleted afterwards.

    A stage created outside the CSDK is installed into the content addon first
    (merging, so the addon's other files survive), then compiled from there.
    """
    if env.resourcecompiler is None or not env.resourcecompiler.is_file():
        raise CompileError("resourcecompiler-missing: choose the CSDK13 root in the addon Setup panel")
    if env.csdk_root is None or env.csdk_gameinfo is None:
        raise CompileError("csdk-incomplete: choose a CSDK13 root with content and game/citadel/gameinfo.gi in Setup")
    addon = _addon_folder(addon_name)
    source = stage_root / "content" / "citadel_addons" / addon
    manifest_path = source / "stage.json"
    if not manifest_path.is_file():
        raise CompileError(f"stage-manifest-missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vmdl_relative = manifest.get("vmdl")
    if not vmdl_relative:
        raise CompileError("stage-manifest-has-no-vmdl")

    # A migrated old body keeps the live hero's LOD slots until the addon's
    # Build LODs / Export & stage run.  Refuse to compile that half-ported stage:
    # the VPK would render the old body at distance as the live hero.
    if manifest.get("preserved_model") and manifest.get("new_root") and manifest.get("new_vmdl"):
        if not manifest.get("lods") and manifest.get("target_dmx"):
            from .stage import target_lod_relatives

            live_root = Path(str(manifest["new_root"]))
            live_lods = target_lod_relatives(live_root, str(manifest["target_dmx"]))
            if live_lods:
                raise CompileError(
                    "compile-needs-restaged-lods: the old body still points at the live hero's "
                    f"{len(live_lods)} LOD slots; press Build LODs, then Export & stage before compiling"
                )

    # Merge into the addon the user already has open in CSDK rather than
    # replacing the folder and its unrelated files.
    content_addon = stage_content(env, stage_root, addon)

    input_relative = Path("citadel_addons") / addon / vmdl_relative
    command = [
        str(env.resourcecompiler),
        "-nop4",
        "-f",
        "-game",
        str(env.csdk_gameinfo.parent),
        "-i",
        str(input_relative),
    ]
    result = _run(env, command, log_path, timeout)

    game_addon = env.csdk_root / "game" / "citadel_addons" / addon
    material_errors: list[str] = []
    material_files: list[Path] = []
    if result.returncode == 0:
        target_relative = str(manifest.get("material_target_dir") or "").replace("\\", "/").strip("/")
        material_root = content_addon / target_relative if target_relative else None
        for source in sorted(material_root.glob("*.vmat")) if material_root is not None else []:
            material_relative = source.relative_to(content_addon).as_posix()
            material_input = Path("citadel_addons") / addon / material_relative
            material_command = [
                str(env.resourcecompiler),
                "-nop4",
                "-f",
                "-game",
                str(env.csdk_gameinfo.parent),
                "-i",
                str(material_input),
            ]
            material_result = _run(env, material_command, log_path, timeout)
            material_files.extend(
                path
                for path in _compiled_paths(game_addon)
                if path.name.lower().startswith(source.stem.lower())
            )
            if material_result.returncode:
                material_errors.append(material_relative)

    compiled = _compiled_paths(game_addon) if result.returncode == 0 and not material_errors else []
    output = game_addon / Path(vmdl_relative).with_suffix(".vmdl_c")
    return CompileResult(
        command,
        result.returncode if not material_errors else 1,
        result.stdout,
        result.stderr,
        log_path,
        content_addon=content_addon,
        output=output if output.is_file() and not material_errors else None,
        compiled_files=compiled,
        material_files=sorted(set(material_files)),
        material_errors=material_errors,
        build_addon=None,
        game_addon=game_addon,
    )
