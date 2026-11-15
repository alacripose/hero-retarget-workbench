"""Reclaim `artifacts/` without losing the builds and evidence that matter.

`artifacts/` reached 15 GiB across 45,751 files and 873 top-level entries, almost
all of it one-shot experiment output: thirty-plus 90 MiB Shiv pak attempts, seven
copies of the same compiled tree, and extracted stage folders that are a compile
away from existing again. Finding the one pinned pak in that is the reason a build
step gets re-run instead of inspected.

The keep list is not a pick made here: each entry is named by a pin, a receipt, or
a pipeline input that the recorded build reads. Everything else is deleted and the
deletion is itself recorded, so a missing experiment is a known removal instead of
a mystery.

    python tools/artifacts_clean.py              # report only
    python tools/artifacts_clean.py --apply      # delete, and write the receipt
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO / "artifacts"

# Every entry here is named by ledger/pins/*.json, a receipt a gate reads, or an
# input the recorded tail build consumes.
KEEP = (
    "receipts",                       # evidence for every claim in AGENTS.md
    "probes",                         # the scripts behind the receipts
    "visual",                         # captures AGENTS.md cites
    "oldviper/shiv_tail_all.vpk",     # ledger/pins/shiv.json, sha 0a966d90...
    "oldviper/shiv_append.vpk",       # pinned working build, sha 01efc18e..., installed as pak93
    "oldviper/shiv_aimcells.vpk",     # aim-cell build, sha af336b73...
    "oldviper/pak97_dir.base0647.vpk",  # the 06:47 base the pinned pak descends from
    "haze-tail/component",            # the authored Haze component the gate reads
    "haze-tail/bodies",               # 197 staged Haze clip bodies (append input)
    "haze-tail/staged-src",           # 197 staged Haze clip documents by m_sourceFilename
    "haze-tail/tails-selected",       # tail sources per clip-pairs.txt
    "haze-tail/appended-selected",    # the 197 tail-appended clip documents (compile input)
    "haze-tail/clip-pairs.txt",
    "haze-tail/haze_noskel.vpk",      # restore point, sha b849c6bf...
    "haze-tail/haze_tail.vpk",        # ledger/pins/haze_tail.json candidate, sha b0eb8dcb...
    "tail-src-tengu-full",            # the complete Tengu extraction (188 clips)
    "tail-src-tengu-staged2",         # 188 staged Tengu clip sources
)

# A running build writing into a folder must not lose its output mid-run.
GUARD = ("appended-selected", "haze2")


def measure(path: Path) -> tuple[int, int]:
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 0
    size = files = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                size += item.stat().st_size
                files += 1
            except OSError:
                pass
    return size, files


def plan() -> list[dict]:
    keep = [ARTIFACTS / entry for entry in KEEP]
    guarded = {ARTIFACTS / name for name in GUARD}
    rows: list[dict] = []

    def walk(path: Path) -> None:
        if any(path == k or path.is_relative_to(k) for k in keep):
            return                                    # this entry is kept whole
        if path in guarded:
            rows.append({"path": str(path.relative_to(REPO)), "action": "keep", "reason": "build in progress"})
            return
        containing = [k for k in keep if k.is_relative_to(path)]
        if containing and path.is_dir():
            for child in sorted(path.iterdir()):  # prune: keep only the protected descendants
                walk(child)
            return
        size, files = measure(path)
        rows.append({"path": str(path.relative_to(REPO)), "action": "delete", "bytes": size, "files": files})

    for entry in sorted(ARTIFACTS.iterdir()):
        walk(entry)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="delete instead of reporting")
    args = parser.parse_args(sys.argv[1:])
    rows = plan()
    doomed = [row for row in rows if row["action"] == "delete"]
    total = sum(row.get("bytes", 0) for row in doomed)
    files = sum(row.get("files", 0) for row in doomed)
    print(f"{len(doomed)} entries, {files} files, {total / 2**30:.2f} GiB to remove; keep list {len(KEEP)} entries")
    for row in sorted(doomed, key=lambda r: -r.get("bytes", 0))[:12]:
        print(f"  {row['bytes'] / 2**20:9.1f} MiB  {row['path']}")
    if not args.apply:
        print("report only; pass --apply to delete")
        return 0
    freed = 0
    for row in doomed:
        target = REPO / row["path"]
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            freed += row.get("bytes", 0)
        except OSError as error:
            print(f"  kept (locked): {row['path']}: {error}")
    receipt = {
        "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "kept": list(KEEP),
        "deleted_entries": len(doomed),
        "deleted_files": files,
        "deleted_bytes": freed,
        "rows": doomed,
    }
    out = ARTIFACTS / "receipts" / f"artifacts-clean-{datetime.date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"removed {freed / 2**30:.2f} GiB; receipt {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
