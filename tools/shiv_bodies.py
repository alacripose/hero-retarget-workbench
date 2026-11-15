"""Stage one body DMX per clip, decompiling only the clips that share a source.

A folder-wide decompile writes to the path a document names, so clips that name
the same path overwrite each other (AGENTS.md, 2026-11-14: `aim_weapon_crouch` was
built from another clip's animation, 92 bones apart). Decompiling every clip
individually is correct but costs a full pak read per clip, which is minutes per
clip here. The shared paths are a small minority, so this copies the folder
extraction where a source belongs to exactly one clip and decompiles only the
clips that share one.

  python tools/shiv_bodies.py --extraction artifacts/live-shiv-stock \
      --out artifacts/live-shiv-bodies
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from shiv_perclip_build import LIVE_PAK, S2V, _clip_documents, _resource_of, _source_of  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--pak", default="", help="pak holding the hero's clip resources")
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-bodies.json"))
    args = parser.parse_args()

    extraction = Path(args.extraction)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scratch = REPO / "artifacts" / "shiv-bodies-scratch"

    documents = _clip_documents(extraction)
    by_source: dict[str, list[Path]] = defaultdict(list)
    for document in documents:
        source = _source_of(document)
        if source:
            by_source[source].append(document)

    report = {"copied": [], "decompiled": [], "failed": []}
    started = time.time()
    for source, clips in sorted(by_source.items()):
        folder_body = extraction / source
        if len(clips) == 1 and folder_body.is_file():
            target = out / f"{clips[0].stem}.dmx"
            shutil.copyfile(folder_body, target)
            report["copied"].append({"clip": clips[0].stem, "source": source})
            print(f"BODY-COPY {clips[0].stem}", flush=True)
            continue
        for document in clips:
            clip = document.stem
            target = out / f"{clip}.dmx"
            resource = _resource_of(document, extraction)
            scratch_dir = scratch / clip
            if scratch_dir.exists():
                shutil.rmtree(scratch_dir)
            proc = subprocess.run(
                [str(S2V), "-i", str(Path(args.pak) if args.pak else LIVE_PAK), "-f", resource, "-d", "-o", str(scratch_dir)],
                capture_output=True,
                text=True,
            )
            produced = sorted(scratch_dir.rglob("*.dmx")) if scratch_dir.is_dir() else []
            if proc.returncode != 0 or not produced:
                report["failed"].append({"clip": clip, "why": f"exit {proc.returncode}"})
                print(f"BODY-FAIL {clip}", flush=True)
                continue
            shutil.copyfile(produced[0], target)
            report["decompiled"].append({"clip": clip, "source": source, "from": str(produced[0])})
            print(f"BODY-DECOMPILE {clip} <- {produced[0].name}", flush=True)
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"BODIES {len(report['copied'])} copied, {len(report['decompiled'])} decompiled, "
        f"{len(report['failed'])} failed in {time.time() - started:.0f}s"
    )
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
