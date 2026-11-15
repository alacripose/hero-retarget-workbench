"""Rebuild the shipped Shiv clips from per-clip live bodies.

The folder-wide decompile (`-f models/heroes_staging/shiv/clips/ -d`) writes each
clip's data to the path its ``m_sourceFilename`` names, and several shipped clips
name the same path (the aim sweeps, the corner leans, the parry).  When the last
clip written is not the clip that was staged, the merge runs on another clip's
animation: measured on ``aim_weapon_crouch`` that body differs from the clip's own
decompile on 92 bones, all four IK targets (26-38 units) and both upper arms
(~1.5 rad), which is the "bones rotated wrong" the owner reported.

So this driver decompiles one clip at a time, stages the body the decompiler
actually produced for that clip, and -- because the compile step reads each
document's ``m_sourceFilename`` -- places that body at the document's own source
path immediately before compiling that one document.  Nothing is shared between
clips, so no clip can be built from a sibling's animation.

  python tools/shiv_perclip_build.py bodies --extraction <live clips dir> --out <bodies dir>
  python tools/shiv_perclip_build.py compile --csdk <csdk> --addon <addon> \
      --merged <merged dir> --extraction <live clips dir> --skeleton-source <tree with vnmskel_c>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
LIVE_PAK = Path("D:/SteamLibrary/steamapps/common/Deadlock/game/citadel/pak01_dir.vpk")


def _clip_documents(extraction: Path) -> list[Path]:
    return sorted(extraction.rglob("clips/*.vnmclip"))


def _resource_of(document: Path, extraction: Path) -> str:
    """The compiled clip this document stands in for, from its own path."""
    rel = document.relative_to(extraction).as_posix()
    return rel[: -len(".vnmclip")] + ".vnmclip_c"


def _hero_dir(document: Path, extraction: Path) -> Path:
    """`models/<group>/<hero>` for a document under `<extraction>/.../clips`."""
    return document.parent.parent.relative_to(extraction)


def _source_of(document: Path) -> str | None:
    for line in document.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("m_sourceFilename"):
            parts = stripped.split('"')
            if len(parts) >= 2:
                return parts[1]
    return None


# The reduced CSDK13 cannot allocate `CNmClipDocEvent_TaggedSound` (it replies
# `Failed to allocate an instance of class`), which is a footstep sound marker in
# the document, not animation data.  Those documents are retried once with the
# marker removed so the clip still ships; the receipt records that it happened.
SOUND_EVENT = re.compile(
    r"{[^{}]*_class = \"CNmClipDocEvent_TaggedSound\"[^{}]*},?"
)


def _strip_tagged_sound(text: str) -> tuple[str, int]:
    stripped, count = SOUND_EVENT.subn("", text)
    return stripped, count


def _copy(src: Path, dst: Path) -> None:
    """Copy unless the two paths are the same file (seed == addon is legal)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.resolve() == dst.resolve():
            return
    except OSError:
        pass
    shutil.copyfile(src, dst)


