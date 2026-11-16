"""The port's release end, inside the addon: model rewrite, compile, VPK, install, launch.

Every step that used to live in `tools/tail_release_pack.py`, `tools/tail_port_build.py` and
`tools/model_skeleton_write.py` is here, because the owner's rule is that a step the addon cannot do
is a refusal.  The VPK writer is Source 2 Viewer -- `--vpk_create` -- not a hand-written container.

The chain, one call each:

    release.write_model(settings)        model vmdl with the armature's own skeleton + tail mesh
    release.compile(settings)            resourcecompiler over the staged CSDK addon
    release.pack(settings, out)          S2V `-i <staging> --vpk_create <out>`
    release.install(settings, pak)       back up the slot, copy the pak in
    release.launch(settings)             start the game

A refusal is raised, never logged and skipped: no model section that disagrees with the skeleton,
no pak without a compiled model and skeleton, no install without a pack receipt.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import bpy

from . import core

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from forge import compile as forge_compile  # noqa: E402
from forge import live, modeldoc  # noqa: E402


class ReleaseError(RuntimeError):
    pass


def _hero_roots(settings) -> tuple[Path, Path]:
    extraction = Path(bpy.path.abspath(settings.extraction_dir))
    body = Path(bpy.path.abspath(settings.body_dmx))
    return extraction, body.parent


def _vmdl(settings) -> Path:
    _, hero = _hero_roots(settings)
    found = sorted(hero.glob("*.vmdl"))
    if not found:
        raise ReleaseError("release-needs-vmdl: the hero folder carries no .vmdl")
    return found[0]


def _armature(settings):
    arm = settings.target_armature
    if arm is None or arm.type != "ARMATURE":
        raise ReleaseError("release-needs-armature: import the hero first")
    return arm


def armature_parents(arm) -> tuple[dict[str, str | None], list[str]]:
    """The armature's own tree, in bone order, as `parents` + `order` for the vmdl writer."""
    parents: dict[str, str | None] = {}
    order: list[str] = []
    for bone in arm.data.bones:
        order.append(bone.name)
        parents[bone.name] = bone.parent.name if bone.parent is not None else None
    return parents, order


def _bone_fields(arm) -> dict[str, list[str]]:
    """`origin`/`angles` lines for bones the vmdl does not carry yet, from the bone's own rest."""
    fields: dict[str, list[str]] = {}
    for bone in arm.data.bones:
        head = bone.head_local
        tail = bone.tail_local
        fields[bone.name] = [
            f"origin = [ {head.x:.6f}, {head.y:.6f}, {head.z:.6f} ]",
            "angles = [ 0.0, 0.0, 0.0 ]",
        ]
        del tail
    return fields


def write_model(settings, *, tail_mesh: Path | None = None, name: str = "") -> dict:
    """Rewrite the hero vmdl's `Skeleton` to the armature, and add the tail mesh if given.

    The client binds meshes and clips through this section, so it must name exactly the bones the
    armature carries, in the armature's order.  A doc that cannot say which bone is which refuses
    in `modeldoc.rewrite_skeleton_bones` rather than shipping a shifted slot.
    """
    arm = _armature(settings)
    source = _vmdl(settings)
    text = source.read_text(encoding="utf-8", errors="replace")
    parents, order = armature_parents(arm)
    if any("tail_" in bone for bone in order) is False:
        raise ReleaseError("release-needs-tail: attach the tail before writing the model")
    rewritten = modeldoc.rewrite_skeleton_bones(text, parents, order, extra_fields=_bone_fields(arm))
    work = Path(core.project_root(settings)) / "artifacts" / "ports" / (name or source.parent.name) / "model"
    work.mkdir(parents=True, exist_ok=True)
    target = work / source.name
    target.write_text(rewritten, encoding="utf-8")
    added = None
    if tail_mesh is not None:
        added = _add_tail_mesh(settings, target, tail_mesh)
    settings.release_model = str(target)
    return {"vmdl": str(target), "bones": len(order), "tail_mesh": added}


def _add_tail_mesh(settings, vmdl: Path, tail_mesh: Path) -> dict:
    extraction, hero = _hero_roots(settings)
    relative = hero.relative_to(extraction).as_posix() + "/dmx/mesh/" + tail_mesh.name
    from forge import migrate

    return migrate.add_component_mesh(
        vmdl,
        mesh_name=tail_mesh.stem,
        dmx_relative=relative,
        bodygroup="DEFAULT",
        choice="BASE",
    )


