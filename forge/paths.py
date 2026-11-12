"""Locate the live game, Source 2 Viewer, Blender, and CSDK13.

The addon passes the paths the user saved in the scene. Environment variables
remain explicit fallbacks for headless commands. When neither is set, Steam's
own library manifest is the only automatic source; no personal home-directory
or drive-letter path is a candidate.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _library_key(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser()
    return os.path.normcase(str(resolved))


def _steam_install_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                value, _ = winreg.QueryValueEx(key, "SteamPath")
            if value:
                roots.append(Path(value))
        except (OSError, ImportError):
            pass
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        base = os.environ.get(variable)
        if base:
            roots.append(Path(base) / "Steam")
    return roots


def steam_libraries() -> list[Path]:
    """Return Steam library roots from Steam's own manifest.

    The Steam install is found through its registry entry and the standard
    Program Files locations. Additional libraries come from
    ``steamapps/libraryfolders.vdf``. An unset or nonstandard machine simply
    returns no roots and the caller asks the user for the folder.
    """
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> Path:
        path = path.expanduser()
        key = _library_key(path)
        if key not in seen:
            seen.add(key)
            roots.append(path)
        return path

    for steam in _steam_install_roots():
        steam = add(steam)
        manifest = steam / "steamapps" / "libraryfolders.vdf"
        if not manifest.is_file():
            continue
        text = manifest.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            value = match.group(1).replace("\\\\", "\\")
            add(Path(value))
    return roots


def _first_file(paths: list[Path], predicate) -> Path | None:
    for path in paths:
        try:
            if path.is_file() and predicate(path):
                return path
        except OSError:
            continue
    return None


def _file_candidate(value: str | Path | None, names: tuple[str, ...]) -> Path | None:
    if value is None or not str(value).strip():
        return None
    path = Path(value).expanduser()
    if path.is_dir():
        for name in names:
            candidate = path / name
            if candidate.is_file():
                return candidate
        return None
    return path if path.is_file() else None


def _game_candidate(value: str | Path) -> tuple[Path, Path] | None:
    candidate = Path(value).expanduser()
    games = [candidate]
    if candidate.name.lower() != "game":
        games.append(candidate / "game")
    for game in games:
        info = game / "citadel" / "gameinfo.gi"
        vpk = game / "citadel" / "pak01_dir.vpk"
        if info.is_file() and vpk.is_file():
            root = game.parent if game.name.lower() == "game" else game
            return root, game
    return None


def _csdk_candidate(value: str | Path | None) -> tuple[Path, Path, Path | None] | None:
    if value is None or not str(value).strip():
        return None
    root = Path(value).expanduser()
    if root.name.lower() == "game":
        root = root.parent
    compiler = root / "game" / "bin" / "win64" / "resourcecompiler.exe"
    info = root / "game" / "citadel" / "gameinfo.gi"
    if compiler.is_file():
        return root, compiler, info if info.is_file() else None
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


def find_game(
    roots: list[Path] | None = None,
    *,
    explicit: str | Path | None = None,
) -> tuple[Path | None, Path | None, list[str]]:
    problems: list[str] = []
    configured = explicit if explicit is not None else (os.environ.get("DEADLOCK_GAME") or os.environ.get("DEADLOCK_ROOT"))
    if configured:
        result = _game_candidate(configured)
        if result:
            return result[0], result[1], problems
        problems.append(f"configured Deadlock install is not a Deadlock folder: {configured}")
        return None, None, problems

    candidates: list[Path] = []
    for root in roots or steam_libraries():
        candidates.extend(
            [
                root / "steamapps" / "common" / "Deadlock",
                root / "steamapps" / "common" / "deadlock",
            ]
        )
    for candidate in candidates:
        result = _game_candidate(candidate)
        if result:
            return result[0], result[1], problems
    problems.append("Deadlock game/citadel/gameinfo.gi and pak01_dir.vpk were not found")
    return None, None, problems


def find_s2v(explicit: str | Path | None = None) -> Path | None:
    configured = explicit if explicit is not None else os.environ.get("S2V_CLI")
    if configured is not None and str(configured).strip():
        return _file_candidate(configured, ("Source2Viewer-CLI.exe", "Source2Viewer-CLI"))
    for name in ("Source2Viewer-CLI.exe", "Source2Viewer-CLI"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def find_blender(explicit: str | Path | None = None) -> Path | None:
    configured = explicit if explicit is not None else os.environ.get("BLENDER")
    if configured is not None and str(configured).strip():
        return _file_candidate(configured, ("blender.exe", "blender"))
    found = shutil.which("blender")
    if found:
        return Path(found)
    for root in steam_libraries():
        base = root / "steamapps" / "common" / "Blender"
        for candidate in (base / "blender.exe", base / "5.4" / "blender.exe"):
            if candidate.is_file():
                return candidate
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(variable)
        if not base:
            continue
        for candidate in sorted((Path(base) / "Blender Foundation" / "Blender").glob("*/blender.exe")):
            if candidate.is_file():
                return candidate
    return None


def find_csdk(explicit: str | Path | None = None) -> tuple[Path | None, Path | None, Path | None]:
    configured = explicit if explicit is not None else os.environ.get("CSDK13_ROOT")
    if configured is not None and str(configured).strip():
        return _csdk_candidate(configured) or (None, None, None)
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


def detect(
    *,
    deadlock_root: str | Path | None = None,
    s2v_cli: str | Path | None = None,
    csdk_root: str | Path | None = None,
    blender_exe: str | Path | None = None,
) -> Environment:
    env = Environment()
    env.game_root, env.game_dir, env.problems = find_game(explicit=deadlock_root)
    if env.game_dir:
        env.vpk = env.game_dir / "citadel" / "pak01_dir.vpk"
        env.gameinfo = env.game_dir / "citadel" / "gameinfo.gi"
        env.build, env.version_date = read_build(env.game_dir)
    env.s2v = find_s2v(s2v_cli)
    env.blender = find_blender(blender_exe)
    env.csdk_root, env.resourcecompiler, env.csdk_gameinfo = find_csdk(csdk_root)
    for name, path, configured in (
        ("live game", env.game_root, deadlock_root),
        ("Source 2 Viewer", env.s2v, s2v_cli),
        ("Blender", env.blender, blender_exe),
        ("CSDK13", env.csdk_root, csdk_root),
    ):
        if path is None:
            detail = f" at {configured}" if configured is not None and str(configured).strip() else ""
            env.problems.append(f"{name} was not found{detail}")
    return env
