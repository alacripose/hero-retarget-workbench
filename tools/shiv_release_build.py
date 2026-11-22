"""Rebuild the shipped clips-only pak from its inputs, in one command.

The release is a clips tree plus one compiled skeleton, and every earlier build was
assembled by hand: extract, edit a DMX, run the compiler in the right working
directory, copy one file, pack. That is how a pak ends up with a skeleton nobody
can regenerate. This chains the same steps and writes the receipt, so the digest
in the gate is reproducible instead of remembered.

It never compiles a clip: the clips come from the pinned pak unchanged, because the
owner's verdict on them is that the tail is right and the body plays correctly.

  python tools/shiv_release_build.py \
      --clips artifacts/oldviper/shiv_noskel.vpk \
      --skeleton-dmx <06:47 shiv_tailbones.dmx> \
      --game-skel <live shiv_skel.dmx> \
      --csdk <home>/Downloads/Reduced_CSDK_13 \
      --out artifacts/oldviper/shiv_root0647.vpk \
      --receipt artifacts/receipts/release-clips-only.json
"""

from __future__ import annotations
import os

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S2V = Path(os.path.expanduser(r"~\Downloads\cli-windows-x64\Source2Viewer-CLI.exe"))
BLENDER = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe")
ADDON = "shiv_release_skel"
SKELETON_RELATIVE = Path("models/heroes_staging/shiv/shiv.vnmskel_c")


def digest(path: Path, algorithm: str = "sha256") -> str:
    handle = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            handle.update(block)
    return handle.hexdigest()


def run(command: list[str], cwd: Path | None = None, log: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, errors="replace")
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("$ " + " ".join(command) + "\n\n" + result.stdout + result.stderr, encoding="utf-8")
    return result


def extract(vpk: Path, tree: Path) -> None:
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    result = run([str(S2V), "-i", str(vpk), "-o", str(tree), "-q"])
    if result.returncode != 0 or not any(tree.rglob("*")):
        raise RuntimeError(f"s2v-extract-failed: {vpk}: {result.stdout[-400:]}{result.stderr[-400:]}")


def root_rest(skeleton_dmx: Path, game_skel: Path, out_dmx: Path, report: Path) -> dict:
    result = run(
        [
            str(BLENDER), "-b", "--python", str(ROOT / "tools" / "skeleton_ingame_root.py"), "--",
            "--skel", str(skeleton_dmx), "--game", str(game_skel),
            "--out", str(out_dmx), "--root-only", "--report", str(report),
        ],
        log=report.with_suffix(".log"),
    )
    if result.returncode != 0 or not out_dmx.is_file():
        raise RuntimeError(f"skeleton-root-failed: {result.stdout[-600:]}")
    return json.loads(report.read_text(encoding="utf-8"))


def compile_skeleton(out_dmx: Path, csdk: Path, log: Path) -> Path:
    """Compile the vnmskel with the skeleton the seed addon already declares."""
    seed = ROOT / "artifacts" / "skeleton-addon-bind"
    content = csdk / "content" / "citadel_addons" / ADDON
    if content.exists():
        shutil.rmtree(content)
    shutil.copytree(seed, content)
    targets = list(content.rglob("shiv_tailbones.dmx"))
    if not targets:
        raise RuntimeError("seed-addon-has-no-skeleton-dmx")
    shutil.copyfile(out_dmx, targets[0])
    result = run(
        [
            str(csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"),
            "-nop4", "-f", "-game", "../game/citadel",
            "-i", f"citadel_addons/{ADDON}/models/heroes_staging/shiv/shiv.vnmskel",
        ],
        cwd=csdk / "content",
        log=log,
    )
    compiled = csdk / "game" / "citadel_addons" / ADDON / SKELETON_RELATIVE
    if result.returncode != 0 or not compiled.is_file():
        raise RuntimeError(f"skeleton-compile-failed: {log}")
    return compiled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", required=True)
    parser.add_argument("--skeleton-dmx", required=True)
    parser.add_argument("--game-skel", required=True)
    parser.add_argument("--csdk", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--receipt", default=str(ROOT / "artifacts" / "receipts" / "release-clips-only.json"))
    parser.add_argument("--work", default=str(ROOT / "artifacts" / "ab" / "release-tree"))
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    clips = Path(args.clips)
    out = Path(args.out)
    tree = Path(args.work)
    csdk = Path(args.csdk)
    logs = ROOT / "logs"

    extract(clips, tree)
    changed = root_rest(
        Path(args.skeleton_dmx), Path(args.game_skel),
        ROOT / "artifacts" / "skeleton" / "shiv_tailbones_release.dmx",
        ROOT / "artifacts" / "receipts" / "skeleton-release-root.json",
    )
    compiled = compile_skeleton(
        ROOT / "artifacts" / "skeleton" / "shiv_tailbones_release.dmx",
        csdk, logs / "release-skeleton-compile.log",
    )
    destination = tree / SKELETON_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(compiled, destination)

    out.parent.mkdir(parents=True, exist_ok=True)
    packed = run([str(S2V), "-i", str(tree), "--vpk_create", str(out), "-q"], log=logs / "release-pack.log")
    if packed.returncode != 0 or not out.is_file():
        raise RuntimeError(f"pack-failed: {packed.stdout[-400:]}")

    files = sorted(str(path.relative_to(tree)).replace("\\", "/") for path in tree.rglob("*") if path.is_file())
    receipt = {
        "vpk": out.as_posix(),
        "bytes": out.stat().st_size,
        "sha256": digest(out),
        "file_count": len(files),
        "skeleton_override": [name for name in files if name.endswith(".vnmskel_c")],
        "skeleton_md5": digest(destination, "md5"),
        "skeleton_bytes": destination.stat().st_size,
        "skeleton_source": f"{args.skeleton_dmx}: only root_motion's rest replaced from {args.game_skel}",
        "skeleton_changed": sorted((changed.get("changed") or {}).keys()),
        "dmx_shipped": [name for name in files if "/dmx/" in name],
        "source_build": f"{args.clips} (clips and model unchanged)",
        "note": args.note,
        "rebuilt_by": "tools/shiv_release_build.py",
    }
    Path(args.receipt).parent.mkdir(parents=True, exist_ok=True)
    Path(args.receipt).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("bytes", "sha256", "file_count", "skeleton_bytes", "skeleton_md5", "skeleton_changed")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
