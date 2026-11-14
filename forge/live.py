"""Thin wrapper around Source 2 Viewer and the live game VPK.

This module lists heroes, extracts the model tree, and inventories the files an
extraction produced. It deliberately does not read or rewrite the vmdl: that
file is an opaque artifact produced by Source 2 Viewer and consumed unchanged
by the CSDK13 compiler.
"""
from __future__ import annotations

import json
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
        raise LiveError("source-2-viewer-missing: choose the Source 2 Viewer CLI in the addon Setup panel")
    if env.vpk is None or env.gameinfo is None:
        raise LiveError("live-game-missing: choose the Steam Deadlock folder in the addon Setup panel")
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


_BODY = re.compile(r"(?:^|[_.\- ])body(?:[_.\- ]?(?:lod)?[_.\- ]?\d+)?(?:$|[_.\- ])", re.IGNORECASE)
_NON_BODY = (
    "head",
    "hair",
    "clothes",
    "clothing",
    "jacket",
    "coat",
    "glasses",
    "weapon",
    "gun",
    "pillow",
    "balloon",
    "cloth_proxy",
    "hull",
    "bindpose",
    "ref",
    "eyes",
    "ear",
    "hat",
    "helmet",
    "mask",
    "tail",
    "wings",
    "accessory",
    "skirt",
    "cape",
    "boots",
    "gloves",
)


def looks_like_body(path: Path | str) -> bool:
    """Whether a DMX name declares the body, including a numbered body variant.

    S2V does not emit one naming scheme. ``shiv_body`` and ``haze_body_lod0``
    are obvious, but Familiar's body is ``familiar_wip_8inf_body8`` and its
    head is the larger ``familiar_wip_head5``. Treating ``body8`` as a body and
    ``head5`` as a part is what stops the importer opening a head as the hero.
    """
    return bool(_BODY.search(Path(path).stem.lower()))


def _body_score(path: Path) -> int:
    name = path.stem.lower()
    score = 100 if looks_like_body(path) else 0
    if any(token in name for token in _NON_BODY):
        score -= 120
    if "lod" not in name:
        score += 10
    return score


def choose_body(paths: list[Path] | tuple[Path, ...]) -> Path | None:
    """Choose the body DMX from an extraction by name, not by file size.

    File size is the wrong signal: a detailed head can be larger than the body.
    Prefer a declared body token, ignore known part words, then use the largest
    remaining file only as a last resort.
    """
    candidates = [Path(path) for path in paths if Path(path).suffix.lower() == ".dmx"]
    if not candidates:
        return None
    strong = [path for path in candidates if _body_score(path) >= 100]
    if strong:
        return max(strong, key=lambda path: (_body_score(path), path.stat().st_size))
    fallback = [path for path in candidates if _body_score(path) > 0]
    if fallback:
        return max(fallback, key=lambda path: path.stat().st_size)
    return max(candidates, key=lambda path: path.stat().st_size)


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
    body = choose_body(dmx)
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


def tail_skeleton_files(root: Path) -> list[Path]:
    """Skeleton DMXs from the live-game skeleton cache, not mesh or clip DMX."""
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*.dmx")
        if path.is_file() and ("_skel" in path.stem.lower() or "skeleton" in path.stem.lower())
    )


def tail_skeleton_cache_key(env: Environment) -> dict:
    return {"vpk": str(env.vpk), "mtime": env.vpk.stat().st_mtime if env.vpk else 0}


def tail_skeleton_cache_fresh(env: Environment, root: Path) -> bool:
    stamp = root / "s2v-tail-skeletons.json"
    try:
        return stamp.is_file() and json.loads(stamp.read_text(encoding="utf-8")) == tail_skeleton_cache_key(env)
    except (OSError, json.JSONDecodeError):
        return False


def extract_tail_skeletons(
    env: Environment,
    destination: Path,
    *,
    force: bool = False,
    timeout: int = 900,
) -> list[Path]:
    """Decompile every live hero skeleton into a small, reusable cache.

    A full hero extraction carries hundreds of clips.  The tail scanner only
    needs bone names and rest positions, so this asks S2V for ``vnmskel_c`` under
    ``models/heroes_`` instead of decompiling every hero model tree.  The cache
    is keyed by the VPK mtime so a game patch refreshes it.
    """
    root = destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = root / "s2v-tail-skeletons.json"
    key = tail_skeleton_cache_key(env)
    try:
        if not force and stamp.is_file() and json.loads(stamp.read_text(encoding="utf-8")) == key:
            cached = tail_skeleton_files(root)
            if cached:
                return cached
    except (OSError, json.JSONDecodeError):
        pass
    log = root / "s2v-tail-skeletons.log"
    result = _run(
        env,
        ["-o", str(root), "-d", "-q", "-f", "models/heroes_", "-e", "vnmskel_c"],
        timeout=timeout,
    )
    log.write_text(result.stdout + ("\n" + result.stderr if result.stderr else ""), encoding="utf-8")
    if result.returncode != 0:
        raise LiveError(f"s2v-tail-skeletons-failed: see {log}")
    files = tail_skeleton_files(root)
    if not files:
        raise LiveError(f"s2v-tail-skeletons-empty: see {log}")
    stamp.write_text(json.dumps(key, indent=2), encoding="utf-8")
    return files


def logical_path(path: Path, root: Path) -> str:
    """Return a stable slash-separated path, or its filename when outside root."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name
