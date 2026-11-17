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


_MODEL_ROOTS = ("models/heroes_wip", "models/heroes_staging", "models/npc", "models/hideout")
_MODEL_EXCLUDE = (
    "_gun",
    "_weapon",
    "_brk",
    "_gib",
    "_piece",
    "_fx",
    "_arrow",
    "_projectile",
    "_bomb",
    "_bottle",
    "_cuffs",
    "_bola",
    "_grenade",
    "_diorama",
    "_banner",
    "_pipes",
    "_pizza",
    "_statue",
    "_roller",
    "/roller/",
    "_plank",
    "_speaker",
    "_zipline",
    "_gibs",
    "cracked_soul",
    "/piece",
    "/particle/",
)
_NPC_ROOTS = (
    "trooper",
    "boss",
    "neutral",
    "ghost",
    "sewer",
    "midboss",
    "gargoyle",
    "titan",
    "medic",
)


def parse_model_listing(text: str) -> list[str]:
    """Read the compiled model paths from an S2V ``-l -e vmdl_c`` listing."""
    paths = []
    for line in text.splitlines():
        path = line.split(" CRC:", 1)[0].strip().replace("\\", "/")
        if path.lower().endswith(".vmdl_c"):
            paths.append(path)
    return paths


def _is_character_model(path: str, roster_paths: set[str]) -> bool:
    """Whether a listed model is a character rather than a gun, prop or break piece."""
    normalized = path.replace("\\", "/").lower()
    if normalized in roster_paths:
        return True
    stem = Path(normalized).stem
    if any(token in normalized for token in _MODEL_EXCLUDE):
        return False
    parts = Path(normalized).parts
    if "heroes_wip" in parts or "heroes_staging" in parts:
        # A direct hero model (abrams/abrams), a transform/variant folder
        # (werewolf/transform, nano/nano_v2), or a named character variant
        # (familiar_wip, ratking_minion).
        return (
            "transform" in parts
            or any(part.endswith("_v2") or part == "v2" for part in parts)
            or "_wip" in stem
            or "minion" in stem
            or (len(parts) >= 2 and stem == parts[-2])
        )
    if "npc" in parts:
        npc_root = parts[parts.index("npc") + 1] if parts.index("npc") + 1 < len(parts) else ""
        return any(token in npc_root for token in _NPC_ROOTS)
    if "hideout" in parts:
        # Hideout NPCs are full character models -- the Inferno bartender carries the only inferno
        # tail mesh in the game -- and they live outside the hero and npc roots.
        return True
    return False


def _display_variant(value: str) -> str:
    words = value.replace("-", "_").split("_")
    labels = {"wip": "WIP", "v2": "V2", "npc": "NPC", "2": "2"}
    return " ".join(labels.get(word.lower(), word.capitalize()) for word in words if word)


def _variant_suffix(path: str, base_folder: str) -> str:
    relative = path[len(base_folder):].strip("/")
    if not relative:
        return ""
    parent = Path(relative).parent
    stem = Path(relative).stem
    base_name = Path(base_folder).name.lower()
    pieces = [part for part in parent.parts if part.lower() not in ("dmx", "mesh")]
    stem_tail = stem.lower()
    for prefix in (base_name + "_", base_name, "hero_"):
        if stem_tail.startswith(prefix):
            stem_tail = stem_tail[len(prefix):]
            break
    if stem_tail and stem_tail != base_name and stem_tail not in {piece.lower() for piece in pieces}:
        pieces.append(stem_tail)
    label = _display_variant(" ".join(pieces))
    base_label = _display_variant(base_name)
    if label.lower().startswith(base_label.lower() + " "):
        label = label[len(base_label) + 1:]
    return label


