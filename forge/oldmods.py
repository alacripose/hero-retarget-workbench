"""Find older downloaded VPKs and unpacked addons, and record what they carry.

A port starts from a package someone made months or years ago. Before choosing
one, the workbench needs a corpus: which packages exist on this machine, which
hero model each one targets, how old it is, and — for unpacked source addons —
which cloth/physics sections its vmdl actually carries. A compiled VPK is only
listed by directory (file names, CRC, archive offsets); its contents are never
decompiled or interpreted here.

The owner's drives hold both shapes: ``*.vpk`` downloads and unpacked
``content/citadel_addons/<name>`` trees left behind by older CSDK installs.
Game paks are excluded by name and by the folders they live in, so a scan can
walk a whole drive without turning the live game into a mod.
"""
from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

from .modeldoc import ModeldocError, cloth_physics_sections

VPK_SIGNATURE = 0x55AA1234
VPK_DIR_ARCHIVE = 0x7FFF
HERO_DIRS = ("heroes_staging", "heroes_wip", "heroes")
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "$recycle.bin",
    "system volume information",
    "windows",
    "winsxs",
    "appdata",
}
SKIP_PATH_MARKERS = ("/game/citadel/", "/game/core/", "/game/csgo_imported/", "/dist/")
MAX_VMDL_PER_ADDON = 24


class OldModsError(ValueError):
    """A package could not be read as an old mod."""


@dataclass(frozen=True)
class VpkEntry:
    path: str
    crc: int
    preload: int
    archive_index: int
    offset: int
    length: int


@dataclass(frozen=True)
class VpkTree:
    version: int
    entries: tuple[VpkEntry, ...]

    @property
    def split(self) -> bool:
        return any(entry.archive_index != VPK_DIR_ARCHIVE for entry in self.entries)


def _cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\0", offset)
    if end < 0:
        raise OldModsError("vpk-tree-string-unterminated")
    return data[offset:end].decode("utf-8", errors="replace"), end + 1


def parse_tree(data: bytes) -> tuple[VpkEntry, ...]:
    """Parse a VPK directory tree into entries.

    The tree is a list of extensions, each holding directories, each holding file
    names and a fixed-size entry record. Preload bytes follow the record.
    """
    entries: list[VpkEntry] = []
    offset = 0
    while True:
        extension, offset = _cstring(data, offset)
        if not extension:
            break
        while True:
            directory, offset = _cstring(data, offset)
            if not directory:
                break
            prefix = directory.rstrip("/") + "/" if directory else ""
            while True:
                filename, offset = _cstring(data, offset)
                if not filename:
                    break
                if offset + 18 > len(data):
                    raise OldModsError("vpk-tree-entry-truncated")
                crc, preload, archive_index, entry_offset, length = struct.unpack_from("<IHHII", data, offset)
                offset += 16
                terminator = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                if terminator != 0xFFFF:
                    raise OldModsError("vpk-tree-entry-has-no-terminator")
                if offset + preload > len(data):
                    raise OldModsError("vpk-tree-preload-truncated")
                offset += preload
                name = f"{filename}.{extension}" if extension else filename
                entries.append(
                    VpkEntry(
                        path=prefix + name,
                        crc=crc,
                        preload=preload,
                        archive_index=archive_index,
                        offset=entry_offset,
                        length=length,
                    )
                )
    return tuple(entries)


def read_vpk(path: Path) -> VpkTree:
    """Read a VPK's directory without touching its file data."""
    path = Path(path)
    with path.open("rb") as handle:
        header = handle.read(28)
        if len(header) < 12:
            raise OldModsError(f"vpk-header-truncated: {path}")
        signature, version, tree_size = struct.unpack_from("<III", header, 0)
        if signature != VPK_SIGNATURE:
            raise OldModsError(f"vpk-signature-invalid: {path}")
        if version == 1:
            header_size = 12
        elif version == 2:
            if len(header) < 28:
                raise OldModsError(f"vpk-header-truncated: {path}")
            header_size = 28
        else:
            raise OldModsError(f"vpk-version-unsupported: {version} ({path})")
        if tree_size > 32 * 1024 * 1024:
            raise OldModsError(f"vpk-tree-too-large: {tree_size} ({path})")
        handle.seek(header_size)
        tree = handle.read(tree_size)
    if len(tree) != tree_size:
        raise OldModsError(f"vpk-tree-truncated: {path}")
    return VpkTree(version=version, entries=parse_tree(tree))


