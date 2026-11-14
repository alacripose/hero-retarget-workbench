"""Match a hero's tail channels to a separate tail armature.

Deadlock hero clips carry the tail bones in the same action as the body.  A
custom model can keep its tail on a second armature; this module decides which
hero tail bones have a same-name or same-numbered partner on that armature.  It
does not read a clip or a vmdl, and it never invents a target: an unmatched row
is ``CHOOSE`` so the owner can name it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r"[A-Za-z]+|\d+")
TAIL_WORDS = ("tail", "ponytail", "braid", "hair")
TAIL_BONE_WORDS = ("tail", "ponytail", "braid")
TAIL_BAD_WORDS = ("target", "socket", "attachment", "constraint", "helper")


@dataclass(frozen=True)
class TailPair:
    source: str
    target: str
    state: str


def _tokens(name: str) -> tuple[str, ...]:
    return tuple(part.lower() for part in _TOKEN.findall(name or ""))


def _normal(name: str) -> str:
    return "".join(_tokens(name))


def is_tail(name: str) -> bool:
    lowered = (name or "").lower()
    return any(word in lowered for word in TAIL_WORDS)


def is_tail_bone(name: str) -> bool:
    """A tail bone, not the weapon target that happens to end in ``_tail``."""
    lowered = (name or "").lower()
    if any(word in lowered for word in TAIL_BAD_WORDS):
        return False
    return any(word in lowered for word in TAIL_BONE_WORDS)


def dmx_bone_names(path: Path | str) -> list[str]:
    """Tail-looking bone names from a binary or text DMX without importing it.

    Source 2 DMX stores its element name table as NUL-separated ASCII before the
    binary payload. Reading those tokens is enough to answer "does this clip
    carry a tail?" even when the file is AG2 and no vnmskel was emitted.
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return []
    if not data.startswith(b"<!-- dmx"):
        return []
    tokens = re.findall(rb"[\x20-\x7e]{2,}", data)
    found: list[str] = []
    seen: set[str] = set()
    for raw in tokens:
        text = raw.decode("ascii", errors="ignore").strip()
        if not text or not is_tail_bone(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(text)
    return found


@dataclass(frozen=True)
class TailChain:
    name: str
    bones: tuple[str, ...]


def chains(names: list[str] | tuple[str, ...]) -> list[TailChain]:
    """Group the tail bone names in one skeleton into displayable chains."""
    groups: dict[tuple[str, ...], list[tuple[int, str]]] = {}
    for name in names or []:
        if not is_tail_bone(name):
            continue
        tokens = _tokens(name)
        if not tokens:
            continue
        index = -1
        base = tokens
        if tokens[-1].isdigit():
            index = int(tokens[-1])
            base = tokens[:-1]
        elif len(tokens) > 1 and tokens[-1] in ("end", "tip", "root", "base"):
            base = tokens[:-1]
        groups.setdefault(base, []).append((index, name))
    found: list[TailChain] = []
    for base, members in groups.items():
        def order(item):
            index, name = item
            tokens = _tokens(name)
            if index >= 0:
                return (1, index, name.lower())
            if tokens and tokens[-1] in ("end", "tip"):
                return (2, 0, name.lower())
            return (0, 0, name.lower())

        ordered = tuple(name for _index, name in sorted(members, key=order))
        found.append(TailChain(name="_".join(base) or "tail", bones=ordered))
    return sorted(found, key=lambda chain: (chain.bones[0].lower(), chain.name.lower()))


def candidates(hero_names: list[str], tail_names: list[str]) -> list[TailPair]:
    """Hero tail channels paired with tail-armature bones, in chain order.

    Exact names win.  A normalized spelling (``Tail_01`` and ``tail01``) wins
    next.  Numbered members with the same base are paired by their number, which
    covers a rig that renamed the root but kept the chain shape.  Everything else
    is left for the owner instead of being guessed from proximity.
    """
    tails = list(tail_names or [])
    by_exact = {name: name for name in tails}
    by_normal: dict[str, str] = {}
    for name in tails:
        by_normal.setdefault(_normal(name), name)
    numbered: dict[tuple[tuple[str, ...], str], str] = {}
    for name in tails:
        tokens = _tokens(name)
        if len(tokens) < 2 or not tokens[-1].isdigit():
            continue
        numbered[(tokens[:-1], tokens[-1])] = name
    rows: list[TailPair] = []
    for source in hero_names or []:
        if not is_tail(source):
            continue
        target = by_exact.get(source) or by_normal.get(_normal(source))
        if target is None:
            tokens = _tokens(source)
            if len(tokens) >= 2 and tokens[-1].isdigit():
                target = numbered.get((tokens[:-1], tokens[-1]))
        rows.append(TailPair(source=source, target=target or "", state="MATCHED" if target else "CHOOSE"))
    return rows


def mapping(rows) -> dict[str, str]:
    return {row.source: row.target for row in rows if row.source and row.target}