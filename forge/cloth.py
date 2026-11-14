"""The hero's separate meshes and its cloth chains, as plain data.

An S2V extraction of a hero does not stop at the body. Shiv's folder carries five
mesh DMXs — ``shiv_body``, ``shiv_hair3``, ``shiv_jacket4``, ``shiv_glasses2`` and
``shiv_gun1`` — each with its own LODs. Importing only the body is why a ported
Shiv had no hair or jacket. This module names those files, and groups the hero
skeleton's bones into the numbered chains a cloth simulation hangs from.

Nothing here reads a vmdl: the mesh list comes from the extraction's own files,
and the chains come from the imported armature. Cloth constraint nodes are a
modeldoc feature and stay in the modeldoc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

LOD = re.compile(r"^(?P<base>.+)_lod\d+$", re.IGNORECASE)
NUMBER = re.compile(r"^(?P<base>.*?)(?P<index>\d+)$")
SIDE = re.compile(r"^(?P<stem>.*?)[_.\- ](?P<side>[LR])$", re.IGNORECASE)

# Words that name a part which hangs, drapes or is simulated. Used for a badge and
# for the panel's default cloth set, never to exclude a part from the import.
CLOTH_WORDS: tuple[str, ...] = (
    "hair",
    "jacket",
    "coat",
    "collar",
    "cape",
    "skirt",
    "robe",
    "cloth",
    "sleeve",
    "scarf",
    "ribbon",
    "tail",
    "tassel",
    "hem",
    "veil",
    "apron",
    "bandana",
    "belt",
    "strap",
)

# Mesh parts that are not simulated but still belong to the hero. The old filter
# only accepted cloth words and ``body``, so a head or glasses mesh could be
# left out of an import even though S2V had emitted it.
PART_WORDS: tuple[str, ...] = (
    "body",
    "head",
    "face",
    "eyes",
    "eyelash",
    "brow",
    "teeth",
    "tongue",
    "ear",
    "horn",
    "glasses",
    "weapon",
    "gun",
    "pillow",
    "balloon",
    "hull",
    "hat",
    "helmet",
    "mask",
    "wings",
    "accessory",
    "armor",
    "boots",
    "gloves",
    "shirt",
    "pants",
    "belt",
    "necklace",
    "bag",
    "pack",
)

# Render variants that share a body group with a canonical part. Importing all of
# them puts three copies of a jacket in the scene; the vmdl chooses between them.
VARIANT_WORDS: tuple[str, ...] = (
    "ui",
    "static_ui",
    "eyes_closed",
    "no_shirt",
    "no_sim",
    "nosim",
    "proxy",
    "bindpose",
    "ref",
)


def _tokens(name: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[^a-z0-9]+", (name or "").lower()) if part)


def _is_variant(name: str) -> bool:
    tokens = _tokens(name)
    return any(word in tokens for word in ("ui", "proxy")) or any(
        word in (name or "").lower() for word in ("eyes_closed", "no_shirt", "no_sim", "nosim", "bindpose")
    )


def _is_body_stem(stem: str) -> bool:
    return bool(re.search(r"(?:^|[_.\- ])body\d*(?:$|[_.\- ])", (stem or "").lower()))


@dataclass(frozen=True)
class MeshFile:
    """One mesh DMX in the extraction, with the LOD files that belong to it."""

    stem: str
    path: Path
    lods: tuple[Path, ...] = ()

    @property
    def part(self) -> str:
        """``shiv_hair3`` -> ``hair``: the hero prefix and any index removed."""
        return part_name(self.stem)

    @property
    def cloth(self) -> bool:
        return is_cloth(self.part)

    @property
    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


@dataclass(frozen=True)
class Chain:
    """A numbered run of bones on one side: a cloth chain or a finger."""

    base: str
    side: str
    bones: tuple[str, ...]

    @property
    def name(self) -> str:
        return f"{self.base}_{self.side}" if self.side else self.base

    @property
    def cloth(self) -> bool:
        return is_cloth(self.base)


def part_name(stem: str) -> str:
    """Strip a trailing index from a file stem: ``shiv_jacket4`` -> ``shiv_jacket``."""
    name = (stem or "").strip()
    match = NUMBER.match(name)
    if match and match.group("base"):
        name = match.group("base").rstrip("_.- ")
    return name


def is_cloth(name: str) -> bool:
    lowered = (name or "").lower()
    return any(word in lowered for word in CLOTH_WORDS)


def mesh_files(folder: Path | str) -> list[MeshFile]:
    """The hero's mesh DMXs in ``folder``, body first.

    A mesh is either the base of a ``_lod<N>`` family, or a name that ends in a
    known part word. Anything else at this level is an animation clip and is not
    a hero part: the import operator still verifies each candidate by importing it
    and keeping the meshes that actually appear.
    """
    root = Path(folder)
    if not root.is_dir():
        return []
    bases: list[Path] = []
    lod_groups: dict[str, set[Path]] = {}
    for path in sorted(root.glob("*.dmx")):
        match = LOD.match(path.stem)
        if match:
            lod_groups.setdefault(match.group("base").lower(), set()).add(path)
            continue
        bases.append(path)
    found: list[MeshFile] = []
    seen_parts: set[str] = set()
    body_present = any(_is_body_stem(base.stem) for base in bases)
    for base in bases:
        key = part_name(base.stem).lower()
        # ``shiv_glasses_lod17`` belongs to ``shiv_glasses2``: the LOD is named after
        # the part, the base carries an index, so both spellings are matched here.
        lods = set(lod_groups.get(key, set()))
        lods.update(lod_groups.get(base.stem.lower(), set()))
        named_part = is_cloth(key) or any(word in key for word in PART_WORDS)
        if not lods and not named_part:
            # No LOD family and no part word: a clip that happens to sit here.
            continue
        if _is_variant(key):
            continue
        if body_present and not is_cloth(key) and not any(
            word in key for word in PART_WORDS if word != "body"
        ) and key.split("_")[-1] not in PART_WORDS:
            # A second body-named base (``familiar_wip_familiar``) duplicates the
            # declared body; the vmdl's render mesh list is the authority for it.
            continue
        if key in seen_parts:
            continue
        seen_parts.add(key)
        found.append(MeshFile(stem=base.stem, path=base, lods=tuple(sorted(lods))))
    return sorted(
        found,
        key=lambda item: (not item.stem.lower().endswith("body"), item.stem.lower()),
    )


def split_chain_name(name: str) -> tuple[str, str, int | None] | None:
    """``jacket_02_L`` -> ``("jacket", "L", 2)``; ``None`` when there is no number."""
    text = (name or "").strip()
    side = ""
    match = SIDE.match(text)
    if match:
        text = match.group("stem")
        side = match.group("side").upper()
    numbered = NUMBER.match(text)
    if not numbered or not numbered.group("base"):
        return None
    base = numbered.group("base").rstrip("_.- ")
    if not base:
        return None
    return base, side, int(numbered.group("index"))


def chains(names: list[str], min_segments: int = 2) -> list[Chain]:
    """Group ``jacket_0_L``, ``jacket_1_L`` … into one chain per base and side."""
    groups: dict[tuple[str, str], dict[int, str]] = {}
    for name in names or []:
        parsed = split_chain_name(name)
        if parsed is None:
            continue
        base, side, index = parsed
        if index is None:
            continue
        groups.setdefault((base, side), {})[index] = name
    found: list[Chain] = []
    for (base, side), members in groups.items():
        if len(members) < max(2, min_segments):
            continue
        found.append(
            Chain(
                base=base,
                side=side,
                bones=tuple(members[index] for index in sorted(members)),
            )
        )
    return sorted(found, key=lambda chain: (chain.base.lower(), chain.side, len(chain.bones)), reverse=False)


def cloth_chains(names: list[str], min_segments: int = 2) -> list[Chain]:
    """Only the chains whose name reads like a hanging part."""
    return [chain for chain in chains(names, min_segments) if chain.cloth]
