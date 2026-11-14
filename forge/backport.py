"""Port a mod onto an older game build, as an experiment.

Updating a mod means taking the live hero model as the base. Backporting is the
same transplant pointed the other way: the base is the hero model of another
installed client, and the mod keeps its cloth/physics sections and materials.

Older clients are not one shape. A build may be a full install, a bare ``game``
folder, or a ``game/citadel`` folder; its pak may be ``pak01_dir.vpk``, a
single-file ``pak01.vpk``, or several packs plus ``addons`` VPKs. The hero model
may also have moved between ``heroes_staging``, ``heroes_wip`` and ``heroes``
since the mod was made. The build is found from any of those roots, every
mounted VPK is searched, the requested path is used when present, and otherwise
the hero slug picks the model in that build. Nothing is guessed silently: the
manifest records the VPK and the path that were actually used.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import migrate, oldmods
from .live import LiveError
from .paths import Environment


class BackportError(ValueError):
    pass


@dataclass(frozen=True)
class ClientBuild:
    root: Path
    game_dir: Path
    vpks: tuple[Path, ...]
    gameinfo: Path | None

    @property
    def vpk(self) -> Path:
        """The pack to name in a manifest; the model search still covers all."""
        return self.vpks[0]


@dataclass(frozen=True)
class ClientModel:
    relative: str
    vpk: Path
    exact: bool


_CHUNK = re.compile(r"_\d{3}\.vpk$", re.IGNORECASE)


def _game_dir(root: Path) -> Path:
    lower = root.name.lower()
    if lower == "citadel":
        return root
    if lower == "game":
        candidate = root / "citadel"
        return candidate if candidate.is_dir() else root
    candidate = root / "game" / "citadel"
    if candidate.is_dir():
        return candidate
    candidate = root / "game"
    return candidate if candidate.is_dir() else root


def _gameinfo(game_dir: Path) -> Path | None:
    for candidate in (
        game_dir / "gameinfo.gi",
        game_dir.parent / "gameinfo.gi",
        game_dir / "citadel" / "gameinfo.gi",
    ):
        if candidate.is_file():
            return candidate
    return None


def client_build(root: Path) -> ClientBuild:
    """Find the game data and every mounted pack in an older client.

    ``root`` may be the install, its ``game`` folder, or ``game/citadel``.
    Chunk files (``pak01_000.vpk``) are not packs; the ``_dir.vpk`` that names
    them is. ``addons`` packs are included because a build can mount a hero
    replacement there.
    """
    root = Path(root).expanduser().resolve()
    game_dir = _game_dir(root)
    if not game_dir.is_dir():
        raise BackportError(f"client-is-not-a-game-build: {root}")
    found: list[Path] = []
    for folder in (game_dir, game_dir / "addons"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.vpk")):
            if _CHUNK.search(path.name):
                continue
            if path.is_file():
                found.append(path)
    if not found:
        raise BackportError(f"client-has-no-vpks: {root}")
    found.sort(key=lambda path: (0 if path.name.lower().endswith("_dir.vpk") else 1, path.name.lower()))
    return ClientBuild(
        root=root,
        game_dir=game_dir,
        vpks=tuple(found),
        gameinfo=_gameinfo(game_dir),
    )


def client_environment(live: Environment, root: Path) -> Environment:
    """A copy of the live environment pointed at the older client's game data."""
    build = client_build(root)
    return Environment(
        game_root=build.root,
        game_dir=build.game_dir,
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


def _normal(path: str) -> str:
    return path.replace("\\", "/").lstrip("/").lower()


def _model_names(path: str) -> set[str]:
    """The source and compiled spellings of one model."""
    name = _normal(path)
    names = {name}
    if name.endswith(".vmdl"):
        names.add(name + "_c")
    elif name.endswith(".vmdl_c"):
        names.add(name[: -len("_c")])
    return names


def _score(relative: str, slug: str) -> tuple:
    lower = relative.lower()
    folder = 0 if "/heroes_staging/" in lower else 1 if "/heroes_wip/" in lower else 2
    source = 0 if lower.endswith(".vmdl") else 1
    return (folder, source, len(relative), lower)


def find_client_model(build: ClientBuild, relative: str = "", hero: str = "") -> ClientModel:
    """Resolve a model in a build, by requested path first and hero slug second.

    A mod names the path it was built with. Older builds rename folders
    (``doorman_v2``), move a hero between staging and wip, or carry the model in
    another pack. The exact path wins only when it exists in one of this build's
    VPKs; otherwise the hero slug chooses, and the caller records that this was
    a substitution.
    """
    wanted = _normal(relative)
    hero_slug = (hero or "").split(",")[0].strip().lower()
    if not hero_slug and wanted:
        from .oldmods import hero_slugs

        slugs = hero_slugs([wanted])
        hero_slug = slugs[0] if slugs else ""
    entries: list[tuple[str, Path]] = []
    unreadable: list[str] = []
    for vpk in build.vpks:
        try:
            tree = oldmods.read_vpk(vpk)
        except (oldmods.OldModsError, OSError) as error:
            unreadable.append(f"{vpk.name}: {error}")
            continue
        for entry in tree.entries:
            lower = _normal(entry.path)
            if lower.endswith((".vmdl", ".vmdl_c")):
                entries.append((entry.path, vpk))
    if wanted:
        for path, vpk in entries:
            if _normal(path) in _model_names(wanted):
                return ClientModel(relative=path, vpk=vpk, exact=True)
    candidates = []
    if hero_slug:
        for path, vpk in entries:
            lower = _normal(path)
            if f"/{hero_slug}/" not in lower and f"/{hero_slug}_" not in lower:
                continue
            if Path(lower).stem.split(".")[0] != hero_slug and not Path(lower).stem.startswith(
                f"{hero_slug}_"
            ):
                continue
            candidates.append((path, vpk))
    if candidates:
        path, vpk = min(candidates, key=lambda item: _score(item[0], hero_slug))
        return ClientModel(relative=path, vpk=vpk, exact=False)
    detail = f"{len(build.vpks)} vpks"
    if unreadable:
        detail += "; unreadable: " + ", ".join(unreadable)
    raise BackportError(
        f"client-model-missing: {relative or hero_slug or 'no path or hero'}; searched {detail}"
    )


def extract_client_model(
    env: Environment,
    relative: str,
    destination: Path,
    *,
    vpk: Path | None = None,
    timeout: int = 900,
) -> Path:
    """Extract one model path from the client's pak, decompiled to source."""
    if env.s2v is None:
        raise BackportError("source-2-viewer-missing")
    destination = Path(destination).resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        str(env.s2v),
        "-i",
        str(vpk or env.vpk),
    ]
    if env.gameinfo is not None:
        command += ["--game", str(env.gameinfo)]
    command += [
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
    relative: str = "",
    hero: str = "",
    old_vmdl: Path | None = None,
    preserve_model: str = "auto",
    preserve_materials: bool = True,
    force: bool = False,
    timeout: int = 1800,
):
    """Transplant a mod onto the older client's hero model.

    ``relative`` is the path the mod names. When the target build no longer has
    it, ``hero`` (a mod's hero attribution, e.g. ``kelvin, wrecker``) selects the
    hero's model in that build and the manifest records the substitution.
    """
    client = client_build(client_root)
    if env.s2v is None:
        raise BackportError("source-2-viewer-missing")
    match = find_client_model(client, relative, hero)
    output = Path(output).resolve()
    if output.exists() and not force:
        raise BackportError(f"output-exists: {output}; enable replace to overwrite")
    output.mkdir(parents=True, exist_ok=True)
    old_root = migrate.extract_package(env, Path(package), output / "old-package", timeout=timeout)
    new_root = output / "client-live"
    client_env = client_environment(env, client.root)
    new_vmdl = extract_client_model(
        client_env, match.relative, new_root, vpk=match.vpk, timeout=timeout
    )
    old_path = None
    if old_vmdl is not None:
        old_path = Path(old_vmdl)
        if not old_path.is_absolute():
            old_path = old_root / old_path
    if old_path is None or not old_path.is_file():
        # The mod's own source path, then the client path the mod was built
        # from, then the only model in the package. A compiled-only mod has no
        # source path until extraction, so this must not assume one spelling.
        for candidate in (relative, match.relative):
            if not candidate:
                continue
            path = Path(candidate)
            if not path.is_absolute():
                path = old_root / path
            if path.is_file():
                old_path = path
                break
    if old_path is None or not old_path.is_file():
        models = sorted(old_root.rglob("*.vmdl"))
        if len(models) == 1:
            old_path = models[0]
    if old_path is None or not old_path.is_file():
        raise BackportError(f"old-vmdl-missing: {old_root}")
    result = migrate.migrate_trees(
        old_root=old_root,
        old_vmdl=old_path,
        new_root=new_root,
        new_vmdl=new_vmdl,
        output=output,
        addon_name=addon,
        vmdl_relative=match.relative,
        preserve_model=preserve_model,
        preserve_materials=preserve_materials,
        sections=None,
        force=force,
        old_package=Path(package),
    )
    manifest = result.manifest
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["backport_client"] = str(client.root)
        data["backport_client_vpk"] = str(match.vpk)
        data["backport_model"] = match.relative
        data["backport_requested_model"] = relative
        data["backport_exact_model"] = match.exact
        data["backport_gameinfo"] = str(client.gameinfo) if client.gameinfo else ""
        data["experimental"] = True
        manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return result
