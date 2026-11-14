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


def _steam_manifest_install(library: Path, appid: str = "1422450") -> Path | None:
    """The install folder Steam records for an app, even when it was renamed.

    Steam writes ``appmanifest_<appid>.acf`` beside the game and keeps the
    folder name in ``installdir``. Reading it finds a library where the folder
    is not literally ``Deadlock``, which the fixed leaf below cannot.
    """
    record = library / "steamapps" / f"appmanifest_{appid}.acf"
    try:
        text = record.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r'"installdir"\s+"([^"]+)"', text)
    if not match:
        return None
    candidate = library / "steamapps" / "common" / match.group(1).replace("\\\\", "\\")
    return candidate if _game_candidate(candidate) else None


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

    libraries = roots or steam_libraries()
    candidates: list[Path] = []
    for root in libraries:
        candidates.extend(
            [
                root / "steamapps" / "common" / "Deadlock",
                root / "steamapps" / "common" / "deadlock",
            ]
        )
        manifest = _steam_manifest_install(root)
        if manifest is not None:
            candidates.append(manifest)
    for candidate in candidates:
        result = _game_candidate(candidate)
        if result:
            return result[0], result[1], problems
    # Steam's manifest can be absent in a copied library; one bounded level of
    # `steamapps/common` finds a Deadlock tree under another folder name.
    for root in libraries:
        common = root / "steamapps" / "common"
        try:
            entries = sorted(common.iterdir())
        except OSError:
            continue
        for candidate in entries:
            result = _game_candidate(candidate)
            if result:
                return result[0], result[1], problems
    problems.append("Deadlock game/citadel/gameinfo.gi and pak01_dir.vpk were not found")
    return None, None, problems


S2V_CLI_NAMES = ("Source2Viewer-CLI.exe", "Source2Viewer-CLI")
S2V_GUI_NAMES = ("Source2Viewer.exe", "Source2Viewer")


def _is_gui(path: Path) -> bool:
    return path.name.lower() in {name.lower() for name in S2V_GUI_NAMES}


def _tool_search_roots() -> list[Path]:
    """Standard user folders a downloaded tool is unpacked into.

    These are Windows' own folder names, not a machine's path: the addon never
    points at one user's folder. The search is bounded and only runs when no
    saved or PATH path resolved, which is the case after a viewer is moved.
    """
    roots: list[Path] = []
    for name in ("Downloads", "Desktop"):
        candidate = Path.home() / name
        try:
            if candidate.is_dir():
                roots.append(candidate)
        except OSError:
            continue
    return roots


def _find_named(
    base: Path,
    names: tuple[str, ...],
    *,
    max_depth: int = 3,
) -> Path | None:
    """First matching file under a bounded walk, pruned and deterministic."""
    if not base.is_dir():
        return None
    skip = {".git", "node_modules", "__pycache__", "$recycle.bin", "system volume information"}
    base_depth = len(base.parts)
    try:
        for current, folders, files in os.walk(base):
            depth = len(Path(current).parts) - base_depth
            if depth >= max_depth:
                folders[:] = []
            else:
                folders[:] = sorted(
                    folder for folder in folders if folder.lower() not in skip
                )
            lowered = {name.lower() for name in names}
            for name in sorted(files):
                if name.lower() in lowered:
                    return Path(current) / name
    except OSError:
        return None
    return None


def find_s2v(
    explicit: str | Path | None = None,
    *,
    roots: list[Path] | None = None,
) -> Path | None:
    """The Source 2 Viewer CLI, from the chosen path or beside it.

    The GUI binary cannot run the extraction commands this addon sends, so it is
    never returned as the CLI. It does ship beside the CLI, so a path that points
    at the GUI still resolves: the CLI in the same folder is what the user meant.
    """
    configured = explicit if explicit is not None else os.environ.get("S2V_CLI")
    if configured is not None and str(configured).strip():
        path = Path(configured).expanduser()
        if path.is_dir():
            return _file_candidate(path, S2V_CLI_NAMES)
        if path.is_file():
            if path.name.lower() in {name.lower() for name in S2V_CLI_NAMES}:
                return path
            # A GUI path, or any other file in the install folder: look for the
            # CLI that ships next to it instead of refusing the pick outright.
            sibling = _file_candidate(path.parent, S2V_CLI_NAMES)
            if sibling is not None:
                return sibling
        return None
    for name in S2V_CLI_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    # The addon's own tools folder (where Download & install puts the CLI), and
    # any tool root the caller names, so a saved workspace finds its viewer.
    for root in roots or []:
        base = Path(root).expanduser()
        for candidate in (
            _file_candidate(base, S2V_CLI_NAMES),
            _file_candidate(base / "tools", S2V_CLI_NAMES),
            _file_candidate(base / "tools" / "s2v", S2V_CLI_NAMES),
        ):
            if candidate is not None:
                return candidate
    # A viewer shipped beside a Steam library is found without a personal path.
    for library in steam_libraries():
        for folder in ("Source2Viewer", "Source2ViewerCLI", "source2viewer"):
            candidate = _file_candidate(
                library / "steamapps" / "common" / folder, S2V_CLI_NAMES
            )
            if candidate is not None:
                return candidate
    # A release zip is normally unpacked into Downloads; after the saved path is
    # moved this is the difference between "missing" and finding the CLI again.
    for root in _tool_search_roots():
        found = _find_named(root, S2V_CLI_NAMES, max_depth=3)
        if found is not None:
            return found
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
    # A reduced CSDK is normally unpacked into Downloads as one folder. The
    # search is one level deep and only accepts a tree with the compiler, so it
    # cannot mistake another game install for a tools host.
    for root in _tool_search_roots():
        try:
            candidates = [root, *sorted(root.iterdir())]
        except OSError:
            continue
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            result = _csdk_candidate(candidate)
            if result is not None:
                return result
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


