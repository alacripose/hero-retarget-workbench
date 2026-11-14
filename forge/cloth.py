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
    for base in bases:
        key = part_name(base.stem).lower()
        # ``shiv_glasses_lod17`` belongs to ``shiv_glasses2``: the LOD is named after
        # the part, the base carries an index, so both spellings are matched here.
        lods = set(lod_groups.get(key, set()))
        lods.update(lod_groups.get(base.stem.lower(), set()))
        named_part = is_cloth(key) or key.endswith("body")
        if not lods and not named_part:
            # No LOD family and no part word: a clip that happens to sit here.
            continue
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