def _npc_title(path: str, parts: tuple[str, ...]) -> str:
    index = parts.index("npc")
    folder = parts[index + 1] if index + 1 < len(parts) else "npc"
    folder_title = _display_variant(folder)
    stem_title = _display_variant(Path(path).stem)
    if stem_title.lower() == folder_title.lower() or folder_title.lower().startswith(stem_title.lower()):
        return f"NPC · {folder_title}"
    if stem_title.lower() in {"model", folder_title.lower() + " model"}:
        return f"NPC · {folder_title}"
    if stem_title.lower().startswith(folder_title.lower()):
        return f"NPC · {stem_title}"
    return f"NPC · {folder_title} · {stem_title}"


def augment_roster(roster: list[Hero], model_paths: list[str]) -> list[Hero]:
    """Add the character model variants the hero table does not name.

    Transforms, alternate bodies, minions and NPC models exist in the VPK but
    not as top-level hero entries.  They are still valid retarget targets, so
    the Source page lists them without turning every gun and break piece into a
    selectable hero.
    """
    unique_roster: list[Hero] = []
    roster_seen: set[str] = set()
    for hero in roster:
        key = hero.model_path.replace("\\", "/").lower()
        if key in roster_seen:
            continue
        roster_seen.add(key)
        stem = Path(hero.model_path).stem.lower()
        title = hero.title
        if "wip" in stem and "wip" not in title.lower():
            title = f"{title} · WIP"
        elif (
            stem != title.lower()
            and not stem.startswith(title.lower())
            and not title.lower().startswith(stem)
        ):
            title = f"{title} · {_display_variant(stem)}"
        unique_roster.append(Hero(hero.slug, hero.model_path, title))
    roster = unique_roster
    by_path = {hero.model_path.replace("\\", "/").lower(): hero for hero in roster}
    folders = {str(Path(path).parent).lower(): hero for path, hero in by_path.items()}
    roster_paths = set(by_path)
    found: list[Hero] = []
    seen = set(by_path)
    for raw in model_paths:
        path = raw.replace("\\", "/")
        key = path.lower()
        if key in seen or not _is_character_model(path, roster_paths):
            continue
        seen.add(key)
        directory = str(Path(path).parent).lower()
        base = next(
            (hero for prefix, hero in folders.items() if directory == prefix or directory.startswith(prefix + "/")),
            None,
        )
        if base is not None:
            folder = str(Path(base.model_path).parent)
            suffix = _variant_suffix(path, folder)
            base_title = base.title.split(" · ", 1)[0]
            title = f"{base_title} · {suffix}" if suffix else f"{base_title} · Base"
            slug = f"{base.slug}__{_display_variant(suffix).lower().replace(' ', '_') or 'base'}"
        else:
            parts = Path(path).parts
            if "npc" in parts:
                index = parts.index("npc")
                folder_name = parts[index + 1] if index + 1 < len(parts) else "npc"
                title = _npc_title(path, parts)
                slug = f"npc__{folder_name}__{Path(path).stem}"
            else:
                index = next(
                    (i for i, part in enumerate(parts) if part in ("heroes_wip", "heroes_staging")),
                    0,
                )
                folder_name = parts[index + 1] if index + 1 < len(parts) else Path(path).stem
                suffix = _variant_suffix(path, str(Path(*parts[: index + 2])))
                title = _display_variant(folder_name) + (f" · {suffix}" if suffix else "")
                slug = f"{folder_name}__{_display_variant(suffix).lower().replace(' ', '_') or 'base'}"
        if key in {hero.model_path.lower() for hero in found}:
            continue
        found.append(Hero(slug=f"{slug}__{Path(path).stem}", model_path=path, title=title))
    return sorted([*roster, *found], key=lambda hero: (hero.title.lower(), hero.slug.lower()))


def list_assets(env: Environment, prefix: str, suffix: str) -> list[str]:
    """Every live asset under `prefix` with `suffix`, read through S2V's own listing.

    The model roots are not the whole game: a hero's bartender variant, an NPC's props and a
    component's meshes live outside `models/heroes_*`, and a listing that only walks those roots
    cannot see them.  This asks the pak itself, so "does the game have it" is answered by the game.
    """
    result = _run(env, ["-l", "-f", prefix, "-e", suffix], timeout=300)
    if result.returncode != 0:
        raise LiveError(f"s2v-listing-failed: {result.stderr.strip() or result.stdout.strip()}")
    return [
        line.split(" CRC:", 1)[0].strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.split(" CRC:", 1)[0].strip().lower().endswith(suffix.lower())
    ]


