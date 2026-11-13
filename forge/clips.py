"""The animation clips an S2V extraction carries, and which of them are editable here.

A Deadlock animation normally arrives as a pair: a ``.dmx`` Blender can edit and
the ``.vnmclip`` the game loads. ``.vnmclip`` is opaque to this project — this
tree decodes no compiled game data at all — so it is listed and paired, never
opened. The ``.dmx`` is what imports, and an import that leaves the ``.vnmclip``
beside it alone is honest about which half changed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Longest first so ``.vnmclip`` is not read as an unknown ``.c``.
KINDS: tuple[tuple[str, str], ...] = (
    (".vnmclip", "vnmclip"),
    (".vnmskel", "vnmskel"),
    (".vnmgraph", "vnmgraph"),
    (".dmx", "dmx"),
)


@dataclass(frozen=True)
class Clip:
    """One animation file: what it is, whether it is compiled, and how big."""

    name: str
    path: Path
    kind: str
    compiled: bool
    size: int

    @property
    def editable(self) -> bool:
        return self.kind == "dmx" and not self.compiled

    @property
    def label(self) -> str:
        """``walk_lower_L`` for both ``walk_lower_L.dmx`` and ``walk_lower_L.vnmclip_c``."""
        if self.compiled:
            return self.path.stem.rsplit("_c", 1)[0]
        return self.path.stem


def classify(path: Path) -> tuple[str, bool] | None:
    """``(kind, compiled)`` for a clip file, or ``None`` when it is not one."""
    name = Path(path).name.lower()
    compiled = name.endswith("_c")
    if compiled:
        name = name[: -len("_c")]
    for suffix, kind in KINDS:
        if name.endswith(suffix):
            return (kind, compiled)
    return None


def scan(folder: Path | str, recursive: bool = True) -> list[Clip]:
    """Every clip under ``folder``, sorted by label then kind.

    A missing folder is an empty list, not an exception: the panel says the
    folder has no clips, which is the difference between "not scanned" and
    "scanned and empty".
    """
    root = Path(folder)
    if not root.is_dir():
        return []
    rows: list[Clip] = []
    if recursive:
        walker = os.walk(root)
        for base, dirs, files in walker:
            dirs.sort()
            for name in sorted(files):
                path = Path(base) / name
                found = classify(path)
                if found is None:
                    continue
                kind, compiled = found
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                rows.append(Clip(name=path.name, path=path, kind=kind, compiled=compiled, size=size))
    else:
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            found = classify(path)
            if found is None:
                continue
            kind, compiled = found
            rows.append(
                Clip(name=path.name, path=path, kind=kind, compiled=compiled, size=path.stat().st_size)
            )
    return sorted(rows, key=lambda row: (row.label.lower(), row.kind, str(row.path)))


def summary(rows: list[Clip]) -> dict[str, int]:
    """Counts the panel prints, including how many pairs are complete."""
    stems: dict[str, set[str]] = {}
    for row in rows:
        key = "dmx_compiled" if (row.kind == "dmx" and row.compiled) else row.kind
        stems.setdefault(row.label, set()).add(key)
    return {
        "total": len(rows),
        "dmx": sum(1 for row in rows if row.kind == "dmx"),
        "vnmclip": sum(1 for row in rows if row.kind == "vnmclip"),
        "compiled": sum(1 for row in rows if row.compiled),
        "editable": sum(1 for row in rows if row.editable),
        "paired": sum(1 for kinds in stems.values() if "dmx" in kinds and "vnmclip" in kinds),
        "dmx_only": sum(1 for kinds in stems.values() if kinds == {"dmx"}),
    }


def editable(rows: list[Clip]) -> list[Clip]:
    """The clips Blender can import, in name order."""
    return sorted(
        (row for row in rows if row.editable),
        key=lambda row: (row.label.lower(), str(row.path)),
    )


def pairs(rows: list[Clip]) -> dict[str, dict[str, Clip]]:
    """Label -> kind -> clip, so a DMX and the vnmclip it replaces sit together."""
    result: dict[str, dict[str, Clip]] = {}
    for row in rows:
        key = "dmx_compiled" if (row.kind == "dmx" and row.compiled) else row.kind
        result.setdefault(row.label, {})[key] = row
    return result
