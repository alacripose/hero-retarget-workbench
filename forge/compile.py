"""Invoke CSDK13's resourcecompiler on the staged, unchanged vmdl."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
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


def _source_build_name(addon_name: str) -> str:
    safe = "".join(char if char.isalnum() or char == "_" else "_" for char in addon_name.lower())
    return (safe or "addon")[:40]


def _compiled_paths(build_addon: Path) -> list[Path]:
    if not build_addon.is_dir():
        return []
    return [
        path
        for path in sorted(build_addon.rglob("*"))
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
    """Compile a stage from a disposable CSDK content folder.

    resourcecompiler resolves its content from the SDK's ``content`` directory,
    so the stage has to be visible there for the build. It is copied into a
    uniquely named build addon, compiled, and removed in ``finally``. Only the
    resulting compiled resources are copied back under ``<stage>/compiled``;
    the user's real ``citadel_addons`` folders are not touched.
    """
    if env.resourcecompiler is None or not env.resourcecompiler.is_file():
        raise CompileError("resourcecompiler-missing: choose the CSDK13 root in the addon Setup panel")
    if env.csdk_root is None or env.csdk_gameinfo is None:
        raise CompileError("csdk-incomplete: choose a CSDK13 root with content and game/citadel/gameinfo.gi in Setup")
    source = stage_root / "content" / "citadel_addons" / addon_name
    manifest_path = source / "stage.json"
    if not manifest_path.is_file():
        raise CompileError(f"stage-manifest-missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vmdl_relative = manifest.get("vmdl")
    if not vmdl_relative:
        raise CompileError("stage-manifest-has-no-vmdl")

    content_root = env.csdk_root / "content" / "citadel_addons"
    content_root.mkdir(parents=True, exist_ok=True)
    build_content = Path(
        tempfile.mkdtemp(prefix=f"dmf_build_{_source_build_name(addon_name)}_", dir=content_root)
    )
    build_name = build_content.name
    build_game = env.csdk_root / "game" / "citadel_addons" / build_name
    try:
        shutil.copytree(source, build_content, dirs_exist_ok=True)
        input_relative = Path("citadel_addons") / build_name / vmdl_relative
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
        compiled = _compiled_paths(build_game)
        compiled_root = stage_root / "compiled" / addon_name
        saved: list[Path] = []
        if result.returncode == 0 and compiled:
            if compiled_root.exists():
                shutil.rmtree(compiled_root)
            for path in compiled:
                relative = path.relative_to(build_game)
                target = compiled_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                saved.append(target)
        output = compiled_root / Path(vmdl_relative).with_suffix(".vmdl_c")
        return CompileResult(
            command,
            result.returncode,
            result.stdout,
            result.stderr,
            log_path,
            content_addon=None,
            output=output if output.is_file() else None,
            compiled_files=saved,
            build_addon=None,
        )
    finally:
        # The SDK content entry is a build scratch space. Remove both halves so
        # CSDK is not polluted with uncompiled DMX/vmdl/materials after a build.
        shutil.rmtree(build_content, ignore_errors=True)
        shutil.rmtree(build_game, ignore_errors=True)
