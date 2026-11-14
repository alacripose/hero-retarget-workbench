"""Every Source 2 game and tools tree on the machine, read the same way.

The workbench needs two different things from a client: a compiler for the
handoff, and a hero model from an older build for a backport. A reduced CSDK is
the first; a game install is the second; CS2 and a CS2 tools build are neither
Deadlock nor interchangeable with a Citadel CSDK, but they are still installs a
user expects the client list to show.

This is the same bounded discovery the Openlock installer uses: Steam's own
library list, every library's ``steamapps/common`` titles, the recorded depots,
and the standard preview/tools placements across drives. It never walks a whole
drive. Classification comes from the tree itself (``game/<name>/gameinfo.gi``,
the client executables and ``resourcecompiler.exe``), not from a folder name.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import steam_libraries

# A Source 2 tree names its game here: citadel (Deadlock), csgo (CS2), core (a
# CSDK tools host), dota, hlvr. This is the general read, not a Deadlock list.
CLIENT_NAMES = ("deadlock.exe", "project8.exe", "cs2.exe", "dota2.exe", "hlvr.exe")
COMPILER_NAMES = ("resourcecompiler.exe",)
TOOL_NAMES = ("resourcecompiler.exe", "CSDKCfgVPK.exe", "resourcecopy.exe")

# The bounded placements Openlock reads. ``*`` under Users keeps this general:
# any Windows account, any drive, not one user's path baked into the source.
TOOLS_PATTERNS = (
    "Users/*/Documents/Documents/deadlockpreview/Project8Staging/*",
    "Users/*/Documents/deadlockpreview/Project8Staging/*",
    "Users/*/Documents/*/Project8Staging/*",
    "Users/*/Downloads/Reduced_CSDK_*",
    "Users/*/Downloads/CSwin64_build_*",
    "Users/*/*/Project8Staging/*",
    "Projects/*/Project8Staging/*",
    "dev/*/Project8Staging/*",
    "Documents/*/Project8Staging/*",
    "Downloaded Files/CSwin64_build_*",
)


@dataclass(frozen=True)
class Install:
    root: Path
    kind: str
    engine: str
    build: str
    can_compile: bool
    can_backport: bool

    @property
    def label(self) -> str:
        return self.root.name or str(self.root)

    @property
    def summary(self) -> str:
        bits = [self.kind, self.engine or "unknown"]
        if self.build:
            bits.append(self.build)
        return " · ".join(bits)


def game_of(root: Path) -> str:
    """The game folder a tree declares, or '' when it is not a Source 2 tree."""
    try:
        for entry in sorted((root / "game").iterdir()):
            if (entry / "gameinfo.gi").is_file():
                return entry.name
    except OSError:
        pass
    return ""


def _build(root: Path, engine: str) -> str:
    info = root / "game" / engine / "steam.inf"
    if not info.is_file():
        return ""
    values: dict[str, str] = {}
    try:
        for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        return ""
    return f"{values.get('ClientVersion', '')} {values.get('VersionDate', '')}".strip()


def classify(root: Path) -> Install | None:
    """Read one tree, or None when it carries no gameinfo."""
    root = Path(root).expanduser()
    engine = game_of(root)
    if not engine:
        return None
    bin_dir = root / "game" / "bin" / "win64"
    tools_bin = root / "game" / "bin_tools" / "win64"
    compiler = any(
        (folder / name).is_file()
        for folder in (bin_dir, tools_bin)
        for name in COMPILER_NAMES
    )
    deadlock_client = (bin_dir / "deadlock.exe").is_file()
    try:
        explicit_tools = (root / "game" / "bin_tools").is_dir()
    except OSError:
        explicit_tools = False
    # Openlock's rule: a Citadel/Core tree without the shipped deadlock.exe is a
    # tools host even when it ships project8.exe or a compiler. CS2 (`csgo`) and
    # another game's tree are games; the shipped Deadlock client is a game.
    kind = (
        "tools"
        if explicit_tools or (engine.lower() in ("citadel", "core") and not deadlock_client)
        else "game"
    )
    can_backport = (
        engine.lower() == "citadel"
        and (root / "game" / "citadel" / "pak01_dir.vpk").is_file()
    )
    return Install(
        root=root,
        kind=kind,
        engine=engine,
        build=_build(root, engine),
        can_compile=compiler,
        can_backport=can_backport,
    )


def _drive_roots() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    roots: list[Path] = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZAB":
        drive = Path(f"{letter}:/")
        try:
            if drive.exists():
                roots.append(drive)
        except OSError:
            continue
    return roots


def _remember(found: dict[str, Path], path: Path) -> None:
    try:
        key = str(path.resolve()).lower()
    except OSError:
        key = str(path).lower()
    found.setdefault(key, path)


def _under(root: Path, depth: int = 3) -> list[Path]:
    """The root and directories below it, bounded; used for explicit folders."""
    paths = [root]
    frontier = [root]
    for _ in range(depth):
        next_frontier: list[Path] = []
        for parent in frontier:
            try:
                children = [child for child in parent.iterdir() if child.is_dir()]
            except OSError:
                continue
            children = [
                child
                for child in children
                if child.name.lower() not in (".git", "node_modules", "__pycache__")
            ]
            next_frontier.extend(children)
            paths.extend(children)
        frontier = next_frontier
    return paths


def discover(
    *extra_roots: Path,
    libraries: list[Path] | None = None,
    drives: list[Path] | None = None,
) -> list[Install]:
    """Every game and tools tree in the bounded standard placements."""
    found: dict[str, Path] = {}
    for root in extra_roots:
        if root is None or not str(root).strip():
            continue
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for candidate in _under(root):
            if game_of(candidate):
                _remember(found, candidate)

    libraries = libraries if libraries is not None else steam_libraries()
    for library in libraries:
        common = library / "steamapps" / "common"
        try:
            for candidate in sorted(common.iterdir()):
                if candidate.is_dir() and game_of(candidate):
                    _remember(found, candidate)
        except OSError:
            pass
        # Steam records depots below steamapps/content; a reduced tools tree
        # can be unpacked there without a title folder.
        content = library / "steamapps" / "content"
        try:
            for app in sorted(content.iterdir()):
                try:
                    depots = sorted(app.iterdir())
                except OSError:
                    continue
                for depot in depots:
                    if depot.is_dir() and game_of(depot):
                        _remember(found, depot)
        except OSError:
            pass

    for drive in drives if drives is not None else _drive_roots():
        for pattern in TOOLS_PATTERNS:
            try:
                matches = list(drive.glob(pattern))
            except (OSError, ValueError):
                continue
            for candidate in matches:
                if candidate.is_dir() and game_of(candidate):
                    _remember(found, candidate)

    rows = [classify(path) for path in found.values()]
    rows = [row for row in rows if row is not None]
    # Compiler hosts first, then backport targets, then the rest; within each
    # group the newest build name wins so a list is stable.
    rows.sort(
        key=lambda row: (
            not row.can_compile,
            not row.can_backport,
            row.engine.lower(),
            row.label.lower(),
            str(row.root).lower(),
        )
    )
    return rows