def clean_slug(value: str) -> str:
    slug = value.strip().lower()
    for suffix in ("_rotation_test", "_backup", "_default", "_july", "_lod0", "_v2", "_v1"):
        if slug.endswith(suffix) and len(slug) > len(suffix):
            slug = slug[: -len(suffix)]
    return slug


def slug_from_model(relative: str) -> str:
    """Guess the hero slug from a model path, without knowing the live roster."""
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    lower = [part.lower() for part in parts]
    for marker in HERO_DIRS:
        if marker in lower:
            index = lower.index(marker)
            if index + 1 < len(parts):
                return clean_slug(parts[index + 1])
    return clean_slug(PurePosixPath(relative).stem)


def hero_slugs(paths) -> list[str]:
    return sorted({slug for slug in (slug_from_model(path) for path in paths) if slug})


def cloth_inventory(vmdl_paths) -> tuple[list[str], dict[str, list[str]]]:
    """Return the union of cloth/physics section names and per-model sections."""
    union: set[str] = set()
    per_model: dict[str, list[str]] = {}
    for path in vmdl_paths:
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            names = cloth_physics_sections(text)
        except (OSError, ModeldocError):
            names = []
        per_model[path.name] = names
        union.update(names)
    return sorted(union), per_model


@dataclass(frozen=True)
class ModRecord:
    path: str
    kind: str
    addon: str
    hero: str
    bytes: int
    modified: str
    models: tuple[str, ...] = ()
    cloth_sections: tuple[str, ...] = ()
    per_model: dict[str, list[str]] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "addon": self.addon,
            "hero": self.hero,
            "bytes": self.bytes,
            "modified": self.modified,
            "models": list(self.models),
            "cloth_sections": list(self.cloth_sections),
            "per_model": self.per_model,
            "note": self.note,
        }


