"""Download and install the external tools the workbench drives.

The owner deleted the Source 2 Viewer CLI and asked the Setup page to install
what it needs. Two different sources exist and they are treated differently:

* Source 2 Viewer publishes a CLI archive as a GitHub release asset, so it can be
  resolved and downloaded without asking the user for a version number.
* The community CSDK13 is distributed from the Deadlock Modding Notes page
  (Google Drive and Mega). Neither link is a stable direct file URL, so the
  add-on opens that page and installs an archive the user has downloaded; it
  never pretends to know a direct download.

Both installers write into a destination the user chooses and verify the result
by looking for the executable they are supposed to produce, so a failed
extraction cannot be mistaken for an installed tool.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

S2V_API = "https://api.github.com/repos/ValveResourceFormat/ValveResourceFormat/releases/latest"
S2V_ASSET = "cli-windows-x64.zip"
S2V_PAGE = "https://s2v.app/"
CSDK13_PAGE = "https://deadlockmodding.pages.dev/modding-tools/csdk-13"
S2V_CLI_NAMES = ("Source2Viewer-CLI.exe", "Source2Viewer-CLI")
USER_AGENT = "hero-retarget-workbench"


class ProvisionError(RuntimeError):
    """A tool could not be resolved, downloaded, or installed."""


def _fetch(url: str, destination: Path, progress=None) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with destination.open("wb") as handle:
            while True:
                block = response.read(1024 * 256)
                if not block:
                    break
                handle.write(block)
                written += len(block)
                if progress is not None and total:
                    progress(min(0.9, written / total), f"{written // (1024 * 1024)} / {total // (1024 * 1024)} MiB")
    if destination.stat().st_size == 0:
        raise ProvisionError(f"download-was-empty: {url}")
    return destination


def latest_cli_release() -> tuple[str, str]:
    """Return (version, asset URL) for the newest Source 2 Viewer CLI archive."""
    request = urllib.request.Request(S2V_API, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = str(payload.get("tag_name") or payload.get("name") or "")
    assets = payload.get("assets") or []
    for asset in assets:
        if str(asset.get("name", "")).lower() == S2V_ASSET:
            return tag, str(asset.get("browser_download_url", ""))
    names = ", ".join(str(asset.get("name", "")) for asset in assets)
    raise ProvisionError(f"s2v-cli-asset-missing: {S2V_ASSET} not in release {tag or 'latest'} ({names})")


def _find_cli(root: Path) -> Path | None:
    for name in S2V_CLI_NAMES:
        direct = root / name
        if direct.is_file():
            return direct
        found = sorted(root.rglob(name))
        if found:
            return found[0]
    return None


def install_s2v(destination: Path, *, progress=None) -> Path:
    """Download the latest CLI archive and extract it under ``destination``."""
    destination = Path(destination).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    if progress is not None:
        progress(0.02, "resolving the latest Source 2 Viewer release")
    version, url = latest_cli_release()
    if not url:
        raise ProvisionError("s2v-cli-url-missing")
    with tempfile.TemporaryDirectory(prefix="dmf-s2v-") as temporary:
        archive = Path(temporary) / S2V_ASSET
        if progress is not None:
            progress(0.1, f"downloading Source 2 Viewer {version}")
        _fetch(url, archive, progress)
        target = destination / "s2v"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(target)
    cli = _find_cli(target if target.is_dir() else destination)
    if cli is None:
        raise ProvisionError(f"s2v-cli-missing-after-extract: {destination}")
    return cli


def _strip_single_folder(root: Path) -> Path:
    """A CSDK archive ships one top folder; the install root is that folder."""
    children = [child for child in root.iterdir() if child.is_dir()]
    files = [child for child in root.iterdir() if child.is_file()]
    if len(children) == 1 and not files:
        return children[0]
    return root


def install_archive(archive: Path, destination: Path, *, progress=None) -> Path:
    """Extract a downloaded CSDK archive and return the install root.

    Accepts a ``.zip``; the community archives are zip files. A folder is
    accepted too, so an already-unpacked client can be registered in one step.
    """
    archive = Path(archive).expanduser()
    destination = Path(destination).expanduser()
    if not archive.exists():
        raise ProvisionError(f"archive-missing: {archive}")
    if archive.is_dir():
        root = archive
    elif archive.suffix.lower() == ".zip":
        destination.mkdir(parents=True, exist_ok=True)
        if progress is not None:
            progress(0.2, "extracting the client archive")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
        root = _strip_single_folder(destination)
    else:
        raise ProvisionError(f"archive-format-unsupported: {archive.suffix or archive.name}")
    compiler = root / "game" / "bin" / "win64" / "resourcecompiler.exe"
    if not compiler.is_file():
        raise ProvisionError(
            f"not-a-csdk-install: {root} has no game/bin/win64/resourcecompiler.exe"
        )
    return root


def find_clients(*roots: Path) -> list[Path]:
    """Every CSDK-style install under the given roots (three levels deep)."""
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        candidates = [root]
        for depth in range(1, 4):
            candidates.extend(
                path
                for path in _level(root, depth)
                if path.is_dir()
            )
        for candidate in candidates:
            compiler = candidate / "game" / "bin" / "win64" / "resourcecompiler.exe"
            if not compiler.is_file():
                continue
            key = str(candidate.resolve()).lower()
            if key not in seen:
                seen.add(key)
                found.append(candidate)
    return sorted(found)


def _level(root: Path, depth: int):
    if depth == 1:
        yield from root.glob("*")
        return
    for parent in _level(root, depth - 1):
        if parent.is_dir():
            yield from parent.glob("*")