def bodies(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scratch = REPO / "artifacts" / "perclip-bodies-scratch"
    extraction = Path(args.extraction)
    pak = Path(getattr(args, "pak", "") or LIVE_PAK)
    report: dict[str, object] = {"bodies": [], "failed": []}
    for document in _clip_documents(extraction):
        clip = document.stem
        if clip.endswith("+non_additive"):
            continue
        if (out / f"{clip}.dmx").is_file() and not args.force:
            continue
        target = scratch / clip
        if target.exists():
            shutil.rmtree(target)
        resource = _resource_of(document, extraction)
        proc = subprocess.run(
            [str(S2V), "-i", str(pak), "-f", resource, "-d", "-o", str(target)],
            capture_output=True,
            text=True,
        )
        produced = sorted(target.rglob("*.dmx")) if target.is_dir() else []
        if proc.returncode != 0 or not produced:
            report["failed"].append({"clip": clip, "why": f"exit {proc.returncode}, {len(produced)} dmx"})
            print(f"BODY-FAIL {clip}", flush=True)
            continue
        shutil.copyfile(produced[0], out / f"{clip}.dmx")
        report["bodies"].append({"clip": clip, "from": str(produced[0]), "bytes": (out / f"{clip}.dmx").stat().st_size})
        print(f"BODY {clip} <- {produced[0].name}", flush=True)
        report_path = REPO / "artifacts" / "receipts" / "perclip-bodies.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"BODIES done {len(report['bodies'])} ok, {len(report['failed'])} failed", flush=True)
    return 0


def compile_documents(args: argparse.Namespace) -> int:
    """Place each clip's own body at its document's source path, then compile that one document."""
    csdk = Path(args.csdk)
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    if not compiler.is_file():
        raise SystemExit(f"resourcecompiler not found at {compiler}")
    addon = csdk / "content" / "citadel_addons" / args.addon
    merged = Path(args.merged)
    skeleton_tree = Path(args.skeleton_source)
    report: dict[str, object] = {"compiled": [], "failed": [], "skipped": []}
    report_path = REPO / "artifacts" / "receipts" / "perclip-compile.json"

    for tree_file in sorted(skeleton_tree.rglob("*.vnmskel_c")):
        _copy(tree_file, addon / tree_file.relative_to(skeleton_tree))
        break

    # A clip only compiles against the skeleton's *source* KV3 and the skeleton
    # mesh DMX the KV3 names; a shipped tree carries just the compiled skeleton,
    # so those inputs come from an addon that was already built.
    if args.seed:
        seed = Path(args.seed)
        for name in sorted(seed.rglob("*.vnmskel")):
            _copy(name, addon / name.relative_to(seed))
        for mesh_file in sorted(seed.rglob("dmx/mesh/*.dmx")):
            _copy(mesh_file, addon / mesh_file.relative_to(seed))

    extraction = Path(args.extraction)
    for document in _clip_documents(extraction):
        clip = document.stem
        # A fused `+non_additive` document cannot be compiled on its own: the
        # compiler rejects the '+' and generates that variant from its base
        # document, which this loop compiles. Counting it as a failure hides that.
        if "+non_additive" in document.name:
            report["skipped"].append({"clip": clip, "why": "generated from its base document"})
            continue
        merged_body = merged / f"{clip}.dmx"
        if not merged_body.is_file():
            report["skipped"].append({"clip": clip, "why": "no merged body"})
            continue
        source = _source_of(document)
        if source is None:
            report["skipped"].append({"clip": clip, "why": "no m_sourceFilename"})
            continue
        staged_document = addon / document.relative_to(extraction)
        _copy(document, staged_document)
        _copy(merged_body, addon / source)
        resource = str(staged_document.relative_to(csdk / "content")).replace("\\", "/")
        started = time.time()
        proc = subprocess.run(
            [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", resource],
            cwd=str(csdk / "content"),
            capture_output=True,
            text=True,
        )
        stripped_events = 0
        if proc.returncode != 0 and "Failed to allocate an instance of class" in (proc.stdout or ""):
            text, stripped_events = _strip_tagged_sound(document.read_text(encoding="utf-8", errors="replace"))
            if stripped_events:
                staged_document.write_text(text, encoding="utf-8")
                proc = subprocess.run(
                    [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", resource],
                    cwd=str(csdk / "content"),
                    capture_output=True,
                    text=True,
                )
        if proc.returncode != 0 or "0 failed" not in proc.stdout:
            report["failed"].append(
                {
                    "clip": clip,
                    "exit": proc.returncode,
                    "tail": (proc.stdout or proc.stderr or "")[-800:],
                }
            )
            print(f"COMPILE-FAIL {clip} exit {proc.returncode}", flush=True)
        else:
            entry = {"clip": clip, "seconds": round(time.time() - started, 2)}
            if stripped_events:
                entry["stripped_tagged_sound_events"] = stripped_events
            report["compiled"].append(entry)
            print(f"COMPILE {clip}", flush=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"COMPILE done {len(report['compiled'])} ok, {len(report['failed'])} failed, {len(report['skipped'])} skipped", flush=True)
    return 0 if not report["failed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    body = sub.add_parser("bodies")
    body.add_argument("--extraction", required=True)
    body.add_argument("--out", required=True)
    body.add_argument("--force", action="store_true")
    body.add_argument("--pak", default="", help="pak holding the hero's clip resources (default: live pak01)")
    comp = sub.add_parser("compile")
    comp.add_argument("--csdk", required=True)
    comp.add_argument("--addon", required=True)
    comp.add_argument("--merged", required=True)
    comp.add_argument("--extraction", required=True)
    comp.add_argument("--skeleton-source", required=True)
    comp.add_argument("--seed", default="", help="content addon to copy the skeleton KV3 and mesh DMX from")
    comp.add_argument("--force", action="store_true", help="recompile every document, overwriting earlier clips")
    args = parser.parse_args()
    return bodies(args) if args.mode == "bodies" else compile_documents(args)


if __name__ == "__main__":
    sys.exit(main())
