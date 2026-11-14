"""Find Source 2 IK target bones and suggest the limb bone each one follows.

A Source 2 rig carries target bones outside the pelvis hierarchy (``Ik_Hand_L``,
``Ik_Foot_R``, sometimes ``Ik_Elbow_L``).  The game's IK chains solve the limbs
from those targets; a Blender export only carries the pose, so a clip whose IK
targets are not constrained and baked leaves the limbs in the wrong place.  This
module is the pure half: it recognises the targets and suggests a plausible
destination by name.  It never decides for the user, and it never reads the
opaque S2V vmdl; the names come from the skeleton the user imported.

The S2V 21.1 release keeps the model's IK chains in the decompiled vmdl and
plays AnimGraph 2 IK in its viewer.  That is the source-side support; the
constraint/bake work here is the Blender-side half, matching the community
guide's Copy Location/Copy Rotation + bake steps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[A-Za-z0-9]+")
_SIDES = {"l": "L", "r": "R", "left": "L", "right": "R"}
# The first token of an IK target.  ``thighbone_ik`` is a bone with "ik" in its
# name, not a target, so only the leading token counts.
_TARGET_HEADS = {"ik", "iktarget"}
# Weapon/prop targets follow an object with Child Of, not a bone with Copy
# Location/Rotation, so they are listed but not auto-suggested.
_OBJECT_TARGETS = {"weapon", "prop", "item", "attachment"}
# Limb word -> candidate destination words.  The destination is checked as a
# substring of the joined token name, so ``lower_arm_L`` matches ``lower_arm``.
_LIMBS = {
    "hand": ("hand", "wrist"),
    "wrist": ("wrist", "hand"),
    "foot": ("ankle", "foot"),
    "ankle": ("ankle", "foot"),
    "toe": ("toe", "ball"),
    "elbow": ("lower_arm", "forearm", "elbow"),
    "knee": ("lower_leg", "calf", "shin", "knee"),
    "shoulder": ("clavicle", "shoulder"),
    "hip": ("thigh", "hip"),
}


@dataclass(frozen=True)
class Suggestion:
    """One IK target and the limb bone it most likely follows."""

    bone: str
    target: str
    confidence: str  # exact, name, related, or empty

    @property
    def ready(self) -> bool:
        return bool(self.target)


def tokens(name: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(name or "")]


def side(names: list[str]) -> str:
    for token in reversed(names):
        if token in _SIDES:
            return _SIDES[token]
    return ""


def is_target(name: str) -> bool:
    """True for a leading ``ik``/``iktarget`` token, false for ``thighbone_ik``."""
    words = tokens(name)
    return bool(words) and words[0] in _TARGET_HEADS


def _base(names: list[str]) -> tuple[list[str], str]:
    words = list(names)
    if words and words[0] in _TARGET_HEADS:
        words = words[1:]
    if words and words[0] == "target":
        words = words[1:]
    found_side = side(words)
    words = [word for word in words if word not in _SIDES]
    return words, found_side


def _score(target: str, source: str, base: list[str], found_side: str) -> tuple[int, str]:
    words = tokens(target)
    if not words or target.casefold() == source.casefold():
        return 0, ""
    target_side = side(words)
    if found_side and target_side and target_side != found_side:
        return 0, ""
    joined = "_".join(words)
    if base and words == base + ([found_side.casefold()] if found_side else []):
        return 100, "exact"
    if base and words[-len(base) :] == base:
        return 80, "name"
    if base and base[0] in words:
        return 60, "name"
    for limb in base[:1]:
        for candidate in _LIMBS.get(limb, ()):
            if candidate in joined:
                return 45, "related"
    return 0, ""


def suggest(bone: str, names: list[str]) -> Suggestion:
    """The best destination for one IK target, or an empty suggestion.

    A result is only offered when the names share a limb word or a side.  The
    panel still lets the user type a different bone; nothing is applied here.
    """
    source_words = tokens(bone)
    if not is_target(bone):
        return Suggestion(bone, "", "")
    base, found_side = _base(source_words)
    if not base or base[0] in _OBJECT_TARGETS:
        return Suggestion(bone, "", "")
    best = (0, "", "")
    for candidate in names:
        if candidate == bone or is_target(candidate):
            continue
        score, confidence = _score(candidate, bone, base, found_side)
        if score <= 0:
            continue
        # Prefer the higher score, then the shorter name, then the first name.
        key = (score, -len(candidate))
        if key > (best[0], -len(best[1]) if best[1] else -10**9):
            best = (score, candidate, confidence)
    return Suggestion(bone, best[1], best[2])


def scan(names: list[str]) -> list[Suggestion]:
    """Every IK target in a skeleton, in name order."""
    return [suggest(name, names) for name in sorted(names) if is_target(name)]