def stage(settings, skeleton: Path, *, name: str = "") -> dict:
    """Copy the model, its meshes and the compiler skeleton into the CSDK addon folder.

    The addon folder is the compiler's input, so it must hold every relative path the vmdl names:
    a RenderMeshFile whose DMX is absent compiles into a model with a hole.  No material is
    invented; whatever the extraction carries is copied with its relative path preserved.
    """
    extraction, hero = _hero_roots(settings)
    content = core.csdk_addon_folder(settings)
    if content is None:
        raise ReleaseError("release-needs-addon-name: set the addon name in Setup")
    relative = hero.relative_to(extraction)
    root = content / relative
    root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source in sorted(hero.glob("*.dmx")):
        target = root / source.name
        shutil.copyfile(source, target)
        copied.append(target.as_posix())
    for source in sorted(hero.rglob("*.vmat*")) + sorted(hero.rglob("*.vtex*")):
        target = content / source.relative_to(extraction)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(target.as_posix())
    mesh_dir = root / "dmx" / "mesh"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    skeleton_target = mesh_dir / skeleton.name
    shutil.copyfile(skeleton, skeleton_target)
    copied.append(skeleton_target.as_posix())
    model = _vmdl(settings)
    model_target = root / model.name
    rewritten = Path(settings.release_model) if getattr(settings, "release_model", "") else None
    if rewritten is not None and rewritten.is_file():
        shutil.copyfile(rewritten, model_target)
    else:
        shutil.copyfile(model, model_target)
    copied.append(model_target.as_posix())
    manifest = {
        "vmdl": model_target.relative_to(content).as_posix(),
        "skeleton": skeleton_target.relative_to(content).as_posix(),
        "hero": hero.name,
    }
    (content / "stage.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"root": str(root), "model": str(model_target), "skeleton": str(skeleton_target), "copied": copied}


def compile_stage(settings, *, name: str = "") -> dict:
    """Compile the staged CSDK addon with the project's own compiler handoff."""
    env = core.env(settings)
    addon_name = name or settings.addon_name
    if not addon_name:
        raise ReleaseError("release-needs-name: set the addon name before compiling")
    root = core.csdk_addon_folder(settings)
    if root is None:
        raise ReleaseError("release-needs-stage: stage the addon in Setup first")
    if not (root / "stage.json").is_file():
        raise ReleaseError(f"release-nothing-to-compile: {root} carries no stage.json")
    if env.csdk_root is None:
        raise ReleaseError("release-needs-csdk: choose the CSDK13 root in Setup")
    log = Path(core.project_root(settings)) / "logs" / "release" / f"{addon_name}.log"
    result = forge_compile.compile_stage(env, env.csdk_root, addon_name, log_path=log)
    if result.returncode:
        raise ReleaseError(
            f"release-compile-failed: {(result.stderr or result.stdout or '').strip()[-600:]}"
        )
    compiled = core.csdk_addon_root(settings) / "game" / "citadel_addons" / addon_name
    produced = _compiled(compiled)
    if not produced:
        raise ReleaseError(f"release-compiled-nothing: {compiled} holds no _c file")
    return {"root": str(compiled), "files": len(produced), "log": str(log)}


def _compiled(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".vmdl_c", ".vnmskel_c", ".vnmclip_c", ".vmat_c", ".vtex_c"}
    )


def pack(settings, out: Path, *, name: str = "") -> dict:
    """Pack the compiled addon with Source 2 Viewer's own VPK writer."""
    env = core.env(settings)
    addon_name = name or settings.addon_name
    base = core.csdk_addon_root(settings)
    root = base / "game" / "citadel_addons" / addon_name if base is not None else None
    if root is None:
        raise ReleaseError("release-needs-csdk: choose the CSDK13 root in Setup")
    files = _compiled(root)
    if not files:
        raise ReleaseError(f"release-nothing-compiled: {root} carries no compiled resource")
    staging = Path(core.project_root(settings)) / "artifacts" / "pack-staging" / Path(out).stem
    if staging.exists():
        shutil.rmtree(staging)
    for path in files:
        relative = path.relative_to(root)
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if env.s2v is None:
        raise ReleaseError("release-needs-s2v: set the Source 2 Viewer path in Setup")
    command = [str(env.s2v), "-i", str(staging), "--vpk_create", str(out), "-q"]
    result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=1800)
    if result.returncode or not out.is_file():
        raise ReleaseError(
            f"release-vpk-failed: {(result.stderr or result.stdout or '').strip()[-500:]}"
        )
    receipt = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pak": str(out),
        "bytes": out.stat().st_size,
        "files": [path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()],
    }
    receipts = Path(core.project_root(settings)) / "artifacts" / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / f"{out.stem}-pack.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def pak_numbers(directory: Path) -> list[int]:
    """The `pakNN_dir.vpk` numbers in one folder.  Two digits is the whole range (1..99)."""
    numbers: list[int] = []
    for path in Path(directory).glob("pak*_dir.vpk"):
        stem = path.name[3:-8]
        if stem.isdigit() and 1 <= int(stem) <= 99:
            numbers.append(int(stem))
    return sorted(numbers)


