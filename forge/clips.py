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

# Folder names that hold animation sources. AG2 projects keep the decompiled
# ``.vnmskel`` beside a ``clips`` folder; AG1 projects normally use ``anims``.
# These are discovery hints, never a rule: a clip found directly in the
# extraction root is still listed.
CLIP_DIRS: tuple[str, ...] = ("clips", "anims", "anims2", "ag1", "ag2", "animgraph2")

AG2_TOKENS: tuple[str, ...] = ("ag2", "animgraph2", "anims2", "vnmclip", "vnmskel", "vnmgraph")
AG1_TOKENS: tuple[str, ...] = ("ag1", "animgraph1", "anims1", "vanmgrph")


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


def animgraph(path: Path | str, roots: tuple[Path, ...] | list[Path] = (), vnmskel: Path | None = None) -> str:
    """Classify a clip as ``AG1``, ``AG2`` or ``UNKNOWN`` from its location.

    This is deliberately a path/type read, not a file parse.  The Cooked ``.vnmskel``
    and ``.vnmclip`` suffixes belong to AnimGraph 2, and the community workflow
    puts a decompiled ``.vnmskel`` beside a ``clips`` directory.  A bare DMX under
    ``anims`` is the legacy AnimGraph 1 shape.  If neither signal exists, the row
    says ``UNKNOWN`` rather than inventing a graph version.
    """
    file = Path(path)
    lowered = [part.lower() for part in file.parts]
    joined = "/".join(lowered)
    name = file.name.lower()
    if any(token in joined for token in AG2_TOKENS):
        return "AG2"
    if any(token in name for token in AG2_TOKENS):
        return "AG2"
    if any(part == "clips" for part in lowered):
        return "AG2"
    if vnmskel is not None:
        skeleton = Path(vnmskel)
        try:
            relative = file.resolve().relative_to(skeleton.parent.resolve())
        except (OSError, ValueError):
            relative = None
        if relative is not None and relative.parts and relative.parts[0].lower() in ("clips", "anims2", "ag2"):
            return "AG2"
    if any(token in joined for token in AG1_TOKENS):
        return "AG1"
    if any(token in name for token in AG1_TOKENS):
        return "AG1"
    if "anims" in lowered or "anims" in joined:
        return "AG1"
    return "UNKNOWN"


def clip_roots(root: Path | str, max_depth: int = 4) -> list[Path]:
    """Directories worth scanning for clips under one extraction root.

    An extraction root also contains models, materials and compiled VPK content.
    The named clip folders are preferred when present; otherwise the root itself
    is returned so an unusual layout is still scanned.  The walk is bounded, so a
    drive-sized folder cannot turn a panel redraw into a filesystem crawl.
    """
    base = Path(root)
    if not base.is_dir():
        return []
    found: list[Path] = []
    base_depth = len(base.parts)
    for current, dirs, _files in os.walk(base):
        path = Path(current)
        depth = len(path.parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        else:
            dirs.sort()
        if path.name.lower() in CLIP_DIRS:
            found.append(path)
    return found or [base]


def find_vnmskel(roots: tuple[Path, ...] | list[Path]) -> Path | None:
    """The first decompiled AnimGraph 2 skeleton under the scan roots."""
    for root in roots:
        base = Path(root)
        if not base.is_dir():
            continue
        direct = sorted(path for path in base.glob("*.vnmskel") if path.is_file())
        if direct:
            return direct[0]
        nested = sorted(path for path in base.rglob("*.vnmskel") if path.is_file())
        if nested:
            return nested[0]
    return None


def discover(roots: tuple[Path, ...] | list[Path]) -> list[Clip]:
    """Scan every root once and de-duplicate clips by resolved path."""
    seen: set[Path] = set()
    rows: list[Clip] = []
    for root in roots:
        for row in scan(root):
            try:
                key = row.path.resolve()
            except OSError:
                key = row.path
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
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


def export_folder(clip_folder: Path | str | None, override: str | Path | None = None) -> Path | None:
    """Where written clips go: the override, else ``<clip folder>/edited``.

    Never the clip folder itself. A write-back that overwrites the extraction is
    a one-way door: the DMX the owner decompiled is the only copy they have.
    """
    if override:
        return Path(override)
    if clip_folder is None:
        return None
    return Path(clip_folder) / "edited"


def glob_escape(name: str) -> str:
    """Escape ``*``, ``?`` and ``[`` so a name matches exactly that one action.

    PulseSrcOps selects the actions to write per file with an fnmatch glob over
    every action that has users. A clip called ``walk*`` would otherwise export
    every action whose name starts with ``walk`` into one file, one after another.
    """
    escaped = []
    for char in name:
        if char in "*?[":
            escaped.append("[[]" if char == "[" else f"[{char}]")
        else:
            escaped.append(char)
    return "".join(escaped)


def written_path(root: Path | str, label: str, ag: str = "") -> Path:
    """Where an edited clip is written for ModelDoc to import.

    AG2 uses the decompiled skeleton's ``clips`` folder, the layout the VmClip
    guide puts the DMX in; AG1 and unknown clips keep the legacy ``anims`` folder.
    """
    folder = "clips" if ag == "AG2" else "anims"
    return Path(root) / folder / f"{label}.dmx"


def pairs(rows: list[Clip]) -> dict[str, dict[str, Clip]]:
    """Label -> kind -> clip, so a DMX and the vnmclip it replaces sit together."""
    result: dict[str, dict[str, Clip]] = {}
    for row in rows:
        key = "dmx_compiled" if (row.kind == "dmx" and row.compiled) else row.kind
        result.setdefault(row.label, {})[key] = row
    return result
