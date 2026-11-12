"""Thin wrapper around Source 2 Viewer and the live game VPK.

This module lists heroes, extracts the model tree, and inventories the files an
extraction produced. It deliberately does not read or rewrite the vmdl: that
file is an opaque artifact produced by Source 2 Viewer and consumed unchanged
by the CSDK13 compiler.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .paths import Environment


class LiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class Hero:
    slug: str
    model_path: str
    title: str


@dataclass
class Extraction:
    hero: Hero
    root: Path
    vmdl: Path | None
    body_dmx: Path | None
    dmx_files: list[Path] = field(default_factory=list)
    gltf_files: list[Path] = field(default_factory=list)
    material_files: list[Path] = field(default_factory=list)
    log: Path | None = None


def _run(env: Environment, args: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    if env.s2v is None:
        raise LiveError("source-2-viewer-missing: set S2V_CLI or install Source2Viewer-CLI")
    if env.vpk is None or env.gameinfo is None:
        raise LiveError("live-game-missing: set DEADLOCK_GAME to the Steam Deadlock folder")
    command = [
        str(env.s2v),
        "-i",
        str(env.vpk),
        "--game",
        str(env.gameinfo),
        *args,
    ]
    return subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout)


def hero_vmdl_path(model_path: str) -> str:
    """Return the logical .vmdl path for a compiled live model path."""
    text = model_path.replace("\\", "/")
    if text.lower().endswith("_c"):
        text = text[:-2]
    return text


def _display_name(value: str) -> str:
    words = value.replace("_", " ").replace("-", " ").split()
    return " ".join(word.capitalize() for word in words)


def parse_hero_roster(text: str) -> list[Hero]:
    """Read every top-level hero entry from Source 2 Viewer's decompiled roster.

    The live game declares hero identity and its model in ``scripts/heroes.vdata``.
    This reads only the top-level hero blocks and two scalar fields. It does not
    read the vmdl or use a general KeyValues reader; the vmdl remains opaque.
    """
    block = re.compile(r"^\thero_([A-Za-z0-9_]+)\s*=\s*$")
    model = re.compile(r'm_strModelName\s*=\s*resource_name:"([^"]+)"')
    search = re.compile(r'm_strHeroSearchName\s*=\s*"#?hero_([^"]+?)(?:_search)?"')
    logo = re.compile(r'm_strLogoImage(?:English|Localized)\s*=\s*panorama:"[^"]*hero_names/([^"/]+?)\.svg"')
    heroes: list[Hero] = []
    current: str | None = None
    model_path: str | None = None
    search_name: str | None = None
    logo_name: str | None = None

    def finish() -> None:
        nonlocal current, model_path, search_name, logo_name
        if current is not None and model_path:
            compiled = model_path if model_path.lower().endswith("_c") else model_path + "_c"
            title_source = logo_name or search_name or Path(model_path).stem
            title = _display_name(title_source.removesuffix("_localized"))
            heroes.append(Hero(current, compiled, title))
        current = None
        model_path = None
        search_name = None
        logo_name = None

    for line in text.splitlines():
        match = block.match(line)
        if match:
            finish()
            current = match.group(1)
            continue
        if current is None:
            continue
        match = model.search(line)
        if match:
            model_path = match.group(1).replace("\\", "/")
        match = search.search(line)
        if match:
            search_name = match.group(1)
        match = logo.search(line)
        if match:
            logo_name = match.group(1)
    finish()
    # hero_base is the shared default, not a selectable hero. Every other
    # top-level hero entry is kept, including disabled and in-development ones.
    return sorted((hero for hero in heroes if hero.slug != "base"), key=lambda hero: (hero.title.lower(), hero.slug.lower()))


def list_heroes(env: Environment) -> list[Hero]:
    """List every hero declared by the live build through Source 2 Viewer."""
    with tempfile.TemporaryDirectory(prefix="dmf-roster-") as temporary:
        root = Path(temporary)
        result = _run(
            env,
            ["--vpk_filepath", "scripts/heroes.vdata_c", "-o", str(root), "-d"],
            timeout=180,
        )
        if result.returncode != 0:
            raise LiveError(f"s2v-roster-failed: {result.stderr.strip() or result.stdout.strip()}")
        candidates = sorted(root.rglob("heroes.vdata"))
        if not candidates:
            raise LiveError("s2v-roster-missing: Source 2 Viewer emitted no scripts/heroes.vdata")
        return parse_hero_roster(candidates[0].read_text(encoding="utf-8", errors="replace"))


def _looks_like_body(path: Path) -> bool:
    name = path.stem.lower()
    return name.endswith("_body") or name == "body" or name.endswith("_body_lod0")


def extract(env: Environment, hero: Hero, destination: Path, *, force: bool = False) -> Extraction:
    """Run S2V's decompile on one live hero into a cache directory.

    The vmdl is whatever S2V emitted. If the CLI emitted no vmdl, this records
    that fact instead of inventing one from the DMX or the model blocks.
    """
    root = destination.resolve()
    if root.exists() and any(root.iterdir()) and not force:
        return inventory(root, hero)
    root.mkdir(parents=True, exist_ok=True)
    log = root / "s2v-extract.log"
    result = _run(
        env,
        ["--vpk_filepath", hero.model_path, "-o", str(root), "-d"],
        timeout=900,
    )
    log.write_text(result.stdout + ("\n" + result.stderr if result.stderr else ""), encoding="utf-8")
    if result.returncode != 0:
        raise LiveError(f"s2v-extract-failed: {hero.model_path}; see {log}")
    return inventory(root, hero, log=log)


def inventory(root: Path, hero: Hero, *, log: Path | None = None) -> Extraction:
    files = [path for path in root.rglob("*") if path.is_file()]
    vmdls = sorted((path for path in files if path.suffix.lower() == ".vmdl"), key=lambda p: (len(p.parts), str(p).lower()))
    dmx = sorted(path for path in files if path.suffix.lower() == ".dmx")
    gltf = sorted(path for path in files if path.suffix.lower() in (".gltf", ".glb"))
    materials = sorted(path for path in files if path.suffix.lower() == ".vmat")
    body = next((path for path in dmx if _looks_like_body(path)), None)
    if body is None and dmx:
        body = max(dmx, key=lambda path: path.stat().st_size)
    return Extraction(
        hero=hero,
        root=root,
        vmdl=vmdls[0] if vmdls else None,
        body_dmx=body,
        dmx_files=dmx,
        gltf_files=gltf,
        material_files=materials,
        log=log,
    )


def extraction_vmdl_candidates(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.vmdl") if path.is_file())


def logical_path(path: Path, root: Path) -> str:
    """Return a stable slash-separated path, or its filename when outside root."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name