@dataclass
class Inventory:
    roots: list[str]
    since: str
    until: str
    mods: list[ModRecord]
    skipped_game_paks: int
    skipped_unreadable: list[str]

    def counts(self) -> dict[str, int]:
        return {
            "packages": len(self.mods),
            "vpks": sum(1 for mod in self.mods if mod.kind == "vpk"),
            "addons": sum(1 for mod in self.mods if mod.kind == "addon"),
            "with_cloth_sections": sum(1 for mod in self.mods if mod.cloth_sections),
            "without_cloth_sections": sum(1 for mod in self.mods if not mod.cloth_sections),
            "hero_packages": sum(
                1 for mod in self.mods if any("hero" in model.lower() for model in mod.models)
            ),
            "skipped_game_paks": self.skipped_game_paks,
        }

    def cloth_types(self) -> dict[str, int]:
        types: dict[str, int] = {}
        for mod in self.mods:
            for name in mod.cloth_sections:
                types[name] = types.get(name, 0) + 1
        return dict(sorted(types.items()))

    def to_dict(self) -> dict:
        return {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "roots": self.roots,
            "since": self.since,
            "until": self.until,
            "counts": self.counts(),
            "cloth_types": self.cloth_types(),
            "skipped_unreadable": self.skipped_unreadable,
            "mods": [mod.to_dict() for mod in self.mods],
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path


def _is_game_pak(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith("pak0") or name.startswith("pak1"):
        return True
    if name.startswith("shaders_"):
        return True
    if "bakeresourcecache" in name:
        return True
    marker = "/" + path.as_posix().lower().lstrip("/")
    return any(part in marker for part in SKIP_PATH_MARKERS)


def _within(path: Path, since: date | None, until: date | None) -> bool:
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return False
    if since is not None and stamp < since:
        return False
    if until is not None and stamp > until:
        return False
    return True


def _date(stamp: float) -> str:
    return datetime.fromtimestamp(stamp).date().isoformat()


def _walk_dirs(root: Path, max_depth: int):
    root = root.resolve()
    base_depth = len(root.parts)
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        dirs[:] = [
            name
            for name in dirs
            if name.lower() not in SKIP_DIRS and depth < max_depth
        ]
        yield current_path, depth


def _addon_from_dir(path: Path, since: date | None, until: date | None) -> ModRecord | None:
    vmdls = sorted(path.rglob("*.vmdl"))[:MAX_VMDL_PER_ADDON]
    if not vmdls:
        return None
    newest = max(vmdls, key=lambda item: item.stat().st_mtime)
    if not _within(newest, since, until):
        return None
    models = [item.relative_to(path).as_posix() for item in vmdls]
    cloth, per_model = cloth_inventory(vmdls)
    return ModRecord(
        path=str(path),
        kind="addon",
        addon=path.name,
        hero=", ".join(hero_slugs(models)),
        bytes=sum(item.stat().st_size for item in vmdls),
        modified=_date(newest.stat().st_mtime),
        models=tuple(models),
        cloth_sections=tuple(cloth),
        per_model=per_model,
        note="" if cloth else "no-cloth-sections",
    )


def _vpk_record(path: Path, since: date | None, until: date | None) -> ModRecord | None:
    if not _within(path, since, until):
        return None
    tree = read_vpk(path)
    compiled = [
        entry.path
        for entry in tree.entries
        if entry.path.lower().endswith((".vmdl_c", ".vmdl"))
    ]
    models = sorted(path for path in compiled if "hero" in path.lower())
    chosen = models or compiled
    slug = ", ".join(hero_slugs(chosen)) if chosen else ""
    note = ""
    if tree.split:
        note = "split-archives"
    if not compiled:
        return None
    return ModRecord(
        path=str(path),
        kind="vpk",
        addon=path.stem,
        hero=slug,
        bytes=path.stat().st_size,
        modified=_date(path.stat().st_mtime),
        models=tuple(chosen[:MAX_VMDL_PER_ADDON]),
        note=note,
    )


def inventory(
    roots,
    *,
    since: date | None = None,
    until: date | None = None,
    max_depth: int = 7,
    progress=None,
) -> Inventory:
    """Scan roots for VPKs and unpacked citadel addons.

    ``progress`` is an optional ``(fraction, message)`` callback. The scan can
    walk tens of thousands of directories, and a button with no moving state
    reads as a button that did nothing.
    """
    mods: list[ModRecord] = []
    seen: set[str] = set()
    skipped_game_paks = 0
    skipped_unreadable: list[str] = []
    resolved_roots = [Path(root).expanduser().resolve() for root in roots]
    total_roots = max(1, len(resolved_roots))

    for root_index, root in enumerate(resolved_roots):
        base = root_index / total_roots
        span = 1.0 / total_roots
        if progress is not None:
            progress(base + span * 0.01, f"scanning {root.name or root}")
        if not root.exists():
            skipped_unreadable.append(f"root-missing: {root}")
            continue
        walked = list(_walk_dirs(root, max_depth))
        step = max(1, len(walked) // 100)
        for index, (current, _depth) in enumerate(walked):
            if progress is not None and index % step == 0:
                progress(
                    base + span * (0.05 + 0.9 * index / max(1, len(walked))),
                    f"{current.name}: {len(mods)} found",
                )
            lower = current.name.lower()
            if lower == "citadel_addons":
                for child in sorted(current.iterdir()):
                    if not child.is_dir():
                        continue
                    key = str(child.resolve()).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    record = _addon_from_dir(child, since, until)
                    if record is not None:
                        mods.append(record)
            for name in current.glob("*.vpk"):
                if not name.is_file():
                    continue
                if _is_game_pak(name):
                    skipped_game_paks += 1
                    continue
                key = str(name.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    record = _vpk_record(name, since, until)
                except (OldModsError, OSError) as error:
                    skipped_unreadable.append(f"{error}")
                    continue
                if record is not None:
                    mods.append(record)

    mods.sort(key=lambda mod: (mod.modified, mod.path), reverse=True)
    return Inventory(
        roots=[str(root) for root in resolved_roots],
        since=since.isoformat() if since else "",
        until=until.isoformat() if until else "",
        mods=mods,
        skipped_game_paks=skipped_game_paks,
        skipped_unreadable=skipped_unreadable,
    )
