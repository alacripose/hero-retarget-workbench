"""Locate the live game, Source 2 Viewer, Blender, and CSDK13.

No path is guessed from a fixed drive letter when the Steam library manifest
answers the question. The environment variables are explicit overrides for a
machine whose layout differs from the default Steam install.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def steam_libraries() -> list[Path]:
    """Return Steam library roots from the client manifest and common paths."""
    roots: list[Path] = []
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Steam",
    ]
    for letter in "CDEFGH":
        candidates.append(Path(f"{letter}:/SteamLibrary"))
    for root in candidates:
        if (root / "steamapps").is_dir() and root not in roots:
            roots.append(root)
        manifest = root / "steamapps" / "libraryfolders.vdf"
        if not manifest.is_file():
            continue
        text = manifest.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            library = Path(match.group(1))
            if library not in roots:
                roots.append(library)
    return roots


def _first(paths: list[Path], predicate) -> Path | None:
    for path in paths:
        try:
            if path.is_file() and predicate(path):
                return path
        except OSError:
            continue
    return None


@dataclass
class Environment:
    game_root: Path | None = None
    game_dir: Path | None = None
    vpk: Path | None = None
    gameinfo: Path | None = None
    build: str = ""
    version_date: str = ""
    s2v: Path | None = None
    blender: Path | None = None
    csdk_root: Path | None = None
    resourcecompiler: Path | None = None
    csdk_gameinfo: Path | None = None
    problems: list[str] = field(default_factory=list)

    def summary(self) -> list[tuple[str, str]]:
        def value(path: Path | None, fallback: str) -> str:
            return str(path) if path else fallback

        return [
            ("live game", value(self.game_root, "not found")),
            ("game build", f"{self.build or 'unknown'} {self.version_date}".strip()),
            ("vpk", value(self.vpk, "not found")),
            ("source 2 viewer", value(self.s2v, "not found")),
            ("blender", value(self.blender, "not found")),
            ("csdk13", value(self.csdk_root, "not found")),
            ("resourcecompiler", value(self.resourcecompiler, "not found")),
        ]


def find_game(roots: list[Path] | None = None) -> tuple[Path | None, Path | None, list[str]]:
    problems: list[str] = []
    explicit = os.environ.get("DEADLOCK_GAME") or os.environ.get("DEADLOCK_ROOT")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    for root in roots or steam_libraries():
        candidates.append(root / "steamapps" / "common" / "Deadlock")
        candidates.append(root / "steamapps" / "common" / "deadlock")
    for candidate in candidates:
        game = candidate / "game" if (candidate / "game").is_dir() else candidate
        info = game / "citadel" / "gameinfo.gi"
        vpk = game / "citadel" / "pak01_dir.vpk"
        if info.is_file() and vpk.is_file():
            return candidate, game, problems
    problems.append("Deadlock game/citadel/gameinfo.gi and pak01_dir.vpk were not found")
    return None, None, problems


def find_s2v() -> Path | None:
    explicit = os.environ.get("S2V_CLI")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    for name in ("Source2Viewer-CLI.exe", "Source2Viewer-CLI"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    candidates.extend(
        [
            Path.home() / "Documents" / "openlock_modern" / "tools" / "s2v" / "Source2Viewer-CLI.exe",
            Path.home() / "Downloads" / "Source2Viewer-CLI.exe",
            Path.home() / "Downloads" / "Source2Viewer.exe",
        ]
    )
    return _first(candidates, lambda path: path.suffix.lower() in (".exe", ""))


def find_blender() -> Path | None:
    explicit = os.environ.get("BLENDER")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("blender")
    if found:
        candidates.append(Path(found))
    for root in steam_libraries():
        base = root / "steamapps" / "common" / "Blender"
        candidates.extend([base / "blender.exe", base / "5.4" / "blender.exe"])
    for letter in "CDEFGH":
        candidates.append(Path(f"{letter}:/Program Files/Blender Foundation/Blender/blender.exe"))
    return _first(candidates, lambda path: path.suffix.lower() == ".exe")


def find_csdk() -> tuple[Path | None, Path | None, Path | None]:
    explicit = os.environ.get("CSDK13_ROOT")
    candidates = [Path(explicit)] if explicit else []
    candidates.extend(
        [
            Path.home() / "Downloads" / "Reduced_CSDK_13",
            Path.home() / "Documents" / "Reduced_CSDK_13",
        ]
    )
    for root in candidates:
        compiler = root / "game" / "bin" / "win64" / "resourcecompiler.exe"
        info = root / "game" / "citadel" / "gameinfo.gi"
        if compiler.is_file():
            return root, compiler, info if info.is_file() else None
    return None, None, None


def read_build(game_dir: Path | None) -> tuple[str, str]:
    if not game_dir:
        return "", ""
    info = game_dir / "citadel" / "steam.inf"
    if not info.is_file():
        return "", ""
    values: dict[str, str] = {}
    for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values.get("ClientVersion", ""), values.get("VersionDate", "")


def detect() -> Environment:
    env = Environment()
    env.game_root, env.game_dir, env.problems = find_game()
    if env.game_dir:
        env.vpk = env.game_dir / "citadel" / "pak01_dir.vpk"
        env.gameinfo = env.game_dir / "citadel" / "gameinfo.gi"
        env.build, env.version_date = read_build(env.game_dir)
    env.s2v = find_s2v()
    env.blender = find_blender()
    env.csdk_root, env.resourcecompiler, env.csdk_gameinfo = find_csdk()
    for name, path in (("live game", env.game_root), ("Source 2 Viewer", env.s2v), ("Blender", env.blender), ("CSDK13", env.csdk_root)):
        if path is None:
            env.problems.append(f"{name} was not found")
    return env
