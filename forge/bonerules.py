"""Mapping rules the user writes, plus the one kept from a typed row.

A rule is one line: a source pattern, a target, and what state a row it answers
gets (mapped, extra or ignored). Three pattern forms, chosen by how the pattern
is written rather than by a hidden setting:

``elbow``      a side stem: ``elbow_L`` and ``elbow_R`` both answer it, and the
               source's own side token is written into the target, so
               ``elbow -> arm_lower_L`` also places ``arm_lower_R``.
``Sp_Hi_*``    a prefix: every source name starting with that text.
``^Sp_(.*)_B$``a regular expression when **Regex** is on; groups such as ``\\1``
               can be used in the target.

Nothing here knows a hero skeleton, a joint name or a cloth convention. A rule
only ever proposes a target that already exists in the hero skeleton, only for a
row with no target, and never a target another row already uses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

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

STATES: tuple[str, ...] = ("MAPPED", "EXTRA", "IGNORED")
NUMBER = "#"  # the one numeric run in a series rule's pattern


def tokens(name: str) -> list[str]:
    """The words of a bone name, lowercased, with separators dropped."""
    return [word for word in re.split(r"[_.\-\s]+", (name or "").lower()) if word]


def template(name: str) -> tuple[str, int, int] | None:
    """``Index_01_L`` -> ``("Index_#_L", 1, 2)``: pattern, value, digit width.

    ``None`` when the name carries no number, or more than one, because one
    example can only place one number against one number.
    """
    numbers = re.findall(r"\d+", name or "")
    if len(numbers) != 1:
        return None
    return re.sub(r"\d+", NUMBER, name, count=1), int(numbers[0]), len(numbers[0])


def series(source: str, target: str) -> Rule | None:
    """A number-shifted rule from one example pair, or ``None`` when they differ more.

    ``Index_01_L -> finger_index_0_L`` gives ``Index_#_L -> finger_index_#_L`` with
    a shift of ``-1``: the words line up in the same order, the target may add a
    leading word, and the two numbers differ by a constant. That is what a finger
    chain is, and it is why one typed row answers the rest of the chain without
    the user writing a regular expression.
    """
    src = template(source)
    tgt = template(target)
    if src is None or tgt is None:
        return None
    src_pattern, src_value, _src_width = src
    tgt_pattern, tgt_value, _tgt_width = tgt
    src_tokens = tokens(src_pattern)
    tgt_tokens = tokens(tgt_pattern)
    if not src_tokens or len(tgt_tokens) < len(src_tokens):
        return None
    extra = len(tgt_tokens) - len(src_tokens)
    if tgt_tokens[extra:] != src_tokens:
        return None
    if extra and not all(word.isalpha() for word in tgt_tokens[:extra]):
        return None
    return Rule(
        source=src_pattern,
        target=tgt_pattern,
        delta=tgt_value - src_value,
        origin="learned",
        side_aware=False,
        state="MAPPED",
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
    """One user rule: how to match a source name, and what to do with the row."""

    source: str
    target: str
    regex: bool = False
    side_aware: bool = True
    state: str = "MAPPED"
    origin: str = "user"
    enabled: bool = True
    support: int = 1
    delta: int = 0

    @property
    def kind(self) -> str:
        if self.regex:
            return "regex"
        if NUMBER in self.source:
            return "series"
        if self.source.strip().endswith("*"):
            return "prefix"
        return "side"

    @property
    def key(self) -> tuple[str, str, bool, str, int]:
        return (self.source.lower(), self.target.lower(), self.regex, self.state, self.delta)


@dataclass(frozen=True)
class Suggestion:
    """What one rule proposes for one source row."""

    target: str
    state: str
    rule: Rule
    label: str


def label(rule: Rule) -> str:
    """Short caption for a panel row or a note."""
    kind = rule.kind
    if kind in ("regex", "prefix"):
        return f"{rule.source} → {rule.target}"
    if kind == "series":
        return f"{rule.source} → {rule.target} (number {rule.delta:+d})"
    stem, _side = split_side(rule.target)
    return f"{rule.source}_{{L,R}} → {stem}_{{L,R}}"


def describe(rule: Rule) -> str:
    """One sentence naming what the rule matches, for the panel hint."""
    if rule.regex:
        return "Regex: matched against the whole name; \\1 and friends come from its groups."
    if rule.kind == "series":
        return (
            f"Series: the same words, and the source's number becomes the target's "
            f"number {rule.delta:+d}. # stands for that number."
        )
    if rule.kind == "prefix":
        return "Prefix: matches every source name starting with that text."
    return "Side rule: matches the stem and writes the source's side token into the target."


def learn(mapping: dict[str, str]) -> list[Rule]:
    """The rule a typed row implies: a numbered series first, then a side stem.

    A numbered pair teaches the number shift before anything else, because that is
    the only form that answers a whole chain (a finger or a skirt segment) from one
    row. A pair whose names carry the same side but no numbers teaches a side stem;
    a deliberate cross-side or structurally unrelated pair teaches nothing.
    """
    found: dict[tuple, Rule] = {}
    for source, target in (mapping or {}).items():
        numbered = series(source or "", target or "")
        if numbered is not None:
            previous = found.get(numbered.key)
            found[numbered.key] = (
                numbered
                if previous is None
                else Rule(
                    source=numbered.source,
                    target=numbered.target,
                    delta=numbered.delta,
                    side_aware=numbered.side_aware,
                    state=numbered.state,
                    origin="learned",
                    support=previous.support + 1,
                )
            )
            continue
        source_stem, source_side = split_side(source or "")
        target_stem, target_side = split_side(target or "")
        if not source_stem or not target_stem:
            continue
        if not (source_side and target_side and source_side == target_side):
            continue
        key = (source_stem.lower(), target_stem.lower())
        if key in found:
            previous = found[key]
            found[key] = Rule(
                source=previous.source,
                target=previous.target,
                side_aware=True,
                state=previous.state,
                origin="learned",
                support=previous.support + 1,
            )
            continue
        found[key] = Rule(
            source=source_stem,
            target=target,
            side_aware=True,
            state="MAPPED",
            origin="learned",
            support=1,
        )
    return ordered(list(found.values()))


def ordered(rules: list[Rule]) -> list[Rule]:
    """Regex, then series, then prefixes, then side stems; best-supported first."""
    rank = {"regex": 0, "series": 1, "prefix": 2, "side": 3}
    return sorted(
        rules,
        key=lambda rule: (rank[rule.kind], -rule.support, -len(rule.source), rule.source.lower()),
    )


@lru_cache(maxsize=256)
def _series_pattern(template: str):
    """The pattern a series rule matches with: its ``#`` becomes one number."""
    parts = (template or "").split(NUMBER)
    if len(parts) != 2:
        return None
    return re.compile(re.escape(parts[0]) + r"(\d+)" + re.escape(parts[1]), re.IGNORECASE)


