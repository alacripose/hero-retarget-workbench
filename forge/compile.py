"""Invoke CSDK13's resourcecompiler on the staged, unchanged vmdl."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

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

    content_addon = env.csdk_root / "content" / "citadel_addons" / addon
    if content_addon.resolve() != source.resolve():
        if content_addon.exists():
            # Merge into the addon the user already has open in CSDK rather
            # than replacing the folder and its unrelated files.
            shutil.copytree(source, content_addon, dirs_exist_ok=True)
        else:
            shutil.copytree(source, content_addon)

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
    compiled = _compiled_paths(game_addon)
    output = game_addon / Path(vmdl_relative).with_suffix(".vmdl_c")
    return CompileResult(
        command,
        result.returncode,
        result.stdout,
        result.stderr,
        log_path,
        content_addon=content_addon,
        output=output if output.is_file() else None,
        compiled_files=compiled if result.returncode == 0 else [],
        build_addon=None,
        game_addon=game_addon,
    )