def search_paths(game_dir: Path) -> set[str]:
    """The folders `gameinfo.gi` mounts, resolved the way the engine does (relative to `game/`)."""
    info = Path(game_dir) / "gameinfo.gi"
    if not info.is_file():
        return set()
    paths: set[str] = set()
    inside = False
    for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if text.startswith("SearchPaths"):
            inside = True
            continue
        if not inside:
            continue
        if text.startswith("}"):
            break
        if not text or text.startswith("//"):
            continue
        parts = text.split(None, 1)
        if len(parts) != 2 or parts[0] in {"{"}:
            continue
        relative = parts[1].split("//", 1)[0].strip()
        if not relative or "*" in relative:
            continue
        paths.add(os.path.normcase(str((Path(game_dir).parent / relative).resolve())))
    return paths


def slot_ceiling(settings, directory: Path) -> tuple[int, int]:
    """How high a pak number may go in `directory`, and the game's own pak count.

    A pak number may not exceed the number of paks `game/citadel` itself mounts unless its folder
    is one of the game's search paths -- a higher number needs its own extra search path.  The
    addons folder already is a search path (`game\tcitadel/addons` in `gameinfo.gi`), so it can use
    the whole two-digit range; any folder that is not registered stops at the game's own count.
    """
    env = core.env(settings)
    if env.game_dir is None:
        raise ReleaseError("release-needs-game: set the game root in Setup")
    # `env.game_dir` is the `game` root; the paks and `gameinfo.gi` live in `game/citadel`.
    game_dir = Path(env.game_dir)
    citadel = game_dir / "citadel" if (game_dir / "citadel").is_dir() else game_dir
    mounted = max(len(pak_numbers(citadel)), 1)
    registered = os.path.normcase(str(Path(directory).resolve())) in search_paths(citadel)
    return (99 if registered else mounted), mounted


def slot(settings) -> Path:
    """The addon pak the game will load, chosen from the selected game instead of a hardcoded path.

    The game loads addons from `game/citadel/addons` of the install chosen in Setup, not from
    `pak01`.  `release_slot_number` picks a slot when set, otherwise the newest `pakNN_dir.vpk`
    already present is replaced.  A number above the game's own pak count is refused unless the
    folder is a search path, because only a registered folder can mount an extra pak.
    """
    env = core.env(settings)
    if env.vpk is None:
        raise ReleaseError("release-needs-vpk: the live addon slot is not resolved")
    addons = Path(env.vpk).parent / "addons"
    requested = int(getattr(settings, "release_slot_number", 0) or 0)
    if requested and not 1 <= requested <= 99:
        raise ReleaseError(
            f"release-slot-out-of-range: pak numbers are 1..99, not {requested}"
        )
    ceiling, mounted = slot_ceiling(settings, addons)
    if not requested:
        existing = pak_numbers(addons)
        number = existing[-1] if existing else 1
    else:
        number = requested
    if number > ceiling:
        raise ReleaseError(
            f"release-slot-needs-searchpath: pak{number:02d} is above the {mounted} pak(s) "
            f"game/citadel mounts and {addons} is not one of the game's search paths; add it to "
            f"SearchPaths or pick 1..{ceiling}"
        )
    return addons / f"pak{number:02d}_dir.vpk"


def install(settings, pak: Path) -> dict:
    """Replace the addon slot, keeping the previous pak byte for byte beside it."""
    import hashlib

    target = slot(settings)
    backup = target
    if target.is_file():
        # A rolling `prev` backup overwrote the only accepted build (haze_noskel) after two installs.
        # Name the backup after the bytes it holds, so no install can destroy the previous good pak.
        digest = hashlib.sha256(target.read_bytes()).hexdigest()[:8]
        backup = target.with_name(f"{target.stem}.{digest}.vpk")
        if not backup.is_file():
            shutil.copyfile(target, backup)
    shutil.copyfile(pak, target)
    return {"slot": str(target), "backup": str(backup), "bytes": target.stat().st_size}


def launch(settings) -> dict:
    """Start the game the slot belongs to, detached, and record the process id."""
    env = core.env(settings)
    if env.game_root is None:
        raise ReleaseError("release-needs-game: set the game root in Setup")
    root = Path(env.game_root)
    exe = next(
        (candidate for candidate in (root / "bin" / "win64" / "deadlock.exe", root / "game" / "bin" / "win64" / "deadlock.exe") if candidate.is_file()),
        None,
    )
    if exe is None:
        raise ReleaseError(f"release-needs-game: no bin/win64/deadlock.exe under {root}")
    process = subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    return {"pid": process.pid, "exe": str(exe)}
