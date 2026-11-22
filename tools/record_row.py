"""Append a family record without a heredoc and without a temporary script.

Two failures on 2026-11-22 made this file necessary. A `python - <<'PY'` heredoc carrying a long
ticket section died on the shell's line endings, and the command it was in was lost whole; then a
one-off `tmp_append_pass15.py` was written into the repository root to do the same job and deleted
afterwards, which is a temporary probe and is exactly what the family refuses.

So the append path is a tool with arguments:

    # a ledger row
    python tools/record_row.py --ledger --result fail --command "python - <<'PY' ..." \
        --observed "the heredoc ended at end-of-file and the command wrote nothing" \
        --artifact logs/authority/2026-11-22-heredoc-and-temp-probe.jsonl

    # a row in any append-only jsonl, such as logs/authority/
    python tools/record_row.py --jsonl logs/authority/2026-11-22-x.jsonl \
        --field kind=owner-correction --field subject=heredocs --field verbatim="..."

    # a dated section at the end of AGENTS-LOG.md
    python tools/record_row.py --log --title "the heredoc and the temporary probe" \
        --body-file logs/records/2026-11-22-heredoc-and-temp-probe.md

Every path appends; none rewrites. `--field at=auto` puts a UTC timestamp in. A field with no value,
or a `--log` without a body, is refused by name rather than written as an empty row.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "ledger" / "ledger.jsonl"
LOG = ROOT / "AGENTS-LOG.md"

REFUSALS = ("record-field-empty", "record-body-absent", "record-path-outside-repository")


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def fields(pairs: list[str], at: str | None) -> dict[str, str]:
    row: dict[str, str] = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        if not key.strip() or not value.strip():
            raise SystemExit(f"record-field-empty: {pair!r} has no key or no value")
        row[key.strip()] = now() if value.strip() == "auto" else value
    if at and "at" not in row:
        row["at"] = at
    return row


def append_jsonl(path: Path, row: dict) -> Path:
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    if ROOT not in resolved.parents:
        raise SystemExit(f"record-path-outside-repository: {path}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="record_row", description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", action="store_true", help="append a row to ledger/ledger.jsonl")
    parser.add_argument("--jsonl", help="append a row to this jsonl, relative to the repository root")
    parser.add_argument("--field", action="append", default=[], help="k=v; v=auto becomes a UTC stamp")
    parser.add_argument("--command", help="the command, for a ledger row")
    parser.add_argument("--result", choices=["pass", "fail", "skip"], help="the ledger result")
    parser.add_argument("--observed", help="what was seen, for a ledger row")
    parser.add_argument("--artifact", action="append", default=[], help="a path the row cites")
    parser.add_argument("--log", action="store_true", help="append a dated section to AGENTS-LOG.md")
    parser.add_argument("--title", help="the section title")
    parser.add_argument("--body-file", help="the section body, a file in this repository")
    arguments = parser.parse_args(argv)

    if arguments.log:
        if not arguments.title or not arguments.body_file:
            raise SystemExit("record-body-absent: --log needs --title and --body-file")
        body_path = (ROOT / arguments.body_file).resolve()
        if not body_path.exists() or body_path.is_dir():
            raise SystemExit(f"record-body-absent: {arguments.body_file} is not a file")
        section = f"\n## {now()[:10]} — {arguments.title}\n\n{body_path.read_text(encoding='utf-8').strip()}\n"
        with LOG.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(section)
        print(f"appended a section to {LOG.relative_to(ROOT)}: {arguments.title}")
        return 0

    row: dict = {}
    if arguments.ledger:
        if not arguments.command or not arguments.result or not arguments.observed:
            raise SystemExit("record-field-empty: a ledger row needs --command, --result and --observed")
        row = {
            "at": now(),
            "command": arguments.command,
            "result": arguments.result,
            "observed": arguments.observed,
            "artifacts": arguments.artifact,
        }
        target = append_jsonl(LEDGER, row)
    elif arguments.jsonl:
        row = fields(arguments.field, now())
        if not row:
            raise SystemExit("record-field-empty: no --field was given")
        target = append_jsonl(Path(arguments.jsonl), row)
    else:
        raise SystemExit("record-field-empty: choose --ledger, --jsonl or --log")

    print(f"appended to {target.relative_to(ROOT)}: {json.dumps(row, sort_keys=True)[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