@lru_cache(maxsize=256)
def _compiled(pattern: str):
    """One compiled regex per pattern, or None when the user's pattern is invalid."""
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def _candidate(rule: Rule, source: str) -> str | None:
    """The target name a rule gives this source, before the hero skeleton is checked."""
    if not rule.source:
        return None
    if rule.regex:
        # A scan and a rule fill ask the same pattern about every row, so the
        # pattern is compiled once instead of once per row.
        pattern = _compiled(rule.source)
        if pattern is None or pattern.fullmatch(source) is None:
            return None
        return pattern.sub(rule.target, source, count=1)
    if rule.kind == "series":
        pattern = _series_pattern(rule.source)
        if pattern is None:
            return None
        found = pattern.fullmatch(source)
        if found is None:
            return None
        value = int(found.group(1)) + rule.delta
        if value < 0:
            return None
        return rule.target.replace(NUMBER, str(value), 1)
    if rule.kind == "prefix":
        text = rule.source[:-1]
        if not source.lower().startswith(text.lower()):
            return None
        return rule.target
    stem, side = split_side(source)
    if stem.lower() != rule.source.lower():
        return None
    if rule.side_aware:
        if not side:
            return None
        return set_side(rule.target, side)
    return rule.target


def matches(rule: Rule, source: str) -> bool:
    """Whether this rule answers this source name at all (target ignored)."""
    return _candidate(rule, source) is not None


def remembered(rows: list[dict]) -> dict[str, tuple[str, str, str]]:
    """Rows a re-scan must not throw away: the ones the user decided themselves.

    Each map row carries what the last scan or rule pass wrote into it
    (``scanned`` / ``scanned_state``). A row whose state or target no longer
    matches that is a row the user typed or chose, so a rescan keeps it and the
    rules are not allowed to answer it again. Untouched rows — an unanswered row
    with no target, or one that still holds exactly what was written for it —
    are rebuilt from the rig and the current rules.
    """
    kept: dict[str, tuple[str, str, str]] = {}
    for row in rows or []:
        source = str(row.get("source") or "")
        if not source:
            continue
        state = str(row.get("state") or "")
        target = str(row.get("target") or "")
        unchanged = target == str(row.get("scanned") or "") and state == str(
            row.get("scanned_state") or ""
        )
        decided = bool(target) or state in STATES
        if decided and not unchanged:
            kept[source] = (state, target, str(row.get("note") or ""))
    return kept


def suggest(
    rules: list[Rule],
    sources: list[str],
    targets: list[str],
    existing: dict[str, str] | None = None,
) -> dict[str, Suggestion]:
    """One rule per unanswered source, never sharing a target with another row.

    ``EXTRA`` and ``IGNORED`` rows do not consume a hero bone, so they never take
    a target out of the pool; only mapped rows do.
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
            if rule.state == "MAPPED":
                target = by_lower.get(candidate.lower())
                if target is None:
                    continue
                # A side rule names one hero bone per side, so it must not take a
                # bone another row already holds. A prefix or regex rule is a
                # deliberate many-to-one statement (a whole skirt chain onto one
                # bone), so it is allowed to share.
                if rule.kind == "side":
                    if target.lower() in taken:
                        continue
                    taken.add(target.lower())
            else:
                target = source
            found[source] = Suggestion(
                target=target,
                state=rule.state,
                rule=rule,
                label=label(rule),
            )
            break
    return found
