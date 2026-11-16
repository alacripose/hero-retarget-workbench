"""Resolve one port's hero files from its extraction, for any hero.

Every tail tool used to carry its own ``SHIV = ... / "shiv"`` and
``WEREWOLF = ... / "werewolf"`` constants, so the whole pipeline could only ever
run against those two heroes and a port of any other hero had to be hand-carved
again.  This module is the one place that answers the questions those constants
were standing in for:

    root = hero_root(extraction)            # .../models/heroes_staging/<hero>
    body = body_dmx(root)                   # .../<hero>_body.dmx
    skel = game_skeleton_dmx(extraction)    # .../dmx/mesh/<hero>_skel.dmx
    clips = clips_dir(root)                 # .../clips

Hero names come from the extraction itself (an S2V tree carries
``<hero>.vmdl``), never from a list in this repository.
"""
from __future__ import annotations

from pathlib import Path


class PortTargetError(RuntimeError):
    """An extraction does not describe a port the way the tools expect."""


def _candidates(extraction: Path) -> list[Path]:
    return sorted(path for path in extraction.rglob("*.vmdl") if path.is_file())


def hero_root(extraction: str | Path, hero: str = "") -> Path:
    """The folder holding one hero's model, skeleton source and clips."""
    extraction = Path(extraction)
    if not extraction.is_dir():
        raise PortTargetError(f"port-extraction-missing: {extraction}")
    vmdls = _candidates(extraction)
    if hero:
        matches = [path for path in vmdls if path.stem.lower() == hero.lower()]
        if not matches:
            matches = [path for path in vmdls if hero.lower() in str(path).lower()]
        if not matches:
            raise PortTargetError(f"port-hero-missing: {hero} in {extraction}")
        return matches[0].parent
    if not vmdls:
        raise PortTargetError(f"port-vmdl-missing: {extraction} has no .vmdl")
    # A transform/variant sub-folder (werewolf/transform) is not the hero's own
    # body folder; prefer the shallowest model, which is the one S2V writes for
    # the hero itself.
    return min(vmdls, key=lambda path: (len(path.relative_to(extraction).parts), str(path))).parent


def body_dmx(root: str | Path) -> Path:
    """The hero's own body mesh DMX."""
    root = Path(root)
    for pattern in ("*body*.dmx", "*_model.dmx"):
        preferred = sorted(root.glob(pattern))
        if preferred:
            return preferred[0]
    # A hero folder also holds per-aim-pose and ability meshes; the body is the
    # largest DMX in it, and an alphabetical pick lands on a clip (measured:
    # tengu_v2/tengu_ability_falling_grace_impact.dmx instead of tengu_tengu_v2.dmx).
    loose = [path for path in root.glob("*.dmx") if "lod" not in path.stem.lower()]
    if not loose:
        raise PortTargetError(f"port-body-missing: {root}")
    return max(loose, key=lambda path: path.stat().st_size)


def game_skeleton_dmx(extraction: str | Path) -> Path:
    """The skeleton DMX the hero's animation skeleton document points at."""
    extraction = Path(extraction)
    named = sorted(extraction.rglob("*_skel.dmx"))
    if named:
        return named[0]
    documents = sorted(extraction.rglob("*.vnmskel"))
    for document in documents:
        text = document.read_text(encoding="utf-8", errors="replace")
        marker = 'm_sourceFilename = "'
        if marker not in text:
            continue
        relative = text.split(marker, 1)[1].split('"', 1)[0]
        candidate = extraction / relative
        if candidate.is_file():
            return candidate
        for found in extraction.rglob(Path(relative).name):
            return found
    raise PortTargetError(f"port-skeleton-missing: {extraction}")


def clips_dir(root: str | Path) -> Path:
    root = Path(root)
    folder = root / "clips"
    if not folder.is_dir():
        raise PortTargetError(f"port-clips-missing: {folder}")
    return folder


def clip_labels(root: str | Path) -> list[str]:
    """Editable clip labels, with the document suffix removed.

    S2V names a decompiled clip after the animation inside it and keeps the
    `+non_additive` suffix on variants, so `.vnmclip` stems are not the label the
    addon pairs on.
    """
    folder = clips_dir(root)
    labels = {path.stem.split(".vnmclip")[0] for path in folder.glob("*.dmx")}
    return sorted(labels)


def describe(extraction: str | Path, hero: str = "") -> dict:
    """Everything a tool needs to name, in one dict."""
    root = hero_root(extraction, hero)
    return {
        "hero": root.name,
        "hero_root": str(root),
        "body_dmx": str(body_dmx(root)),
        "game_skeleton": str(game_skeleton_dmx(extraction)),
        "clips": str(clips_dir(root)),
        "clip_labels": clip_labels(root)[:400],
    }
