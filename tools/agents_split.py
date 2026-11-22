"""Keep the owner's own words at the top of AGENTS.md and move everything after them to the ledgers.

The owner's instruction, twice: the head of the file is the owner's text and is not resynthesised,
and everything after it belongs in the ledgers, where the next project can read it. The file was
4,262 lines before `d7493fb` moved the dated evidence to `AGENTS-LOG.md`; this is the same move
carried to its end, so the file holds the owner's block and nothing appended to it afterwards.

The seam is named rather than guessed: the owner's block ends at the line `Do not delete patch
probes.` The head is copied byte-for-byte and checked afterwards; the tail is written in full to
`logs/records/AGENTS-after-head@<date>.md`, and every heading in it gets a ledger row carrying the
archive path and the section's digest.

    python tools/agents_split.py --plan     # what would move, and the head's digest
    python tools/agents_split.py --apply    # write the archive, the ledger rows and the new file

A missing seam is `agents-head-missing`, and a head that does not survive the rewrite is
`agents-head-changed`; neither writes a file.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
LEDGER = ROOT / "ledger" / "ledger.jsonl"
ARCHIVE = ROOT / "logs" / "records"
SEAM = "Do not delete patch probes."

REFUSALS = ("agents-head-missing", "agents-head-changed", "agents-archive-unwritable")


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def split(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == SEAM:
            return "".join(lines[: index + 1]), "".join(lines[index + 1 :]).lstrip("\n")
    raise SystemExit(
        f"agents-head-missing: no line reads {SEAM!r}, so the seam cannot be found and nothing is moved"
    )


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def plan() -> int:
    original = AGENTS.read_text(encoding="utf-8")
    head, tail = split(original)
    headings = [line.strip() for line in tail.splitlines() if line.startswith("## ")]
    print(f"head: {len(head.splitlines())} lines, {digest(head)}")
    print(f"tail: {len(tail.splitlines())} lines, {len(headings)} headings, {digest(tail)}")
    for heading in headings:
        print(f"  moves  {heading}")
    return 0


def apply() -> int:
    original = AGENTS.read_text(encoding="utf-8")
    head, tail = split(original)
    head_digest = digest(head)
    today = now()[:10]

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    archive = ARCHIVE / f"AGENTS-after-head@{today}.md"
    provenance = (
        f"<!-- Moved out of AGENTS.md on {today} by tools/agents_split.py --apply. The owner's block at the "
        f"head of that file is untouched ({head_digest}); this file is the text that followed it, kept in full. -->\n\n"
    )
    try:
        archive.write_text(provenance + tail, encoding="utf-8", newline="\n")
    except OSError as error:
        raise SystemExit(f"agents-archive-unwritable: {error}") from error

    rows = []
    for block in tail.split("\n## "):
        section = block if block.startswith("## ") else "## " + block
        heading = section.splitlines()[0].lstrip("# ").strip() or "(untitled)"
        rows.append(
            {
                "at": now(),
                "command": "python tools/agents_split.py --apply",
                "result": "recorded",
                "observed": f"moved out of AGENTS.md, heading {heading!r}, {len(section.splitlines())} lines, {digest(section)}",
                "artifacts": [str(archive.relative_to(ROOT)).replace("\\", "/"), "AGENTS.md"],
            }
        )
    with LEDGER.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    AGENTS.write_text(head, encoding="utf-8", newline="\n")
    written = AGENTS.read_text(encoding="utf-8")
    if digest(written) != head_digest:
        raise SystemExit("agents-head-changed: the rewritten head is not the head that was read")

    print(f"head kept: {len(head.splitlines())} lines, {head_digest}")
    print(f"moved: {len(tail.splitlines())} lines, {len(rows)} ledger rows -> {archive.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agents_split", description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="show what would move")
    parser.add_argument("--apply", action="store_true", help="write the archive, the rows and the new file")
    arguments = parser.parse_args(argv)
    if arguments.apply:
        return apply()
    return plan()


if __name__ == "__main__":
    sys.exit(main())
