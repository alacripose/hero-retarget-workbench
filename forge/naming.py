"""Names for imported parts: keep the part word, drop a stale rig prefix.

A model ported twice arrives carrying the previous rig's names — ``shiv_body``
when the hero is Shiv, ``thicc_mayu_v3_head`` when the last port was Mayu. The
import renames its own objects from the file it came from, so a new port never
inherits the last one's identity, and the part word (body, head, hair) survives
because that is the word that carries meaning in the export scope.
"""
from __future__ import annotations

import re
from pathlib import Path

_TOKEN = re.compile(r"[A-Za-z0-9]+")
_ILLEGAL = re.compile(r'[\\/:*?"<>|]')
FALLBACK = "model"


def sanitize(name: str) -> str:
    """A Blender-safe ID name: no path characters, no surrounding punctuation."""
    value = _ILLEGAL.sub("_", (name or "").strip())
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._ ")
    if len(value) > 60:
        value = value[:60].rstrip("._ ")
    return value


def model_name(path_stem: str, fallback: str = FALLBACK) -> str:
    """The name a freshly imported model is known by: its own file, not the last one."""
    return sanitize(path_stem) or fallback


def _tokens(name: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in _TOKEN.finditer(name or "")]


def strip_prefix(name: str, prefixes: list[str]) -> str:
    """``shiv_body`` with prefix ``shiv`` gives ``body``.

    Whole leading tokens only: prefix ``thigh`` never eats the front of
    ``thighbone_ik`` (lengths differ) and prefix ``arm`` leaves ``arm_lower_L``'s
    other tokens intact. When nothing is left the name is returned unchanged: a
    part is never renamed to nothing.
    """
    tokens = _tokens(name)
    if not tokens:
        return name
    wanted: list[list[str]] = []
    for prefix in prefixes or []:
        cleaned = sanitize(prefix).lower()
        if not cleaned:
            continue
        parts = [piece for piece in cleaned.replace(".", "_").split("_") if piece]
        if parts:
            wanted.append(parts)
    for parts in sorted(wanted, key=len, reverse=True):
        if len(tokens) <= len(parts):
            continue
        if [token.lower() for token, _start, _end in tokens[: len(parts)]] != parts:
            continue
        rest = name[tokens[len(parts)][1] :]
        if rest.strip("._ -"):
            return rest
    return name


def part_names(names: list[str], prefixes: list[str]) -> dict[str, dict[str, str]]:
    """Old name -> ``{"object": ..., "data": ...}`` for every imported part.

    A stripped name that would collide with another part keeps its original
    spelling, so two parts can never silently merge under one name.
    """
    stripped = {name: strip_prefix(name, prefixes) for name in names}
    counts: dict[str, int] = {}
    for new in stripped.values():
        counts[new.lower()] = counts.get(new.lower(), 0) + 1
    result: dict[str, dict[str, str]] = {}
    for name in names:
        new = stripped[name]
        if counts[new.lower()] > 1 and new != name:
            new = name
        result[name] = {"object": sanitize(new) or name, "data": sanitize(new) or name}
    return result


def collection_name(path: Path | str, fallback: str = FALLBACK) -> str:
    """The import's own collection name, from its own file."""
    stem = Path(path).stem if path else ""
    return f"DMF {model_name(stem, fallback)}"


def rename_plan(
    imported: list[tuple[str, str, str]], prefixes: list[str]
) -> list[dict[str, str]]:
    """Rows of ``(object, armature-or-empty, mesh-data)`` turned into rename targets.

    Armatures are renamed last and get a ``_rig`` suffix so a rig never shares a
    name with the mesh it deforms, which is what makes an outliner unreadable
    after two ports.
    """
    names = [row[0] for row in imported]
    plan = part_names(names, prefixes)
    rows: list[dict[str, str]] = []
    for name, armature, data in imported:
        entry = plan[name]
        rows.append(
            {
                "object": entry["object"],
                "data": entry["data"],
                "kind": "ARMATURE" if armature and armature == name else "MESH",
            }
        )
    return rows
