"""Bone and vertex-group name matching for retargeting.

The matcher is deliberately conservative. Exact names win, then a declared
alias, then a normalized form. It never guesses a nearest bone; an unmatched
group is reported and left untouched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PREFIXES = (
    "ValveBiped.",
    "ValveBiped_",
    "Bip01_",
    "Bip01 ",
    "mixamorig:",
    "mixamorig.",
    "Armature|",
)


def normalize(name: str) -> str:
    value = name.strip().lower()
    for prefix in _PREFIXES:
        if value.startswith(prefix.lower()):
            value = value[len(prefix) :]
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


@dataclass
class MatchResult:
    mapping: dict[str, str] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)
    collisions: list[tuple[str, list[str]]] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "mapping": dict(sorted(self.mapping.items())),
            "unmatched": sorted(self.unmatched),
            "collisions": self.collisions,
            "aliases": dict(sorted(self.aliases.items())),
        }


def match(source: list[str], target: list[str], *, aliases: dict[str, str] | None = None) -> MatchResult:
    aliases = {key.strip().lower(): value for key, value in (aliases or {}).items()}
    target_by_exact = {name: name for name in target}
    target_by_norm: dict[str, list[str]] = {}
    for name in target:
        target_by_norm.setdefault(normalize(name), []).append(name)

    result = MatchResult(aliases=aliases)
    used: dict[str, list[str]] = {}
    for name in source:
        chosen = None
        if name in target_by_exact:
            chosen = name
        elif name.lower() in aliases and aliases[name.lower()] in target_by_exact:
            chosen = aliases[name.lower()]
            result.aliases[name] = chosen
        else:
            candidates = target_by_norm.get(normalize(name), [])
            if len(candidates) == 1:
                chosen = candidates[0]
        if chosen is None:
            result.unmatched.append(name)
            continue
        result.mapping[name] = chosen
        used.setdefault(chosen, []).append(name)

    result.collisions = [(target_name, sources) for target_name, sources in sorted(used.items()) if len(sources) > 1]
    return result
