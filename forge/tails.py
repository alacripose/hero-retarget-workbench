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

_TOKEN = re.compile(r"[A-Za-z]+|\d+")
TAIL_WORDS = ("tail", "ponytail", "braid", "hair")


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