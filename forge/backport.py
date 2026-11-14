"""Port a mod onto an older game build, as an experiment.

Updating a mod means taking the live hero model as the base. Backporting is the
same transplant pointed the other way: the base is the hero model of another
installed client, and the mod keeps its cloth/physics sections and materials.

The older client is not guessed. It must be a CSDK-style install whose
``game/citadel/pak01_dir.vpk`` and ``gameinfo.gi`` exist; the hero model is
extracted from that client with Source 2 Viewer using the model path the mod
already names, so no roster from another build has to be parsed.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import migrate
from .live import LiveError
from .paths import Environment


class BackportError(ValueError):
    pass


@dataclass(frozen=True)
class ClientBuild:
    root: Path
    vpk: Path
    gameinfo: Path


def client_build(root: Path) -> ClientBuild:
    root = Path(root).expanduser().resolve()
    vpk = root / "game" / "citadel" / "pak01_dir.vpk"
    gameinfo = root / "game" / "citadel" / "gameinfo.gi"
    if not vpk.is_file() or not gameinfo.is_file():
        raise BackportError(f"client-is-not-a-game-build: {root}")
    return ClientBuild(root=root, vpk=vpk, gameinfo=gameinfo)


def client_environment(live: Environment, root: Path) -> Environment:
    """A copy of the live environment pointed at the older client's game data."""
    build = client_build(root)
    return Environment(
        game_root=build.root,
        game_dir=build.root / "game",
        vpk=build.vpk,
        gameinfo=build.gameinfo,
        s2v=live.s2v,
        build="backport-target",
        version_date="",
        blender=live.blender,
        csdk_root=live.csdk_root,
        resourcecompiler=live.resourcecompiler,
        csdk_gameinfo=live.csdk_gameinfo,
    )


def extract_client_model(env: Environment, relative: str, destination: Path, *, timeout: int = 900) -> Path:
    """Extract one model path from the client's pak, decompiled to source."""
    if env.s2v is None:
        raise BackportError("source-2-viewer-missing")
    destination = Path(destination).resolve()
    if destination.exists():
        import shutil

        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        str(env.s2v),
        "-i",
        str(env.vpk),
        "--game",
        str(env.gameinfo),
        "-f",
        relative,
        "-o",
        str(destination),
        "-d",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    (destination / "s2v-client.log").write_text(
        "$ " + " ".join(command) + "\n\n" + completed.stdout + ("\n" + completed.stderr if completed.stderr else ""),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise BackportError(f"client-extract-failed: {relative}; see {destination / 's2v-client.log'}")
    candidates = sorted(destination.rglob("*.vmdl"))
    if not candidates:
        raise BackportError(f"client-model-missing: {relative} extracted no vmdl")
    return candidates[0]


def backport_package(
    env: Environment,
    client_root: Path,
    package: Path,
    output: Path,
    addon: str,
    *,
    relative: str,
    old_vmdl: Path | None = None,
    preserve_model: str = "auto",
    preserve_materials: bool = True,
    force: bool = False,
    timeout: int = 1800,
):
    """Transplant a mod onto the older client's hero model.

    The mod's own vmdl relative path is required: it is both the path read from
    the old client and the path the result is written back to.
    """
    client = client_build(client_root)
    if env.s2v is None:
        raise BackportError("source-2-viewer-missing")
    relative = relative.replace("\\", "/").lstrip("/")
    if not relative:
        raise BackportError("client-model-path-required")
    output = Path(output).resolve()
    if output.exists() and not force:
        raise BackportError(f"output-exists: {output}; enable replace to overwrite")
    output.mkdir(parents=True, exist_ok=True)
    old_root = migrate.extract_package(env, Path(package), output / "old-package", timeout=timeout)
    new_root = output / "client-live"
    client_env = client_environment(env, client.root)
    new_vmdl = extract_client_model(client_env, relative, new_root, timeout=timeout)
    if old_vmdl is None:
        old_vmdl = relative
    old_path = Path(old_vmdl)
    if not old_path.is_absolute():
        old_path = old_root / old_path
    if not old_path.is_file():
        raise BackportError(f"old-vmdl-missing: {old_path}")
    result = migrate.migrate_trees(
        old_root=old_root,
        old_vmdl=old_path,
        new_root=new_root,
        new_vmdl=new_vmdl,
        output=output,
        addon=addon,
        vmdl_relative=relative,
        preserve_model=preserve_model,
        preserve_materials=preserve_materials,
        sections=None,
        force=force,
        old_package=Path(package),
    )
    manifest = result.manifest
    if manifest.is_file():
        import json

        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["backport_client"] = str(client.root)
        data["backport_client_vpk"] = str(client.vpk)
        data["experimental"] = True
        manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return result