def s2v_gui_note(configured: str | Path | None) -> str | None:
    """Explain a path that only reaches the GUI, since the GUI cannot extract.

    A pick that still resolves to a CLI (the file itself, its folder, or the CLI
    beside it) has no note: only a path whose folder offers no CLI at all does.
    """
    if configured is None or not str(configured).strip():
        return None
    if find_s2v(configured) is not None:
        return None
    path = Path(str(configured)).expanduser()
    folder = path if path.is_dir() else path.parent
    gui = next((folder / name for name in S2V_GUI_NAMES if (folder / name).is_file()), None)
    if gui is None and not _is_gui(path):
        return None
    shown = gui if gui is not None else path
    return (
        f"Source 2 Viewer GUI only at {shown}; the GUI has no CLI mode, "
        "so choose Source2Viewer-CLI.exe in Setup or place it in that folder"
    )


def detect(
    *,
    deadlock_root: str | Path | None = None,
    s2v_cli: str | Path | None = None,
    csdk_root: str | Path | None = None,
    blender_exe: str | Path | None = None,
    tool_roots: list[Path] | None = None,
) -> Environment:
    env = Environment()
    env.game_root, env.game_dir, env.problems = find_game(explicit=deadlock_root)
    if env.game_dir:
        env.vpk = env.game_dir / "citadel" / "pak01_dir.vpk"
        env.gameinfo = env.game_dir / "citadel" / "gameinfo.gi"
        env.build, env.version_date = read_build(env.game_dir)
    env.s2v = find_s2v(s2v_cli, roots=tool_roots)
    if env.s2v is None and s2v_cli is not None and str(s2v_cli).strip():
        # A saved CLI file can be moved by a later download. Only a missing
        # CLI-shaped pick falls back; a folder or a deliberately wrong pick
        # stays a refusal, so detection does not overrule the user silently.
        picked = Path(str(s2v_cli)).expanduser()
        if (
            picked.name.lower() in {name.lower() for name in S2V_CLI_NAMES}
            and not picked.exists()
        ):
            env.s2v = find_s2v(None, roots=tool_roots)
    # find_s2v also reads S2V_CLI itself; the message below has to know that value
    # too, or a headless run reports a bare "not found" for a path it was given.
    if s2v_cli is None:
        s2v_cli = os.environ.get("S2V_CLI")
    env.blender = find_blender(blender_exe)
    env.csdk_root, env.resourcecompiler, env.csdk_gameinfo = find_csdk(csdk_root)
    if env.csdk_root is None and csdk_root is not None and str(csdk_root).strip():
        picked = Path(str(csdk_root)).expanduser()
        if "csdk" in picked.name.lower() and not picked.exists():
            env.csdk_root, env.resourcecompiler, env.csdk_gameinfo = find_csdk(None)
    for name, path, configured in (
        ("live game", env.game_root, deadlock_root),
        ("Source 2 Viewer", env.s2v, s2v_cli),
        ("Blender", env.blender, blender_exe),
        ("CSDK13", env.csdk_root, csdk_root),
    ):
        if path is None:
            detail = f" at {configured}" if configured is not None and str(configured).strip() else ""
            gui = s2v_gui_note(configured) if name == "Source 2 Viewer" else None
            if gui is not None:
                env.problems.append(gui)
            else:
                env.problems.append(f"{name} was not found{detail}")
    return env
