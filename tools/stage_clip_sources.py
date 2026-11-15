"""Stage a hero's clip DMX under the clip document's own label.

S2V decompiles `clips/<label>.vnmclip_c` to a DMX named after the **animation
inside it**, not the document (`item_stand_idle` yields `item_idle_loop.dmx`), so
a folder of clip DMX cannot be paired to a folder of documents by filename.  The
document says where its data is: `m_sourceFilename`.  This tool reads that, copies
the DMX to `<label>.dmx`, and refuses when any document's data is absent.

That refusal is the point: a partial source folder is what produced the
"28 of 188" Tengu clip set, and the ad-hoc fallback that followed it was an
invented input, not a measurement.

Refusal codes:

    clip-source-missing   a clip document declares a DMX that is not in the extraction
    clip-source-incomplete  fewer DMX staged than clip documents — a partial source set

  python tools/stage_clip_sources.py --clips <extraction clips folder> --out <staged folder>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_PATTERN = re.compile(r'm_sourceFilename\s*=\s*"([^"]+)"')


class Refused(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _resolve(extraction_root: Path, declared: str) -> Path | None:
    relative = declared.replace("\\", "/")
    for base in (extraction_root, extraction_root / "models", extraction_root.parent, extraction_root.parent.parent):
        candidate = base / relative
        if candidate.is_file():
            return candidate
    return None


def stage(clips_dir: Path, out_dir: Path) -> dict:
    documents = sorted(clips_dir.glob("*.vnmclip"))
    if not documents:
        raise Refused("clip-source-missing", f"no *.vnmclip documents in {clips_dir}")
    # The extraction root is the deepest folder above the clip documents' own
    # `models/...` tree, so a declared path can be rooted there.
    root = clips_dir
    for parent in clips_dir.parents:
        if parent.name == "models" or (parent / "models").is_dir() or parent.name == "artifacts":
            root = parent if (parent / "models").is_dir() else parent.parent
            break
    out_dir.mkdir(parents=True, exist_ok=True)
    staged, missing, collisions = [], [], []
    for document in documents:
        text = document.read_text(encoding="utf-8", errors="replace")
        match = SOURCE_PATTERN.search(text)
        if not match:
            missing.append({"document": document.name, "reason": "no m_sourceFilename"})
            continue
        source = _resolve(root, match.group(1))
        if source is None:
            missing.append({"document": document.name, "declared": match.group(1)})
            continue
        label = document.name[: -len(".vnmclip")]
        target = out_dir / f"{label}.dmx"
        if target.exists() and target.stat().st_size != source.stat().st_size:
            collisions.append(label)
        shutil.copyfile(source, target)
        staged.append({"label": label, "source": str(source), "bytes": target.stat().st_size})
    if missing:
        raise Refused(
            "clip-source-missing",
            f"{len(missing)} of {len(documents)} clip documents declare data that is not in the extraction "
            f"(e.g. {missing[:3]})",
        )
    return {
        "clips_dir": str(clips_dir),
        "out_dir": str(out_dir),
        "documents": len(documents),
        "staged": len(staged),
        "labels": [row["label"] for row in staged],
        "collisions": collisions,
    }


def stage_or_refuse(clips_dir: Path, out_dir: Path) -> dict:
    receipt = stage(clips_dir, out_dir)
    if receipt["staged"] < receipt["documents"]:
        raise Refused(
            "clip-source-incomplete",
            f"{receipt['staged']} DMX staged for {receipt['documents']} clip documents; a partial set is what "
            "forced a hand-picked fallback source",
        )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(sys.argv[1:])
    try:
        receipt = stage_or_refuse(Path(args.clips), Path(args.out))
    except Refused as refusal:
        print(f"REFUSE {refusal.code}: {refusal.detail}")
        return 2
    print(f"STAGE {receipt['staged']}/{receipt['documents']} clip sources -> {receipt['out_dir']}")
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
