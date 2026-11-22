"""Track what Valve changes inside Deadlock's VPKs, without parsing a VPK.

Source 2 Viewer is the reader.  Its ``--vpk_dir`` listing carries the path, CRC,
stored size, archive chunk number and offset of every entry; this tool turns
that listing into a snapshot, binds the snapshot with BLAKE3, and reports what
was added, removed or modified between two snapshots.

That boundary is deliberate.  Reimplementing the VPK directory would make the
tracker a second, wrong reader of the format; S2V is already the reader this
project ships against.  The tool never writes a VPK either.

    python tools/vpk_tracker.py snapshot --label 6863
    python tools/vpk_tracker.py snapshot --manifest 1422456:322100466064667547
    python tools/vpk_tracker.py list
    python tools/vpk_tracker.py diff <old> <new> --json artifacts/receipts/vpk-diff.json
    python tools/vpk_tracker.py serve --port 8765

A local snapshot is one source; a historical snapshot is another.  The
``--manifest`` form fetches every ``game/citadel/*_dir.vpk`` and ``steam.inf``
for that depot manifest through SteamFileDownloader, then reads them with S2V.
Only directory VPKs are downloaded; ``ls`` supplies the archive chunk inventory,
so a historical build does not require an installed copy or its chunks.

Snapshots live under ``artifacts/vpk-tracker/snapshots`` and are ignored by git;
manifest downloads live under ``artifacts/vpk-tracker/depots``.  The UI is a
local, no-build Popit surface in ``tools/vpk_tracker_ui``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.hashes import blake3_file, blake3_hex  # noqa: E402
from forge.paths import detect  # noqa: E402

SCHEMA = "openlock.vpk-tracker/1"
TRACKER_DIR = ROOT / "artifacts" / "vpk-tracker"
SNAPSHOT_DIR = TRACKER_DIR / "snapshots"
INDEX_PATH = TRACKER_DIR / "index.json"
UI_DIR = Path(__file__).resolve().parent / "vpk_tracker_ui"
LEDGER = ROOT / "ledger" / "ledger.jsonl"
SFD_NAMES = ("SteamFileDownloader.exe", "SteamFileDownloader")
SFD_CANDIDATES = (
    ROOT / "artifacts" / "tools" / "sfd" / "SteamFileDownloader.exe",
    ROOT / "tools" / "sfd" / "SteamFileDownloader.exe",
)
DEFAULT_APP = "1422450"
DEFAULT_DEPOT = "1422456"
DEFAULT_MANIFESTS = TRACKER_DIR / "depots"
LAUNCH_LOGS = TRACKER_DIR / "logs"
GITHUB_REPO = "SteamTracking/GameTracking-Deadlock"
GITHUB_MANIFEST_PATH = "manifests/manifest_1422456.txt"
BUILD_HISTORY_LIMIT = 30
LIVE_POLL_SECONDS = 2.0
LIVE_SETTLE_SECONDS = 2.5

_ENTRY = re.compile(
    r"^(?P<path>.+?) crc=(?P<crc>0x[0-9a-fA-F]+) metadatasz=(?P<meta>\d+) "
    r"fnumber=(?P<fnum>\d+) ofs=(?P<offset>0x[0-9a-fA-F]+) sz=(?P<size>\d+)\s*$"
)
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class TrackerError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# S2V listing


def parse_vpk_dir(text: str) -> list[list]:
    """Read S2V's ``--vpk_dir`` output into compact entries.

    An entry is ``[path, crc32, stored_size, archive_chunk, offset]``.  A
    non-empty line that does not match is a refusal, not a skip: a silently
    dropped line would make a snapshot claim a file was removed.
    """
    entries: list[list] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.replace("\r", "").strip()
        if not line:
            continue
        match = _ENTRY.match(line)
        if match is None:
            raise TrackerError(f"vpk-listing-unreadable line {number}: {line[:180]}")
        entries.append(
            [
                match.group("path").replace("\\", "/"),
                int(match.group("crc"), 16),
                int(match.group("size")),
                int(match.group("fnum")),
                int(match.group("offset"), 16),
            ]
        )
    entries.sort(key=lambda entry: entry[0].casefold())
    return entries


def list_vpk(s2v: Path, vpk: Path, *, timeout: int = 300) -> list[list]:
    if not Path(s2v).is_file():
        raise TrackerError(f"source-2-viewer-missing: {s2v}")
    if not Path(vpk).is_file():
        raise TrackerError(f"vpk-missing: {vpk}")
    process = subprocess.run(
        [str(s2v), "-i", str(vpk), "--vpk_dir"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "").strip()[-500:]
        raise TrackerError(f"vpk-listing-failed: {Path(vpk).name}: {detail}")
    entries = parse_vpk_dir(process.stdout or "")
    if not entries:
        raise TrackerError(f"vpk-listing-empty: {Path(vpk).name}: {(process.stderr or '')[-300:]}")
    return entries


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value) -> str:
    return "blake3:" + blake3_hex(_canonical(value))


def _s2v_version(s2v: Path) -> str:
    try:
        process = subprocess.run(
            [str(s2v), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    line = (process.stdout or "").strip().splitlines()
    return line[0].replace("Version:", "").strip() if line else ""


def chunk_prefix(vpk: Path) -> str:
    name = Path(vpk).name
    if name.lower().endswith("_dir.vpk"):
        return name[: -len("_dir.vpk")] + "_"
    return Path(vpk).stem + "_"


def chunks_for(vpk: Path) -> list[dict]:
    """The archive chunks S2V reads beside a ``*_dir.vpk``, by stat only."""
    vpk = Path(vpk)
    prefix = chunk_prefix(vpk)
    chunks = []
    for path in sorted(vpk.parent.glob(prefix + "*.vpk")):
        if path.name.lower() == vpk.name.lower() or not path.is_file():
            continue
        stat = path.stat()
        chunks.append({"name": path.name, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return chunks


def capture_vpk(
    s2v: Path,
    vpk: Path,
    *,
    include_chunks: bool = True,
    chunks: list[dict] | None = None,
) -> dict:
    vpk = Path(vpk).resolve()
    stat = vpk.stat()
    entries = list_vpk(s2v, vpk)
    row = {
        "name": vpk.name,
        "path": str(vpk),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "blake3": "blake3:" + blake3_file(vpk),
        "entry_count": len(entries),
        "entries_digest": _digest(entries),
        "entries": entries,
    }
    if include_chunks:
        row["chunks"] = chunks_for(vpk) if chunks is None else chunks
    return row


# ---------------------------------------------------------------------------
# SteamFileDownloader: historical manifests without an installed build


def find_sfd(explicit: str | Path | None = None) -> Path | None:
    configured = explicit or os.environ.get("SFD_CLI") or os.environ.get("STEAM_FILE_DOWNLOADER")
    if configured is not None and str(configured).strip():
        path = Path(str(configured)).expanduser()
        if path.is_dir():
            for name in SFD_NAMES:
                candidate = path / name
                if candidate.is_file():
                    return candidate
            return None
        return path if path.is_file() else None
    for candidate in SFD_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("SteamFileDownloader")
    return Path(found) if found else None


def parse_sfd_rows(text: str) -> list[dict]:
    """Read SteamFileDownloader's tab-separated manifest rows.

    ``ls`` rows are depot, manifest, sha1, size, path.  VPK entry rows use crc32
    in the sha1 column and carry ``<dir.vpk>:<entry>`` in the path column; this
    parser keeps the columns intact and lets the caller choose which it needs.
    """
    rows: list[dict] = []
    for raw in text.splitlines():
        fields = raw.replace("\r", "").split("\t")
        if len(fields) < 5:
            continue
        depot, manifest, digest, size, path = fields[:5]
        if not depot.strip().isdigit() or not manifest.strip().isdigit():
            continue
        try:
            byte_size = int(size)
        except ValueError:
            continue
        rows.append(
            {
                "depot": depot.strip(),
                "manifest": manifest.strip(),
                "sha1": digest.strip(),
                "size": byte_size,
                "path": path.strip().replace("\\", "/"),
            }
        )
    return rows


def read_steam_inf(path: Path) -> tuple[str, str]:
    if not Path(path).is_file():
        return "", ""
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values.get("ClientVersion", ""), values.get("VersionDate", "")


def manifest_chunks(rows: list[dict], vpk_name: str) -> list[dict]:
    """The archive chunks a manifest places beside one ``*_dir.vpk``."""
    prefix = chunk_prefix(Path(vpk_name))
    chunks = []
    for row in rows:
        name = Path(row["path"]).name
        if name == vpk_name or not name.startswith(prefix) or not name.lower().endswith(".vpk"):
            continue
        chunks.append({"name": name, "size": row["size"], "sha1": row["sha1"]})
    chunks.sort(key=lambda chunk: chunk["name"])
    return chunks


def _sfd_failure(process: subprocess.CompletedProcess[str], verb: str) -> TrackerError:
    detail = (process.stderr or process.stdout or "").strip()[-800:]
    if process.returncode == 3:
        return TrackerError(
            "steam-login-required: run `python tools/vpk_tracker.py login` once and scan the QR "
            "with the Steam mobile app; SteamFileDownloader stores the refresh token"
        )
    if process.returncode == 4:
        return TrackerError("steam-rate-limited: wait about 15 minutes before retrying")
    if process.returncode == 5:
        return TrackerError(f"steam-no-access: {detail}")
    if process.returncode == 6:
        return TrackerError(f"steam-file-downloader-{verb}-no-match: {detail}")
    return TrackerError(f"steam-file-downloader-{verb}-failed: {detail}")


def fetch_manifests(
    sfd: Path,
    app: str,
    targets: list[str],
    cache: Path,
    *,
    timeout: int = 1800,
) -> list[dict]:
    """Download every ``*_dir.vpk`` for one or more depot manifests.

    One login covers all targets.  Only directory VPKs and ``steam.inf`` are
    downloaded: the directory holds every path, CRC, size, archive chunk and
    offset, so a historical build costs a few megabytes instead of a depot.
    ``ls`` supplies the chunk sizes and hashes that are not inside the dir file.
    """
    targets = list(dict.fromkeys(target.strip() for target in targets if target.strip()))
    if not targets:
        raise TrackerError("snapshot-needs-a-manifest")
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    log_dir = TRACKER_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"manifest-{_slug('-'.join(targets))}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log"

    get_command = [
        str(sfd), "get", app, *targets, "--output", str(cache), "--",
        "game/citadel/*_dir.vpk", "game/citadel/steam.inf",
    ]
    get = subprocess.run(
        get_command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )
    if get.returncode != 0:
        log_path.write_text(
            "$ " + " ".join(get_command) + "\n"
            + (get.stdout or "") + ("\n" + get.stderr if get.stderr else ""),
            encoding="utf-8",
        )
        raise _sfd_failure(get, "get")
    listing_command = [str(sfd), "ls", app, *targets, "--", "game/citadel/*.vpk"]
    listing = subprocess.run(
        listing_command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )
    log_path.write_text(
        "$ " + " ".join(get_command) + "\n"
        + (get.stdout or "") + ("\n" + get.stderr if get.stderr else "")
        + "\n$ " + " ".join(listing_command) + "\n"
        + (listing.stdout or "") + ("\n" + listing.stderr if listing.stderr else ""),
        encoding="utf-8",
    )
    if listing.returncode != 0:
        raise _sfd_failure(listing, "ls")
    rows = parse_sfd_rows(listing.stdout or "")
    by_manifest: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_manifest[(row["depot"], row["manifest"])].append(row)

    fetched = []
    for target in targets:
        if ":" not in target:
            raise TrackerError(f"manifest-target-wants-depot:manifest: {target}")
        depot, manifest = target.split(":", 1)
        root = cache / depot / manifest
        citadel = root / "game" / "citadel"
        vpks = sorted(path for path in citadel.glob("*_dir.vpk") if path.is_file())
        if not vpks:
            raise TrackerError(f"manifest-vpk-missing: {target}; see {log_path}")
        build, version_date = read_steam_inf(citadel / "steam.inf")
        manifest_rows = by_manifest.get((depot, manifest), [])
        chunks_by_vpk = {path.name: manifest_chunks(manifest_rows, path.name) for path in vpks}
        fetched.append(
            {
                "target": target,
                "app": app,
                "depot": depot,
                "manifest": manifest,
                "root": root,
                "vpks": vpks,
                "chunks_by_vpk": chunks_by_vpk,
                "build": build,
                "version_date": version_date,
                "log": log_path,
            }
        )
    return fetched


# ---------------------------------------------------------------------------
# Public build history and saved Steam login

_BUILD_LOCK = threading.Lock()
_BUILD_CACHE: dict = {"at": 0.0, "limit": 0, "rows": []}
_MANIFEST_ID_LOCK = threading.Lock()
_MANIFEST_ID_CACHE: dict[str, str] = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_CACHE: dict = {"at": 0.0, "logged_in": False, "known": False, "detail": ""}


def _http_text(url: str, *, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "openlock-vpk-tracker", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def parse_build_commit(commit: dict) -> dict | None:
    """Turn one GameTracking commit into a build row.

    GameTracking writes ``6864 | 2 files | M\\tgame/citadel/steam.inf, ...`` as
    the first line.  The manifest ID is not in the message; it is read from that
    commit's manifest file only when the owner asks to fetch the build.
    """
    metadata = commit.get("commit") or {}
    message = str(metadata.get("message") or "")
    first = message.splitlines()[0].strip() if message.splitlines() else ""
    parts = [part.strip() for part in first.split("|")]
    build = parts[0] if parts else ""
    if not re.fullmatch(r"\d{3,6}", build):
        return None
    changed = []
    if len(parts) >= 3:
        for item in parts[2].split(","):
            match = re.match(r"([AMDR])\s+(.+)", item.strip())
            if match:
                changed.append(
                    {"status": match.group(1), "path": match.group(2).replace("\\", "/")}
                )
    count = len(changed)
    if len(parts) >= 2:
        found = re.search(r"\d+", parts[1])
        if found:
            count = int(found.group(0))
    patch = re.search(r"https://steamdb\.info/patchnotes/\d+", message)
    sha = str(commit.get("sha") or "")
    return {
        "build": build,
        "sha": sha,
        "short_sha": sha[:7],
        "date": (metadata.get("committer") or {}).get("date")
        or (metadata.get("author") or {}).get("date")
        or "",
        "files_changed": count,
        "changed": changed[:40],
        "patch_url": patch.group(0) if patch else "",
        "commit_url": str(commit.get("html_url") or ""),
    }


def fetch_upstream_builds(limit: int = BUILD_HISTORY_LIMIT) -> list[dict]:
    limit = max(1, min(60, int(limit)))
    now = time.monotonic()
    with _BUILD_LOCK:
        if (
            _BUILD_CACHE["rows"]
            and _BUILD_CACHE["limit"] >= limit
            and now - _BUILD_CACHE["at"] < 300
        ):
            return list(_BUILD_CACHE["rows"])
    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/commits"
        f"?path={quote(GITHUB_MANIFEST_PATH, safe='/')}&per_page={limit}"
    )
    try:
        payload = json.loads(_http_text(url))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        with _BUILD_LOCK:
            if _BUILD_CACHE["rows"]:
                return list(_BUILD_CACHE["rows"])
        raise TrackerError("build-list-unavailable") from error
    if not isinstance(payload, list):
        raise TrackerError("build-list-unreadable")
    rows = []
    seen = set()
    for commit in payload:
        row = parse_build_commit(commit)
        if row is None or row["build"] in seen:
            continue
        seen.add(row["build"])
        rows.append(row)
        if len(rows) >= limit:
            break
    with _BUILD_LOCK:
        _BUILD_CACHE.update({"at": now, "limit": limit, "rows": rows})
    return rows


def fetch_manifest_id(sha: str) -> str:
    sha = (sha or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise TrackerError("build-sha-invalid")
    with _MANIFEST_ID_LOCK:
        if sha in _MANIFEST_ID_CACHE:
            return _MANIFEST_ID_CACHE[sha]
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{sha}/{GITHUB_MANIFEST_PATH}"
    try:
        text = _http_text(url)
    except OSError as error:
        raise TrackerError("build-manifest-unavailable") from error
    match = re.search(r"Manifest ID\s*/\s*date\s*:\s*(\d{1,25})", text)
    if match is None:
        raise TrackerError("build-manifest-unreadable")
    manifest = match.group(1)
    with _MANIFEST_ID_LOCK:
        _MANIFEST_ID_CACHE[sha] = manifest
    return manifest


def steam_login_status(*, refresh: bool = False) -> dict:
    now = time.monotonic()
    with _LOGIN_LOCK:
        if not refresh and now - _LOGIN_CACHE["at"] < 30:
            return dict(_LOGIN_CACHE)
    sfd = find_sfd()
    if sfd is None:
        status = {"at": now, "logged_in": False, "known": False, "detail": "Steam tools missing"}
    else:
        try:
            process = subprocess.run(
                [str(sfd), "login", "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            detail = ((process.stdout or "") + (process.stderr or "")).strip()
            logged = process.returncode == 0 and "no saved logins" not in detail.casefold()
            status = {
                "at": now,
                "logged_in": logged,
                "known": True,
                "detail": "Signed in" if logged else "Not signed in",
            }
        except (OSError, subprocess.SubprocessError):
            status = {"at": now, "logged_in": False, "known": False, "detail": "Steam status unavailable"}
    with _LOGIN_LOCK:
        _LOGIN_CACHE.update(status)
    return dict(status)


# ---------------------------------------------------------------------------
# Snapshots


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    return _SAFE.sub("-", value.strip()).strip("-").lower() or "snapshot"


def _relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def snapshot_summary(snapshot: dict, path: Path | None = None) -> dict:
    return {
        "id": snapshot["id"],
        "label": snapshot.get("label", ""),
        "created_at": snapshot.get("created_at", ""),
        "game": snapshot.get("game", ""),
        "build": snapshot.get("build", ""),
        "version_date": snapshot.get("version_date", ""),
        "digest": snapshot.get("digest", ""),
        "source": snapshot.get("source", {"kind": "local"}),
        "summary": snapshot.get("summary", {}),
        "vpks": [
            {
                "name": vpk["name"],
                "entry_count": vpk.get("entry_count", len(vpk.get("entries", []))),
                "size": vpk.get("size", 0),
                "mtime_ns": vpk.get("mtime_ns"),
                "blake3": vpk.get("blake3", ""),
            }
            for vpk in snapshot.get("vpks", [])
        ],
        "path": _relative(path) if path is not None else snapshot.get("path", ""),
    }


def build_snapshot(
    vpk_paths: list[Path],
    *,
    s2v: Path,
    label: str = "",
    game: str = "",
    build: str = "",
    version_date: str = "",
    pretty: bool = False,
    source: dict | None = None,
    chunks_by_vpk: dict[str, list[dict]] | None = None,
    identifier_suffix: str = "",
    guard: Callable[[], None] | None = None,
) -> tuple[Path, dict]:
    if not vpk_paths:
        raise TrackerError("snapshot-needs-a-vpk")
    created = utc_now()
    resolved_label = label.strip() or build.strip() or "snapshot"
    identifier = f"{_slug(created[:19])}-{_slug(resolved_label)}"
    if identifier_suffix.strip():
        identifier += "-" + _slug(identifier_suffix)
    unique_paths = list(dict.fromkeys(Path(path).resolve() for path in vpk_paths))
    vpks = [
        capture_vpk(
            s2v,
            path,
            chunks=chunks_by_vpk.get(path.name) if chunks_by_vpk is not None else None,
        )
        for path in unique_paths
    ]
    if guard is not None:
        guard()
    chunks = [
        {**chunk, "vpk": vpk["name"]}
        for vpk in vpks
        for chunk in vpk.get("chunks", [])
    ]
    snapshot = {
        "schema": SCHEMA,
        "id": identifier,
        "label": resolved_label,
        "created_at": created,
        "game": game,
        "build": build,
        "version_date": version_date,
        "source": source or {"kind": "local"},
        "s2v": {"path": str(s2v), "version": _s2v_version(s2v)},
        "summary": {
            "vpks": len(vpks),
            "entries": sum(vpk["entry_count"] for vpk in vpks),
            "chunks": len(chunks),
            "dir_bytes": sum(vpk["size"] for vpk in vpks),
        },
        "vpks": vpks,
        "chunks": chunks,
    }
    snapshot["digest"] = _digest(snapshot)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    target = SNAPSHOT_DIR / f"{identifier}.json"
    text = json.dumps(
        snapshot,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        ensure_ascii=False,
    )
    _write_text_atomic(target, text)
    update_index(snapshot, target)
    append_ledger(
        {
            "at": created,
            "command": "vpk_tracker snapshot",
            "result": "pass",
            "observed": (
                f"build {build or 'unknown'}, {snapshot['summary']['entries']} entries "
                f"across {len(vpks)} VPKs, digest {snapshot['digest']}"
            ),
            "artifacts": [_relative(target)],
        }
    )
    return target, snapshot


def _read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def update_index(snapshot: dict, path: Path) -> None:
    index = read_index(rebuild=False)
    rows = [
        row
        for row in index.get("snapshots", [])
        if row.get("id") != snapshot["id"]
    ]
    rows.append(snapshot_summary(snapshot, path))
    rows.sort(key=lambda row: (row.get("created_at", ""), row.get("id", "")))
    _write_text_atomic(
        INDEX_PATH,
        json.dumps(
            {"schema": SCHEMA, "updated_at": utc_now(), "snapshots": rows},
            indent=2,
        ),
    )


def rebuild_index() -> dict:
    rows = []
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        try:
            snapshot = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if snapshot.get("schema") != SCHEMA:
            continue
        rows.append(snapshot_summary(snapshot, path))
    rows.sort(key=lambda row: (row.get("created_at", ""), row.get("id", "")))
    index = {"schema": SCHEMA, "updated_at": utc_now(), "snapshots": rows}
    if rows:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def read_index(*, rebuild: bool = True) -> dict:
    if INDEX_PATH.is_file():
        try:
            index = _read_json(INDEX_PATH)
            if index.get("schema") == SCHEMA:
                return index
        except (OSError, json.JSONDecodeError):
            pass
    return rebuild_index() if rebuild else {"schema": SCHEMA, "snapshots": []}


def resolve_snapshot(reference: str, index: dict | None = None) -> dict:
    reference = (reference or "").strip()
    index = index or read_index()
    rows = index.get("snapshots", [])
    if not rows:
        raise TrackerError("no-snapshots: run `python tools/vpk_tracker.py snapshot` first")
    if reference in ("", "latest"):
        row = rows[-1]
    elif reference == "previous":
        if len(rows) < 2:
            raise TrackerError("no-previous-snapshot")
        row = rows[-2]
    else:
        path = Path(reference)
        if path.is_file():
            snapshot = _read_json(path)
            snapshot.setdefault("path", _relative(path))
            return snapshot
        row = next((item for item in rows if item["id"] == reference), None)
        if row is None:
            row = next((item for item in rows if item["id"].startswith(reference)), None)
        if row is None:
            row = next((item for item in rows if item.get("label") == reference), None)
        if row is None:
            raise TrackerError(f"snapshot-not-found: {reference}")
    path = Path(row["path"])
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise TrackerError(f"snapshot-file-missing: {path}")
    return _read_json(path)


def load_snapshot_by_id(identifier: str) -> dict:
    path = SNAPSHOT_DIR / f"{identifier}.json"
    if not path.is_file():
        raise TrackerError(f"snapshot-file-missing: {path}")
    return _read_json(path)


# ---------------------------------------------------------------------------
# Diff


def _entry_map(entries: list[list]) -> dict[str, list]:
    return {entry[0].replace("\\", "/").casefold(): entry for entry in entries}


def _top_folder(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "(root)"


def _extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else "(none)"


def _chunk_changed(before: dict, after: dict) -> bool:
    if before.get("size") != after.get("size"):
        return True
    if before.get("sha1") and after.get("sha1"):
        return before["sha1"] != after["sha1"]
    if before.get("mtime_ns") is not None and after.get("mtime_ns") is not None:
        return before["mtime_ns"] != after["mtime_ns"]
    return False


def diff_snapshots(old: dict | None, new: dict) -> dict:
    """Content diff between two captured snapshots.

    ``old is None`` produces a baseline inventory: every entry is a row, but it
    is labelled ``baseline`` rather than pretending the files were added by an
    update that was never observed.  Build metadata is recorded separately so
    a build-only patch is not reported as an identical pair.
    """
    old_vpks = {vpk["name"]: vpk for vpk in (old or {}).get("vpks", [])}
    new_vpks = {vpk["name"]: vpk for vpk in new.get("vpks", [])}
    build = {
        "before": str((old or {}).get("build") or ""),
        "after": str(new.get("build") or ""),
        "version_date_before": str((old or {}).get("version_date") or ""),
        "version_date_after": str(new.get("version_date") or ""),
        "changed": bool(old) and str(old.get("build") or "") != str(new.get("build") or ""),
    }
    rows: list[dict] = []
    vpk_summary: list[dict] = []
    counts = Counter()

    for name in sorted(set(old_vpks) | set(new_vpks)):
        before = old_vpks.get(name)
        after = new_vpks.get(name)
        old_entries = _entry_map(before.get("entries", [])) if before else {}
        new_entries = _entry_map(after.get("entries", [])) if after else {}
        local = Counter()
        for key in sorted(set(old_entries) | set(new_entries)):
            old_entry = old_entries.get(key)
            new_entry = new_entries.get(key)
            if old_entry is None:
                path, crc, size, fnum, offset = new_entry
                rows.append(
                    {
                        "kind": "added",
                        "vpk": name,
                        "path": path,
                        "old_crc": None,
                        "new_crc": crc,
                        "old_size": None,
                        "new_size": size,
                        "delta": size,
                        "fnum": fnum,
                        "offset": offset,
                    }
                )
                local["added"] += 1
            elif new_entry is None:
                path, crc, size, fnum, offset = old_entry
                rows.append(
                    {
                        "kind": "removed",
                        "vpk": name,
                        "path": path,
                        "old_crc": crc,
                        "new_crc": None,
                        "old_size": size,
                        "new_size": None,
                        "delta": -size,
                        "fnum": fnum,
                        "offset": offset,
                    }
                )
                local["removed"] += 1
            elif old_entry[1] != new_entry[1] or old_entry[2] != new_entry[2]:
                rows.append(
                    {
                        "kind": "modified",
                        "vpk": name,
                        "path": new_entry[0],
                        "old_crc": old_entry[1],
                        "new_crc": new_entry[1],
                        "old_size": old_entry[2],
                        "new_size": new_entry[2],
                        "delta": new_entry[2] - old_entry[2],
                        "fnum": new_entry[3],
                        "offset": new_entry[4],
                    }
                )
                local["modified"] += 1
            elif old_entry[3] != new_entry[3] or old_entry[4] != new_entry[4]:
                local["repacked"] += 1
            else:
                local["unchanged"] += 1
        counts.update(local)
        vpk_summary.append(
            {
                "name": name,
                "present_before": before is not None,
                "present_after": after is not None,
                "entries_before": len(old_entries),
                "entries_after": len(new_entries),
                "added": local["added"],
                "removed": local["removed"],
                "modified": local["modified"],
                "repacked": local["repacked"],
                "unchanged": local["unchanged"],
                "dir_blake3_before": (before or {}).get("blake3", ""),
                "dir_blake3_after": (after or {}).get("blake3", ""),
            }
        )

    baseline = old is None
    if baseline:
        rows = [
            {
                "kind": "baseline",
                "vpk": vpk["name"],
                "path": entry[0],
                "old_crc": None,
                "new_crc": entry[1],
                "old_size": None,
                "new_size": entry[2],
                "delta": entry[2],
                "fnum": entry[3],
                "offset": entry[4],
            }
            for vpk in new.get("vpks", [])
            for entry in vpk.get("entries", [])
        ]
        counts = Counter({"baseline": len(rows), "unchanged": 0})
        for row in vpk_summary:
            row.update({"added": 0, "removed": 0, "modified": 0, "repacked": 0, "unchanged": row["entries_after"]})

    old_chunks = {(chunk.get("vpk", ""), chunk["name"]): chunk for chunk in (old or {}).get("chunks", [])}
    new_chunks_map = {(chunk.get("vpk", ""), chunk["name"]): chunk for chunk in new.get("chunks", [])}
    added_chunks = [] if baseline else [chunk for key, chunk in new_chunks_map.items() if key not in old_chunks]
    removed_chunks = [] if baseline else [chunk for key, chunk in old_chunks.items() if key not in new_chunks_map]
    changed_chunks = [] if baseline else [
        {
            **chunk,
            "old_size": old_chunks[key].get("size", 0),
            "old_sha1": old_chunks[key].get("sha1", ""),
            "old_mtime_ns": old_chunks[key].get("mtime_ns"),
        }
        for key, chunk in new_chunks_map.items()
        if key in old_chunks and _chunk_changed(old_chunks[key], chunk)
    ]
    added_chunks.sort(key=lambda chunk: chunk["name"])
    changed_chunks.sort(key=lambda chunk: chunk["name"])
    removed_chunks.sort(key=lambda chunk: chunk["name"])

    groups = {}
    for kind in ("added", "removed", "modified"):
        selected = [row for row in rows if row["kind"] == kind]
        groups[kind] = {
            "folders": Counter(_top_folder(row["path"]) for row in selected).most_common(30),
            "extensions": Counter(_extension(row["path"]) for row in selected).most_common(30),
        }

    bytes_added = sum(row["new_size"] for row in rows if row["kind"] == "added")
    bytes_removed = sum(row["old_size"] for row in rows if row["kind"] == "removed")
    summary = {
        "added": counts["added"],
        "removed": counts["removed"],
        "modified": counts["modified"],
        "repacked": counts["repacked"],
        "unchanged": counts["unchanged"],
        "baseline": len(rows) if baseline else 0,
        "rows": len(rows),
        "bytes_added": bytes_added,
        "bytes_removed": bytes_removed,
        "bytes_delta": sum(row["delta"] for row in rows if row["kind"] != "baseline"),
        "new_chunks": len(added_chunks),
        "changed_chunks": len(changed_chunks),
        "build_changed": build["changed"],
    }
    report = {
        "schema": SCHEMA,
        "from": snapshot_summary(old) if old else None,
        "to": snapshot_summary(new),
        "baseline": baseline,
        "build": build,
        "summary": summary,
        "vpks": vpk_summary,
        "groups": groups,
        "new_chunks": added_chunks,
        "changed_chunks": changed_chunks,
        "removed_chunks": removed_chunks,
        "rows": rows,
    }
    report["digest"] = _digest(
        {
            "from": report["from"]["id"] if report["from"] else "",
            "to": report["to"]["id"],
            "build": build,
            "summary": summary,
            "vpks": vpk_summary,
            "rows": rows,
        }
    )
    return report


def _format_bytes(value: int) -> str:
    sign = "+" if value > 0 else ""
    size = float(abs(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for index, unit in enumerate(units):
        if size < 1024 or unit == "TiB":
            return f"{sign}{size:,.1f} {unit}"
        size /= 1024
    return f"{sign}{size:,.1f} TiB"


def diff_text(report: dict, limit: int = 20) -> str:
    old = report.get("from")
    new = report.get("to")
    summary = report["summary"]
    if report.get("baseline"):
        return "\n".join(
            [
                f"baseline {new['label']}  build {new['build']}",
                f"{summary['baseline']:,} entries across {len(report['vpks'])} VPKs  "
                f"{len(new.get('vpks', []))} directory files",
                "no previous snapshot: this is the inventory the next capture will be compared against",
            ]
        )
    head = f"{old['label'] if old else 'baseline'} -> {new['label']}"
    lines = [
        f"{head}  build {old['build'] if old else '-'} -> {new['build']}",
        f"added {summary['added']:,}  removed {summary['removed']:,}  modified {summary['modified']:,}  "
        f"repacked {summary['repacked']:,}  unchanged {summary['unchanged']:,}",
        f"bytes +{_format_bytes(summary['bytes_added']).lstrip('+')} / "
        f"{_format_bytes(-summary['bytes_removed'])}  net {_format_bytes(summary['bytes_delta'])}",
    ]
    if report["new_chunks"]:
        lines.append("new chunks: " + ", ".join(chunk["name"] for chunk in report["new_chunks"][:limit]))
    for row in report["vpks"]:
        if row["added"] or row["removed"] or row["modified"]:
            lines.append(
                f"{row['name']}: +{row['added']:,} -{row['removed']:,} ~{row['modified']:,} "
                f"({row['entries_after']:,} entries)"
            )
    if (
        not (summary["added"] or summary["removed"] or summary["modified"] or summary["repacked"])
        and not (report["new_chunks"] or report["changed_chunks"] or report["removed_chunks"])
    ):
        lines.append("no VPK entries changed" + ("; build metadata changed" if report["build"]["changed"] else ""))
    for kind in ("added", "modified", "removed"):
        selected = [row for row in report["rows"] if row["kind"] == kind][:limit]
        if not selected:
            continue
        lines.append(f"\n{kind}:")
        for row in selected:
            detail = ""
            if kind == "modified":
                detail = f"  {row['old_size']:,} -> {row['new_size']:,} B"
            elif kind == "added":
                detail = f"  {row['new_size']:,} B"
            else:
                detail = f"  {row['old_size']:,} B"
            lines.append(f"  {row['vpk']}  {row['path']}{detail}")
    return "\n".join(lines)


def _append_ledger(row: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


def append_ledger(row: dict) -> None:
    _append_ledger(row)


# ---------------------------------------------------------------------------
# Local UI server

_SNAPSHOT_CACHE: dict[str, tuple[int, dict]] = {}
_DIFF_CACHE: dict[tuple[str, str], dict] = {}
_DIFF_LOCK = threading.Lock()


def _load_snapshot_cached(identifier: str) -> dict:
    path = SNAPSHOT_DIR / f"{identifier}.json"
    stat = path.stat()
    cached = _SNAPSHOT_CACHE.get(identifier)
    if cached and cached[0] == stat.st_mtime_ns:
        return cached[1]
    snapshot = _read_json(path)
    if len(_SNAPSHOT_CACHE) > 6:
        _SNAPSHOT_CACHE.clear()
    _SNAPSHOT_CACHE[identifier] = (stat.st_mtime_ns, snapshot)
    return snapshot


def _cached_diff(old_id: str, new_id: str) -> dict:
    key = (old_id, new_id)
    with _DIFF_LOCK:
        if key in _DIFF_CACHE:
            return _DIFF_CACHE[key]
    old = _load_snapshot_cached(old_id) if old_id else None
    new = _load_snapshot_cached(new_id)
    report = diff_snapshots(old, new)
    with _DIFF_LOCK:
        if len(_DIFF_CACHE) > 4:
            _DIFF_CACHE.clear()
        _DIFF_CACHE[key] = report
    return report


_HISTORY_LOCK = threading.Lock()
_HISTORY_CACHE: dict = {"key": None, "rows": []}


def history_rows() -> list[dict]:
    """Snapshot rows with the stats of each version against its predecessor.

    This is the commit-log view: every captured version keeps its own row, and
    a live capture never rewrites the previous one.
    """
    index = read_index()
    rows = index.get("snapshots", [])
    key = (index.get("updated_at", ""), tuple(row.get("id", "") for row in rows))
    with _HISTORY_LOCK:
        if _HISTORY_CACHE["key"] == key:
            return list(_HISTORY_CACHE["rows"])
    result = []
    previous = None
    for row in rows:
        item = dict(row)
        item["stats"] = None
        if previous is not None:
            try:
                report = _cached_diff(previous.get("id", ""), row.get("id", ""))
                summary = report.get("summary", {})
                item["stats"] = {
                    "added": summary.get("added", 0),
                    "removed": summary.get("removed", 0),
                    "modified": summary.get("modified", 0),
                    "repacked": summary.get("repacked", 0),
                    "chunks": summary.get("new_chunks", 0) + summary.get("changed_chunks", 0),
                    "bytes_delta": summary.get("bytes_delta", 0),
                    "build_changed": bool(report.get("build", {}).get("changed")),
                }
            except (OSError, json.JSONDecodeError, TrackerError):
                item["stats"] = None
        result.append(item)
        previous = row
    with _HISTORY_LOCK:
        _HISTORY_CACHE.update({"key": key, "rows": result})
    return list(result)


_JOB_LOCK = threading.Lock()
_JOB: dict = {
    "id": "",
    "action": "",
    "label": "",
    "status": "idle",
    "started_at": "",
    "ended_at": "",
    "exit_code": None,
    "log": "",
    "pid": None,
}


def _job_public() -> dict:
    with _JOB_LOCK:
        job = dict(_JOB)
    log_path = Path(job["log"]) if job.get("log") else None
    if log_path and log_path.is_file():
        try:
            job["log_tail"] = log_path.read_text(encoding="utf-8", errors="replace")[-5000:]
        except OSError:
            job["log_tail"] = ""
        job["log"] = _relative(log_path)
    else:
        job["log_tail"] = ""
    return job


def _job_worker(job_id: str, command: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exit_code = 1
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        try:
            log.write("$ " + " ".join(command) + "\n")
            log.flush()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            with _JOB_LOCK:
                if _JOB.get("id") == job_id:
                    _JOB["pid"] = process.pid
            exit_code = process.wait()
        except Exception:  # noqa: BLE001 - the log is the only place this can be reported
            log.write("\n" + traceback.format_exc())
            exit_code = 1
    with _JOB_LOCK:
        if _JOB.get("id") != job_id:
            return
        _JOB["status"] = "done" if exit_code == 0 else "failed"
        _JOB["ended_at"] = utc_now()
        _JOB["exit_code"] = exit_code


def _start_job(action: str, command: list[str], label: str) -> dict:
    with _JOB_LOCK:
        if _JOB.get("status") == "running":
            raise TrackerError("job-already-running")
        job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = LAUNCH_LOGS / f"launcher-{job_id}.log"
        _JOB.update(
            {
                "id": job_id,
                "action": action,
                "label": label,
                "status": "running",
                "started_at": utc_now(),
                "ended_at": "",
                "exit_code": None,
                "log": str(log_path),
                "pid": None,
            }
        )
    thread = threading.Thread(
        target=_job_worker,
        args=(job_id, command, log_path),
        name="vpk-launcher",
        daemon=True,
    )
    thread.start()
    return _job_public()


def start_local_snapshot(*, stable: bool = False) -> dict:
    command = [sys.executable, str(Path(__file__).resolve()), "snapshot"]
    if stable:
        command.append("--wait-stable")
    return _start_job("snapshot", command, "installed build")


def start_manifest_snapshot(target: str) -> dict:
    target = target.strip()
    if not re.fullmatch(r"\d{1,20}:\d{1,25}", target):
        raise TrackerError("manifest-target-wants-depot:manifest")
    command = [sys.executable, str(Path(__file__).resolve()), "snapshot", "--manifest", target]
    return _start_job("manifest", command, f"manifest {target}")


def open_steam_login_window() -> None:
    if os.name != "nt":
        raise TrackerError("steam-login-window-needs-windows")
    sfd = find_sfd()
    if sfd is None:
        raise TrackerError("steam-file-downloader-missing")
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen([str(sfd), "login"], cwd=ROOT, creationflags=flags)


class TrackerHandler(BaseHTTPRequestHandler):
    server_version = "OpenLockVPKTracker/1"

    def log_message(self, format, *args):  # noqa: A002 - base class signature
        return

    def _json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name: str) -> None:
        path = UI_DIR / name
        if not path.is_file():
            self._json({"error": "not-found"}, HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as error:
            raise TrackerError("bad-content-length") from error
        if length > 32768:
            raise TrackerError("request-too-large")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TrackerError("bad-json") from error
        if not isinstance(payload, dict):
            raise TrackerError("json-object-required")
        return payload

    def _mutation_allowed(self) -> bool:
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            return False
        origin = self.headers.get("Origin", "")
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.hostname in ("127.0.0.1", "localhost") and parsed.port == self.server.server_port

    def do_POST(self) -> None:  # noqa: N802 - base class signature
        parsed = urlparse(self.path)
        if not self._mutation_allowed():
            self._json({"error": "local-only"}, HTTPStatus.FORBIDDEN)
            return
        try:
            payload = self._read_json()
            if parsed.path == "/api/jobs":
                action = str(payload.get("action", "")).strip()
                if action == "snapshot":
                    job = start_local_snapshot(stable=True)
                elif action == "manifest":
                    target = str(payload.get("manifest", "")).strip()
                    sha = str(payload.get("sha", "")).strip()
                    if not target and sha:
                        target = f"{DEFAULT_DEPOT}:{fetch_manifest_id(sha)}"
                    job = start_manifest_snapshot(target)
                else:
                    raise TrackerError("unknown-launcher-action")
                self._json({"job": job}, HTTPStatus.ACCEPTED)
                return
            if parsed.path == "/api/login":
                open_steam_login_window()
                self._json(
                    {
                        "ok": True,
                        "message": "Steam login window opened. Scan the QR code there with the Steam mobile app.",
                    }
                )
                return
            self._json({"error": "not-found"}, HTTPStatus.NOT_FOUND)
        except TrackerError as error:
            status = HTTPStatus.CONFLICT if str(error) == "job-already-running" else HTTPStatus.BAD_REQUEST
            self._json({"error": str(error)}, status)
        except OSError as error:
            self._json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self) -> None:  # noqa: N802 - base class signature
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._json({"ok": True, "schema": SCHEMA})
            return
        if path == "/api/jobs/current":
            self._json({"job": _job_public()})
            return
        if path == "/api/launcher":
            try:
                env = detect()
                s2v = str(env.s2v) if env.s2v else ""
                game = str(env.game_dir) if env.game_dir else ""
            except (TrackerError, OSError):
                s2v = ""
                game = ""
            sfd = find_sfd()
            refresh_login = parse_qs(parsed.query).get("login", [""])[0] == "refresh"
            login = steam_login_status(refresh=refresh_login)
            self._json(
                {
                    "schema": SCHEMA,
                    "s2v": s2v,
                    "game": game,
                    "sfd": str(sfd) if sfd else "",
                    "cache": _relative(DEFAULT_MANIFESTS),
                    "snapshots": len(read_index().get("snapshots", [])),
                    "login_window": os.name == "nt",
                    "logged_in": login.get("logged_in", False),
                    "login": login,
                    "job": _job_public(),
                }
            )
            return
        if path == "/api/live":
            self._json({"schema": SCHEMA, **live_public()})
            return
        if path == "/api/login/status":
            self._json({"schema": SCHEMA, **steam_login_status(refresh=True)})
            return
        if path == "/api/history":
            self._json(
                {
                    "schema": SCHEMA,
                    "snapshots": history_rows(),
                    "login": steam_login_status(),
                    "job": _job_public(),
                }
            )
            return
        if path == "/api/builds":
            try:
                limit = int(parse_qs(parsed.query).get("limit", [str(BUILD_HISTORY_LIMIT)])[0])
            except ValueError:
                limit = BUILD_HISTORY_LIMIT
            try:
                builds = fetch_upstream_builds(limit)
            except TrackerError as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
                return
            captured = {}
            for row in read_index().get("snapshots", []):
                if row.get("build"):
                    captured[str(row["build"])] = row
            for row in builds:
                match = captured.get(str(row["build"]))
                row["snapshot_id"] = match.get("id", "") if match else ""
                row["snapshot_source"] = (match.get("source") or {}).get("kind", "") if match else ""
            self._json(
                {
                    "schema": SCHEMA,
                    "builds": builds,
                    "login": steam_login_status(),
                }
            )
            return
        if path == "/api/snapshots":
            index = read_index()
            rows = index.get("snapshots", [])
            self._json(
                {
                    "schema": SCHEMA,
                    "latest": rows[-1]["id"] if rows else None,
                    "previous": rows[-2]["id"] if len(rows) > 1 else None,
                    "snapshots": rows,
                }
            )
            return
        if path == "/api/diff":
            self._diff(parsed.query)
            return
        if path in ("/", "/index.html"):
            self._file("index.html")
            return
        if path in ("/app.css", "/app.js"):
            self._file(path[1:])
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self._json({"error": "not-found"}, HTTPStatus.NOT_FOUND)

    def _diff(self, query: str) -> None:
        params = parse_qs(query)
        get = lambda key, default="": params.get(key, [default])[0]  # noqa: E731
        index = read_index()
        rows = index.get("snapshots", [])
        if not rows:
            self._json({"error": "no-snapshots"}, HTTPStatus.CONFLICT)
            return
        to_id = get("to") or rows[-1]["id"]
        to_index = next((index for index, row in enumerate(rows) if row["id"] == to_id), -1)
        from_id = get("from")
        if not from_id:
            from_id = rows[to_index - 1]["id"] if to_index > 0 else ""
        if from_id == to_id:
            from_id = rows[to_index - 1]["id"] if to_index > 0 else ""
        known = {row["id"] for row in rows}
        if to_id not in known or (from_id and from_id not in known):
            self._json({"error": "snapshot-not-found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            report = _cached_diff(from_id, to_id)
        except (OSError, json.JSONDecodeError, TrackerError) as error:
            self._json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        vpk = get("vpk", "all")
        kind = get("kind", "all")
        search = get("q", "").strip().casefold()
        selected = report["rows"]
        if vpk != "all":
            selected = [row for row in selected if row["vpk"] == vpk]
        if kind != "all":
            selected = [row for row in selected if row["kind"] == kind]
        if search:
            selected = [row for row in selected if search in row["path"].casefold()]
        sort = get("sort", "path")
        if sort == "delta":
            selected = sorted(selected, key=lambda row: abs(row["delta"]), reverse=True)
        else:
            selected = sorted(selected, key=lambda row: row["path"].casefold())
        try:
            limit = max(1, min(500, int(get("limit", "200"))))
            offset = max(0, int(get("offset", "0")))
        except ValueError:
            self._json({"error": "bad-pagination"}, HTTPStatus.BAD_REQUEST)
            return
        page = selected[offset : offset + limit]
        self._json(
            {
                "schema": SCHEMA,
                "from": report["from"],
                "to": report["to"],
                "baseline": report["baseline"],
                "digest": report["digest"],
                "build": report["build"],
                "summary": report["summary"],
                "vpks": report["vpks"],
                "groups": report["groups"],
                "new_chunks": report["new_chunks"],
                "changed_chunks": report["changed_chunks"],
                "removed_chunks": report["removed_chunks"],
                "filtered": len(selected),
                "offset": offset,
                "limit": limit,
                "rows": page,
            }
        )


def _tracker_alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=2) as response:
            if response.status != HTTPStatus.OK:
                return False
            return json.loads(response.read().decode("utf-8")).get("schema") == SCHEMA
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def serve(
    host: str,
    port: int,
    *,
    open_browser: bool = False,
    reuse: bool = False,
    watch: bool = True,
) -> int:
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    url = f"http://{browser_host}:{port}/"
    if reuse and _tracker_alive(url):
        print(f"VPK tracker already running {url}")
        if open_browser:
            webbrowser.open(url)
        return 0
    try:
        server = ThreadingHTTPServer((host, port), TrackerHandler)
    except OSError as error:
        print(f"port-in-use: {error}", file=sys.stderr)
        return 2
    print(f"VPK tracker {url}")
    print(f"snapshots {SNAPSHOT_DIR}")
    if not read_index().get("snapshots"):
        print("no snapshots yet; use the launcher panel to capture the installed build")
    stop_watch = start_live_watcher() if watch else None
    if stop_watch is not None:
        print("live watch on")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if stop_watch is not None:
            stop_watch.set()
        server.server_close()
    return 0


# ---------------------------------------------------------------------------
# CLI


def _default_vpks(game_dir: Path, include_addons: bool) -> list[Path]:
    citadel = game_dir / "citadel"
    paths = sorted(citadel.glob("*_dir.vpk"))
    if include_addons:
        paths.extend(sorted((citadel / "addons").rglob("*_dir.vpk")))
    return [path for path in paths if path.is_file()]


# ---------------------------------------------------------------------------
# Live local-build watch

_LIVE_LOCK = threading.Lock()
_LIVE: dict = {
    "enabled": False,
    "watching": False,
    "state": "starting",
    "build": "",
    "version_date": "",
    "message": "Checking game…",
    "latest_local": "",
    "candidate_build": "",
    "candidate_at": "",
    "capture_job": "",
    "last_capture": "",
    "last_capture_at": "",
    "last_capture_build": "",
    "last_capture_status": "",
    "last_error": "",
}


def _live_update(**fields) -> None:
    with _LIVE_LOCK:
        _LIVE.update(fields)


def live_public() -> dict:
    with _LIVE_LOCK:
        payload = dict(_LIVE)
    payload["job"] = _job_public()
    return payload


def _file_signature(path: Path) -> list:
    try:
        stat = Path(path).stat()
    except OSError:
        return [Path(path).name, -1, -1]
    return [Path(path).name, stat.st_size, stat.st_mtime_ns]


def local_signature(env) -> dict:
    if env.game_dir is None:
        raise TrackerError("deadlock-missing")
    game_dir = Path(env.game_dir)
    citadel = game_dir / "citadel"
    return {
        "build": str(env.build or ""),
        "version_date": str(env.version_date or ""),
        "game_dir": str(game_dir),
        "vpks": [_file_signature(path) for path in _default_vpks(game_dir, False)],
        "steam_inf": _file_signature(citadel / "steam.inf"),
    }


def _signature_matches_snapshot(signature: dict, snapshot: dict) -> bool:
    if str(snapshot.get("build") or "") != signature["build"]:
        return False
    saved = {
        vpk.get("name"): (vpk.get("size"), vpk.get("mtime_ns"))
        for vpk in snapshot.get("vpks", [])
    }
    current = {name: (size, mtime) for name, size, mtime in signature["vpks"]}
    return saved == current


def _files_signature(vpks: list[Path], steam_inf: Path) -> list:
    return [
        [_file_signature(path) for path in vpks],
        _file_signature(steam_inf),
    ]


def _wait_for_stable(
    vpks: list[Path],
    steam_inf: Path,
    *,
    settle: float = 1.2,
    timeout: float = 20.0,
) -> list:
    deadline = time.monotonic() + timeout
    previous = None
    while True:
        current = _files_signature(vpks, steam_inf)
        if current == previous:
            return current
        previous = current
        if time.monotonic() >= deadline:
            break
        time.sleep(settle)
    raise TrackerError("game-not-stable: the install is still changing")


def _guard_signature(vpks: list[Path], steam_inf: Path, expected: list) -> None:
    if _files_signature(vpks, steam_inf) != expected:
        raise TrackerError("game-changed-during-snapshot")


def _latest_local_row(index: dict) -> dict | None:
    row = next(
        (
            row
            for row in reversed(index.get("snapshots", []))
            if (row.get("source") or {}).get("kind") == "local"
        ),
        None,
    )
    if row is None:
        return None
    # The index summary omits VPK mtimes; the live signature needs them.
    return _load_snapshot_cached(row["id"])


def _last_job_line(job: dict) -> str:
    lines = [line.strip() for line in str(job.get("log_tail") or "").splitlines() if line.strip()]
    return lines[-1][:240] if lines else "See the launcher log"


def _live_watcher(stop: threading.Event) -> None:
    """Watch the installed build while the tracker server is open.

    A stat signature is cheap enough to sample every two seconds.  A changed
    signature has to stay unchanged for a settle interval before the same
    guarded snapshot command the launcher uses is started.  There is at most one
    job, so a patch that lands during a manifest fetch is picked up afterwards.
    """
    candidate = None
    candidate_since = 0.0
    retry_after = 0.0
    _live_update(enabled=True, watching=False, state="starting", message="Checking game…")
    while not stop.is_set():
        try:
            env = detect()
            if env.game_dir is None:
                _live_update(
                    watching=False,
                    state="unavailable",
                    build="",
                    message="Game not found",
                    latest_local="",
                    candidate_build="",
                )
                stop.wait(LIVE_POLL_SECONDS)
                continue
            if env.s2v is None:
                _live_update(
                    watching=False,
                    state="unavailable",
                    build=str(env.build or ""),
                    message="Viewer missing",
                    latest_local="",
                )
                stop.wait(LIVE_POLL_SECONDS)
                continue

            signature = local_signature(env)
            latest = _latest_local_row(read_index())
            job = _job_public()
            capture_job = str(_LIVE.get("capture_job") or "")

            if capture_job and job.get("id") == capture_job:
                if job.get("status") == "running":
                    _live_update(
                        watching=True,
                        state="capturing",
                        build=signature["build"],
                        version_date=signature["version_date"],
                        message=f"Capturing build {signature['build']}…",
                        latest_local=latest["id"] if latest else "",
                    )
                    stop.wait(LIVE_POLL_SECONDS)
                    continue
                if job.get("status") == "done":
                    _live_update(
                        watching=True,
                        state="watching",
                        message=f"Build {signature['build']} captured",
                        latest_local=latest["id"] if latest else "",
                        capture_job="",
                        last_capture=job.get("id", ""),
                        last_capture_at=job.get("ended_at", ""),
                        last_capture_build=signature["build"],
                        last_capture_status="done",
                        last_error="",
                    )
                    candidate = None
                    candidate_since = 0.0
                elif job.get("status") == "failed":
                    retry_after = time.monotonic() + 30
                    _live_update(
                        watching=True,
                        state="error",
                        message="Patch capture failed",
                        capture_job="",
                        last_capture=job.get("id", ""),
                        last_capture_at=job.get("ended_at", ""),
                        last_capture_build=signature["build"],
                        last_capture_status="failed",
                        last_error=_last_job_line(job),
                    )
                    candidate = None
                    candidate_since = 0.0

            if latest is None:
                _live_update(
                    watching=True,
                    state="needs-first",
                    build=signature["build"],
                    version_date=signature["version_date"],
                    message="Snapshot the installed game once",
                    latest_local="",
                    candidate_build="",
                    last_error="",
                )
                stop.wait(LIVE_POLL_SECONDS)
                continue

            if _signature_matches_snapshot(signature, latest):
                _live_update(
                    watching=True,
                    state="watching",
                    build=signature["build"],
                    version_date=signature["version_date"],
                    latest_local=latest["id"],
                    message=f"Live · build {signature['build']}",
                    candidate_build="",
                    last_error="",
                )
                candidate = None
                candidate_since = 0.0
                stop.wait(LIVE_POLL_SECONDS)
                continue

            if time.monotonic() < retry_after:
                stop.wait(LIVE_POLL_SECONDS)
                continue

            if candidate != signature:
                candidate = signature
                candidate_since = time.monotonic()
                _live_update(
                    watching=True,
                    state="settling",
                    build=signature["build"],
                    version_date=signature["version_date"],
                    latest_local=latest["id"],
                    message=f"Patch detected · build {signature['build']}…",
                    candidate_build=signature["build"],
                    candidate_at=utc_now(),
                    last_error="",
                )
            elif time.monotonic() - candidate_since >= LIVE_SETTLE_SECONDS:
                if job.get("status") == "running":
                    _live_update(
                        watching=True,
                        state="waiting",
                        message="Waiting for current job",
                        latest_local=latest["id"],
                    )
                    stop.wait(LIVE_POLL_SECONDS)
                    continue
                try:
                    started = start_local_snapshot(stable=True)
                    _live_update(
                        watching=True,
                        state="capturing",
                        build=signature["build"],
                        version_date=signature["version_date"],
                        message=f"Capturing build {signature['build']}…",
                        latest_local=latest["id"],
                        candidate_build="",
                        capture_job=started["id"],
                        last_capture=started["id"],
                        last_capture_at="",
                        last_capture_build=signature["build"],
                        last_capture_status="running",
                        last_error="",
                    )
                    candidate = None
                    candidate_since = 0.0
                except TrackerError as error:
                    if str(error) == "job-already-running":
                        _live_update(
                            watching=True,
                            state="waiting",
                            message="Waiting for current job",
                            latest_local=latest["id"],
                        )
                    else:
                        retry_after = time.monotonic() + 20
                        _live_update(
                            watching=True,
                            state="error",
                            message="Patch capture failed",
                            last_error=str(error)[:300],
                        )
        except (OSError, TrackerError, json.JSONDecodeError) as error:
            _live_update(
                watching=False,
                state="error",
                message="Patch watch failed",
                last_error=str(error)[:300],
            )
        stop.wait(LIVE_POLL_SECONDS)


def start_live_watcher() -> threading.Event:
    stop = threading.Event()
    thread = threading.Thread(target=_live_watcher, args=(stop,), name="vpk-live", daemon=True)
    thread.start()
    return stop


def cmd_snapshot(args: argparse.Namespace) -> int:
    env = detect(deadlock_root=args.game or None, s2v_cli=args.s2v or None)
    s2v = Path(args.s2v) if args.s2v else env.s2v
    if s2v is None:
        print("source-2-viewer-missing: choose Source2Viewer-CLI.exe", file=sys.stderr)
        return 2

    if args.manifest:
        sfd = find_sfd(args.sfd or None)
        if sfd is None:
            print(
                "steam-file-downloader-missing: pass --sfd or place SteamFileDownloader.exe in "
                f"{SFD_CANDIDATES[0].parent}",
                file=sys.stderr,
            )
            return 2
        cache = Path(args.depot_output) if args.depot_output else DEFAULT_MANIFESTS
        try:
            fetched = fetch_manifests(sfd, args.app, args.manifest, cache)
        except (TrackerError, OSError, subprocess.SubprocessError) as error:
            print(f"snapshot-failed: {error}", file=sys.stderr)
            return 2
        written = []
        for item in fetched:
            base = args.label or (f"build {item['build']}" if item["build"] else f"manifest {item['manifest'][-8:]}")
            source = {
                "kind": "manifest",
                "app": item["app"],
                "depot": item["depot"],
                "manifest": item["manifest"],
                "cache": str(item["root"]),
                "log": _relative(item["log"]),
            }
            try:
                target, snapshot = build_snapshot(
                    item["vpks"],
                    s2v=s2v,
                    label=base,
                    game=str(item["root"]),
                    build=item["build"],
                    version_date=item["version_date"],
                    pretty=args.pretty,
                    source=source,
                    chunks_by_vpk=item["chunks_by_vpk"],
                    identifier_suffix=f"m{item['manifest'][-8:]}",
                )
            except (TrackerError, OSError, subprocess.SubprocessError) as error:
                print(f"snapshot-failed: {item['target']}: {error}", file=sys.stderr)
                return 2
            written.append((target, snapshot))
            print(f"snapshot {target}")
            print(
                f"manifest {item['depot']}:{item['manifest']}  build {snapshot['build'] or 'unknown'}  "
                f"{snapshot['summary']['entries']:,} entries across {len(snapshot['vpks'])} VPKs"
            )
            for vpk in snapshot["vpks"]:
                print(
                    f"  {vpk['name']:24} {vpk['entry_count']:>8,} entries  "
                    f"{len(vpk.get('chunks', []))} chunks  {vpk['blake3']}"
                )
        return 0 if written else 2

    if args.vpk:
        vpks = [Path(value) for value in args.vpk]
    else:
        if env.game_dir is None:
            print("deadlock-missing: pass --game or set DEADLOCK_GAME", file=sys.stderr)
            return 2
        vpks = _default_vpks(env.game_dir, args.include_addons)
    vpks = [path.resolve() for path in vpks]
    if not vpks:
        print("no *_dir.vpk files found", file=sys.stderr)
        return 2
    guard = None
    if args.wait_stable:
        steam_inf = (Path(env.game_dir) / "citadel" / "steam.inf") if env.game_dir else vpks[0].parent / "steam.inf"
        try:
            expected = _wait_for_stable(vpks, steam_inf)
        except TrackerError as error:
            print(f"snapshot-failed: {error}", file=sys.stderr)
            return 2
        guard = lambda: _guard_signature(vpks, steam_inf, expected)
    try:
        target, snapshot = build_snapshot(
            vpks,
            s2v=s2v,
            label=args.label,
            game=str(env.game_root or vpks[0].parent),
            build=env.build,
            version_date=env.version_date,
            pretty=args.pretty,
            source={"kind": "local", "game": str(env.game_root or vpks[0].parent)},
            guard=guard,
        )
    except (TrackerError, OSError, subprocess.SubprocessError) as error:
        print(f"snapshot-failed: {error}", file=sys.stderr)
        return 2
    print(f"snapshot {target}")
    print(
        f"build {snapshot['build'] or 'unknown'}  "
        f"{snapshot['summary']['entries']:,} entries across {len(snapshot['vpks'])} VPKs  "
        f"{snapshot['digest']}"
    )
    for vpk in snapshot["vpks"]:
        print(f"  {vpk['name']:24} {vpk['entry_count']:>8,} entries  {vpk['blake3']}")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    sfd = find_sfd(args.sfd or None)
    if sfd is None:
        print(
            "steam-file-downloader-missing: pass --sfd or place SteamFileDownloader.exe in "
            f"{SFD_CANDIDATES[0].parent}",
            file=sys.stderr,
        )
        return 2
    print(f"Running {sfd} login; scan the QR code with the Steam mobile app.")
    return subprocess.call([str(sfd), "login"])


def cmd_list(args: argparse.Namespace) -> int:
    index = read_index()
    rows = index.get("snapshots", [])
    if not rows:
        print("no snapshots", file=sys.stderr)
        return 2
    for row in rows:
        summary = row.get("summary", {})
        source = row.get("source", {})
        origin = (
            f"m{str(source.get('manifest', ''))[-8:]}"
            if source.get("kind") == "manifest"
            else "installed"
        )
        print(
            f"{row['id']}  build {row.get('build') or '?':>5}  {origin:>12}  "
            f"{summary.get('entries', 0):>8,} entries  {row['digest']}"
        )
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    index = read_index()
    rows = index.get("snapshots", [])
    if not rows:
        print("no snapshots", file=sys.stderr)
        return 2
    if args.old:
        old = resolve_snapshot(args.old, index)
    else:
        old = resolve_snapshot("previous", index) if len(rows) > 1 else None
    new = resolve_snapshot(args.new or "latest", index)
    report = diff_snapshots(old, new)
    print(diff_text(report, limit=args.limit))
    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport {target}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    return serve(
        args.host,
        args.port,
        open_browser=args.open,
        reuse=args.reuse,
        watch=not args.no_watch,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="save a Steam login for manifest downloads (QR scan)")
    login.add_argument("--sfd", default="", help="SteamFileDownloader.exe")
    login.set_defaults(func=cmd_login)

    snapshot = sub.add_parser("snapshot", help="capture the game's VPKs through S2V")
    snapshot.add_argument("--game", default="", help="Deadlock install root or game folder")
    snapshot.add_argument("--s2v", default="", help="Source2Viewer-CLI.exe")
    snapshot.add_argument("--vpk", action="append", default=[], help="capture one specific *_dir.vpk")
    snapshot.add_argument(
        "--manifest",
        action="append",
        default=[],
        help="historical depot:manifest target; repeatable and fetched through SteamFileDownloader",
    )
    snapshot.add_argument("--app", default=DEFAULT_APP, help=f"Steam app id (default {DEFAULT_APP})")
    snapshot.add_argument("--sfd", default="", help="SteamFileDownloader.exe")
    snapshot.add_argument("--depot-output", default="", help="manifest cache root")
    snapshot.add_argument("--include-addons", action="store_true", help="also capture game/citadel/addons")
    snapshot.add_argument("--label", default="", help="snapshot label; defaults to the build")
    snapshot.add_argument(
        "--wait-stable",
        action="store_true",
        help="wait for VPKs and steam.inf to settle, and abort if they change while S2V reads",
    )
    snapshot.add_argument("--pretty", action="store_true", help="write indented JSON (larger)")
    snapshot.set_defaults(func=cmd_snapshot)

    listing = sub.add_parser("list", help="list captured snapshots")
    listing.set_defaults(func=cmd_list)

    diff = sub.add_parser("diff", help="diff two snapshots")
    diff.add_argument("old", nargs="?", default="", help="old snapshot id/label/path; default previous")
    diff.add_argument("new", nargs="?", default="latest", help="new snapshot id/label/path; default latest")
    diff.add_argument("--json", default="", help="write the full report here")
    diff.add_argument("--limit", type=int, default=20, help="paths printed per kind")
    diff.set_defaults(func=cmd_diff)

    server = sub.add_parser("serve", help="serve the local Popit tracker UI")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--open", action="store_true")
    server.add_argument("--reuse", action="store_true", help="open an already-running tracker instead of failing")
    server.add_argument("--no-watch", action="store_true", help="disable the live local-build watcher")
    server.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TrackerError as error:
        print(f"tracker-failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