def list_models(env: Environment) -> list[str]:
    """List character model paths from the live VPK, tolerating a failed root."""
    paths: list[str] = []
    for root in _MODEL_ROOTS:
        try:
            result = _run(env, ["-l", "-f", root, "-e", "vmdl_c"], timeout=180)
        except (LiveError, OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            paths.extend(parse_model_listing(result.stdout))
    return paths


def list_all_models(env: Environment) -> list[str]:
    """Every compiled model the live pak carries under `models/`, by S2V's own listing.

    `list_models` walks four character roots so a hero roster stays small. The picker
    needs the other direction: every `.vmdl_c` the pak holds, so a directory filter can
    name a real VPK folder instead of a hand-written category.
    """
    return sorted(set(list_assets(env, "models/", "vmdl_c")))


def model_root(path: str) -> str:
    """The VPK folder a model lives in, two levels under `models/`.

    A model that sits directly in `models/` has no folder of its own, so it belongs
    to `models` rather than to a pseudo-folder named after the file.
    """
    parts = [part for part in str(path).replace("\\", "/").strip("/").split("/") if part]
    folders = parts[:-1]
    if len(folders) >= 2:
        return "/".join(folders[:2])
    return folders[0] if folders else ""


def roster_for_models(paths: list[str], named: list[Hero] | tuple = ()) -> list[Hero]:
    """One picker row per live model, keeping a hero's own title where the table has it."""
    titles = {hero.model_path.lower(): hero.title for hero in named}
    rows: list[Hero] = []
    seen: set[str] = set()
    for path in paths:
        key = path.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        title = titles.get(key)
        if not title:
            stem = Path(path).stem
            folder = Path(path).parent.name
            title = f"{stem} · {folder}" if folder and folder.lower() != stem.lower() else stem
        rows.append(Hero(slug=path, model_path=path, title=title))
    return sorted(rows, key=lambda hero: (hero.title.lower(), hero.model_path.lower()))


def list_heroes(env: Environment) -> list[Hero]:
    """List every playable hero plus its live model variants and NPCs."""
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
        roster = parse_hero_roster(candidates[0].read_text(encoding="utf-8", errors="replace"))
    return augment_roster(roster, list_models(env))


_BODY = re.compile(
    r"(?:^|[_.\- ])(?:body|model|hull)(?:[_.\- ]?(?:lod)?[_.\- ]?\d+)?(?:$|[_.\- ])",
    re.IGNORECASE,
)
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
    head is the larger ``familiar_wip_head5``. Drifter and several WIP heroes
    call their body ``drifter_model``, and Werewolf emits ``werewolf_hull`` as a
    tiny physics hull beside its real model. Recognising ``model`` and ``hull``
    lets the importer repair a body field that points at a head or a clip; the
    size tiebreak still picks the real model over the hull.
    """
    return bool(_BODY.search(Path(path).stem.lower()))


def _body_score(path: Path) -> int:
    name = path.stem.lower()
    score = 100 if looks_like_body(path) else 0
    if any(token in name for token in _NON_BODY):
        score -= 120
    folders = {part.lower() for part in path.parts[:-1]}
    if folders & {"clips", "animation", "anims"}:
        # An animation DMX can be larger than a low-poly body.  It is never the
        # body, even when its stem happens to contain a body-like word.
        score -= 200
    if "lod" not in name:
        score += 10
    return score


def render_mesh_files(vmdl_text: str) -> list[str]:
    """The DMX paths a hero's own vmdl declares in its `RenderMeshList`.

    This is the model's own answer to "which meshes are this hero", and it is the
    only list a body may be chosen from.  Seven is why: its render meshes are
    `outer_costume`, `gun1`, `skeleton2`, `shirt_backfaces3` and `headgear4` -- no
    part is called a body at all -- so a name score over every DMX in the folder
    picked `gigawatt_prisoner_lightning_ball_upper_body.dmx`, an ability clip.
    """
    # The addon already reads this list (`forge/modeldoc.render_mesh_files`), so this is a
    # delegation, not a second parser.  A document-wide `filename = "*.dmx"` scan is what went
    # wrong: the vmdl names 251 DMX paths, animation clips among them, and the body pick chose
    # `gigawatt_prisoner_lightning_ball_upper_body.dmx` -- an ability animation.
    from . import modeldoc

    return [
        row.filename.replace("\\\\", "/")
        for row in modeldoc.render_mesh_files(vmdl_text)
        if row.filename.lower().endswith(".dmx")
    ]


def model_bone_names(vmdl_text: str) -> list[str]:
    """The bone nodes of the model's own built-in `Skeleton` section.

    This is the model's skeleton, not the animation skeleton: a `.vnmskel` is a separate
    document that names a DMX, and the two are not interchangeable.  The `Skeleton`
    section is the hierarchy every render mesh in the model is skinned to, and it is what
    a body has to name when the pick is "which RenderMeshFile is the body".
    """
    marker = re.search(r'_class\s*=\s*"Skeleton"', vmdl_text)
    if marker is None:
        return []
    depth = 0
    opened = False
    end = len(vmdl_text)
    for index in range(marker.end(), len(vmdl_text)):
        character = vmdl_text[index]
        if character == "[":
            depth += 1
            opened = True
        elif character == "]":
            depth -= 1
            if opened and depth == 0:
                end = index
                break
    text = vmdl_text[marker.end() : end]
    names: list[str] = []
    seen: set[str] = set()
    for value in re.findall(r'\bname\s*=\s*"([^"]+)"', text):
        if value in seen:
            continue
        seen.add(value)
        names.append(value)
    return names


def choose_body(
    paths: list[Path] | tuple[Path, ...],
    *,
    render_meshes: list[str] | tuple[str, ...] | None = None,
    model_bones: set[str] | None = None,
    body_meshes: list[str] | tuple[str, ...] | None = None,
) -> Path | None:
    """Choose the body DMX from the meshes the hero's own model renders.

    File size is the wrong signal: a detailed head can be larger than the body.
    When the vmdl's `RenderMeshList` is known, the body must be one of its
    entries -- a pick that is not rendered by the model is refused by name,
    because that is how an ability clip became "the body" on Seven.
    """
    candidates = [Path(path) for path in paths if Path(path).suffix.lower() == ".dmx"]
    if not candidates:
        return None
    if model_bones:
        # The body is a mesh the model renders that is skinned to the model's own `Skeleton`
        # bone nodes.  The document that *is* the skeleton names every one of them and is not
        # a body; a prop or an animation clip names none.
        from .tails import dmx_joint_names

        wanted = {Path(entry).stem.lower() for entry in (render_meshes or ())}

        def _in_body_group(stem: str) -> bool:
            if not body_meshes:
                return True
            return any(stem == mesh.lower() or stem.endswith(f"_{mesh.lower()}") for mesh in body_meshes)

        pool = [
            path
            for path in candidates
            if (not wanted or path.stem.lower() in wanted)
            and "lod" not in path.stem.lower()
            and _in_body_group(path.stem.lower())
        ]
        scored: list[tuple[int, int, Path]] = []
        for path in pool:
            # Every S2V mesh export carries the model's whole joint table, so "names a bone"
            # is the gate and the body is the largest mesh the body group actually shows.
            overlap = len(set(dmx_joint_names(path)) & model_bones)
            if not overlap:
                continue
            scored.append((overlap, path.stat().st_size, path))
        if not scored:
            # A static prop can have a model Skeleton section and meshes that
            # carry no joints.  Choosing the largest declared LOD0 mesh keeps
            # the model importable; the joint check is a preference, not a
            # reason to fail the whole Source-page import.
            fallback = [path for path in pool if "lod" not in path.stem.lower()] or pool
            if not fallback:
                wanted = {Path(entry).stem.lower() for entry in (render_meshes or ())}
                fallback = [
                    path for path in candidates
                    if (not wanted or path.stem.lower() in wanted)
                    and "lod" not in path.stem.lower()
                ] or candidates
            return max(fallback, key=lambda path: path.stat().st_size) if fallback else None
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return scored[0][2]
    declared: list[Path] = []
    if render_meshes:
        wanted = {Path(entry).stem.lower() for entry in render_meshes}
        declared = [path for path in candidates if path.stem.lower() in wanted]
        lod0 = [path for path in declared if "lod" not in path.stem.lower()]
        pool = lod0 or declared
        scored = [path for path in pool if _body_score(path) > 0]
        if scored:
            return max(scored, key=lambda path: (_body_score(path), path.stat().st_size))
        # No part word at all (Seven): the largest LOD0 render mesh is the body.
        return max(pool, key=lambda path: path.stat().st_size)
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


def body_for_hero_folder(vmdl: Path, dmx: list[Path] | None = None) -> Path | None:
    """The hero's body, chosen the only way the model allows (one copy of the rule).

    The vmdl's own `Skeleton` bone nodes decide what a body is, its `BodyGroupList`
    decides which meshes the model shows, and its `RenderMeshList` is the closed set.  A
    caller that re-picks with filenames alone -- the hero import's body repair did -- can
    swap the body for an ability clip, which is how Seven's import opened an animation
    document and reported no armature.
    """
    dmx = dmx if dmx is not None else sorted(vmdl.parent.glob("*.dmx"))
    if not dmx:
        return None
    text = vmdl.read_text(encoding="utf-8", errors="replace")
    bones = set(model_bone_names(text))
    render = render_mesh_files(text)
    group_meshes: list[str] = []
    try:
        from . import modeldoc

        # A model can carry an optional group (Warden's only group is the
        # low-violence cage hand) without a DEFAULT group.  Taking the first
        # group then restricts the body pool to an accessory and leaves zero
        # render meshes.  Only DEFAULT/BASE narrows the body; otherwise the
        # model's RenderMeshList is the pool and size decides the body.
        groups = modeldoc.body_groups(text)
        default = next((group for group in groups if group.name.casefold() == "default"), None)
        if default is not None:
            group_meshes.extend(default.meshes)
    except Exception:
        group_meshes = []
    return choose_body(
        dmx,
        render_meshes=render or None,
        model_bones=bones or None,
        body_meshes=group_meshes or None,
    )


def inventory(root: Path, hero: Hero, *, log: Path | None = None) -> Extraction:
    files = [path for path in root.rglob("*") if path.is_file()]
    vmdls = sorted((path for path in files if path.suffix.lower() == ".vmdl"), key=lambda p: (len(p.parts), str(p).lower()))
    dmx = sorted(path for path in files if path.suffix.lower() == ".dmx")
    gltf = sorted(path for path in files if path.suffix.lower() in (".gltf", ".glb"))
    materials = sorted(path for path in files if path.suffix.lower() == ".vmat")
    body = None
    if vmdls:
        # The Components inventory already reads the model's own RenderMeshList
        # and marks its primary mesh.  Use that same answer here instead of a
        # second body-matching rule; a static prop or an NPC body is valid.
        try:
            from . import components

            rows = components.inventory(root, vmdl=vmdls[0], include_materials=False)
            body = next((row.path for row in rows if getattr(row, "primary", False)), None)
            if body is None and rows:
                body = rows[0].path
        except Exception:
            body = body_for_hero_folder(vmdls[0], dmx)
    # A model is allowed to be a static prop or a rig without a body.  The
    # Source page still extracts it; Import model decides what it can build.
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
