"""Pattern rules for bone mapping: one row teaches the rest.

A hand-made row ``elbow_L -> arm_lower_L`` also answers ``elbow_R ->
arm_lower_R`` because the rule remembers the target's side token and swaps it to
match the source. A regex rule covers the names that share no side token.

Rules only ever *suggest*: a suggestion is offered for a row that has no target,
the target must already exist in the hero skeleton, and a target another row
already uses is never proposed twice. ``forge.names.match`` still never guesses
a nearest bone, and nothing mapped is overwritten.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Longest first, so ``_left`` is not read as ``_l`` + ``eft``.
SIDE_TOKENS: tuple[tuple[str, str], ...] = (
    ("_left", "L"),
    (".left", "L"),
    ("-left", "L"),
    (" left", "L"),
    ("_right", "R"),
    (".right", "R"),
    ("-right", "R"),
    (" right", "R"),
    ("_l", "L"),
    (".l", "L"),
    ("-l", "L"),
    (" l", "L"),
    ("_r", "R"),
    (".r", "R"),
    ("-r", "R"),
    (" r", "R"),
)


def split_side(name: str) -> tuple[str, str]:
    """``arm_lower_L`` -> ``("arm_lower", "L")``; no side token gives ``""``."""
    lowered = (name or "").lower()
    for token, side in SIDE_TOKENS:
        if lowered.endswith(token) and len(lowered) > len(token):
            return name[: len(name) - len(token)], side
    # Camel case joins the word to the stem: ElbowLeft has no separator at all.
    for word, side in (("left", "L"), ("right", "R")):
        if lowered.endswith(word) and len(name) > len(word):
            before = name[-len(word) - 1]
            if before.islower() or before.isdigit():
                return name[: -len(word)], side
    return name, ""


def set_side(name: str, side: str) -> str:
    """The same name on the other side, keeping its separator and capitalisation."""
    if side not in ("L", "R"):
        raise ValueError(f"side must be L or R, not {side!r}")
    stem, current = split_side(name)
    if not current:
        return name
    tail = name[len(stem) :]
    body = tail.lstrip("_.- ")
    separator = tail[: len(tail) - len(body)]
    word = body.lower()
    if word in ("l", "r"):
        piece = "L" if side == "L" else "R"
        if body.islower():
            piece = piece.lower()
    else:
        piece = "Left" if side == "L" else "Right"
        if body.islower():
            piece = piece.lower()
        elif body.isupper():
            piece = piece.upper()
    return stem + separator + piece


def mirror(name: str) -> str:
    """The opposite-side spelling of a name, or the name itself when it has no side."""
    _, side = split_side(name)
    if side == "L":
        return set_side(name, "R")
    if side == "R":
        return set_side(name, "L")
    return name


@dataclass(frozen=True)
class Rule:
    """One pattern. ``source`` is a stem for a side rule, a regex otherwise."""

    source: str
    target: str
    regex: bool = False
    side_aware: bool = False
    origin: str = "learned"
    enabled: bool = True
    support: int = 1

    @property
    def key(self) -> tuple[str, str, bool]:
        return (self.source.lower(), self.target.lower(), self.regex)


@dataclass(frozen=True)
class Suggestion:
    """A target a rule proposes for one source name, and the rule that did it."""

    target: str
    rule: Rule
    label: str


def label(rule: Rule) -> str:
    """Short rule caption for a panel row or a note."""
    if rule.regex:
        return f"{rule.source} → {rule.target}"
    stem, _side = split_side(rule.target)
    return f"{rule.source}_{{L,R}} → {stem}_{{L,R}}"


def learn(mapping: dict[str, str]) -> list[Rule]:
    """Side rules implied by mapping rows, strongest first.

    Only pairs where both names carry the same side learn a rule: a row that
    crosses sides (``elbow_L -> arm_lower_R``) is a deliberate exception, not a
    pattern, and a row with no side token teaches nothing general.
    """
    counts: dict[tuple[str, str], tuple[str, int]] = {}
    for source, target in (mapping or {}).items():
        source_stem, source_side = split_side(source or "")
        target_stem, target_side = split_side(target or "")
        if not (source_stem and target_stem):
            continue
        if source_side and target_side and source_side == target_side:
            key = (source_stem.lower(), target_stem.lower())
            seen_target, count = counts.get(key, (target, 0))
            counts[key] = (seen_target, count + 1)
        else:
            continue
    rules = [
        Rule(
            source=source,
            target=seen_target,
            side_aware=True,
            origin="learned",
            support=count,
        )
        for (source, _target), (seen_target, count) in counts.items()
    ]
    return ordered(rules)


def ordered(rules: list[Rule]) -> list[Rule]:
    """Regex rules first, then the best-supported and most specific side rules."""
    return sorted(
        rules,
        key=lambda rule: (
            not rule.regex,
            -rule.support,
            -len(rule.source),
            rule.source.lower(),
        ),
    )


def _letters(value: str) -> str:
    return "".join(sorted(re.sub(r"[^a-z0-9]", "", (value or "").lower())))


# Words modelers use for the same joint. A group only becomes a rule when the
# hero skeleton actually has a stem that spells the canonical word, so this
# never invents a target.
SYNONYMS: tuple[tuple[str, ...], ...] = (
    ("elbow", "forearm", "lowerarm", "lower_arm", "lower arm", "arm_lower"),
    ("upperarm", "upper_arm", "upper arm", "shoulder", "deltoid", "arm_upper"),
    ("hand", "wrist", "palm"),
    ("thigh", "upperleg", "upper_leg", "upper leg", "femur", "leg_upper"),
    ("shin", "calf", "lowerleg", "lower_leg", "lower leg", "leg_lower"),
    ("foot", "ankle"),
    ("toe", "ball", "toes"),
    ("spine", "chest", "torso", "abdomen"),
    ("neck", "throat"),
    ("head", "skull"),
    ("pelvis", "hips", "hip"),
    ("clavicle", "collarbone", "shoulderblade"),
    ("tail",),
    ("jaw",),
    ("eye", "eyes"),
)


def builtin(targets: list[str]) -> list[Rule]:
    """Rules that map a common joint word onto a hero bone that exists.

    Only the stems the hero skeleton really has are used, so a hero without a
    tail never produces a tail rule.
    """
    stems: dict[str, str] = {}
    for name in targets or []:
        stem, side = split_side(name)
        if stem:
            stems.setdefault(_letters(stem), name if side else stem)
    rules: list[Rule] = []
    for group in SYNONYMS:
        target_name = None
        for word in group:
            found = stems.get(_letters(word))
            if found:
                target_name = found
                break
        if target_name is None:
            continue
        for word in group:
            if _letters(word) == _letters(split_side(target_name)[0]):
                continue
            rules.append(
                Rule(
                    source=word,
                    target=target_name,
                    side_aware=True,
                    origin="builtin",
                    support=0,
                )
            )
    return ordered(rules)


def _candidate(rule: Rule, source: str) -> str | None:
    if rule.regex:
        try:
            if re.fullmatch(rule.source, source, flags=re.IGNORECASE) is None:
                return None
            return re.sub(rule.source, rule.target, source, count=1, flags=re.IGNORECASE)
        except re.error:
            return None
    stem, side = split_side(source)
    if stem.lower() != rule.source.lower():
        return None
    if rule.side_aware:
        if not side:
            return None
        return set_side(rule.target, side)
    return rule.target


def suggest(
    rules: list[Rule],
    sources: list[str],
    targets: list[str],
    existing: dict[str, str] | None = None,
) -> dict[str, Suggestion]:
    """Targets for the sources that have none, one rule each, no shared target.

    ``existing`` is the current map; a row that already has a target is left
    alone and its target is not offered to another row.
    """
    existing = existing or {}
    by_lower = {name.lower(): name for name in targets or []}
    taken = {value.lower() for value in existing.values() if value}
    found: dict[str, Suggestion] = {}
    for source in sources or []:
        if existing.get(source):
            continue
        for rule in rules:
            if not rule.enabled:
                continue
            candidate = _candidate(rule, source)
            if candidate is None:
                continue
            target = by_lower.get(candidate.lower())
            if target is None or target.lower() in taken:
                continue
            found[source] = Suggestion(target=target, rule=rule, label=label(rule))
            taken.add(target.lower())
            break
    return found
