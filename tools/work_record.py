"""Refuse ephemeral work, and make every release command record itself.

Two defects this exists to stop, both hit in this repository:

* a working command was run and only the shell's history knew it: the ledger row
  carried the short form, the receipt carried no `command`, and the next session
  could not reproduce the port;
* work was written to a temp directory (`%TEMP%`, `codebuff-process-*`, `/tmp`),
  which goes away, so the project cannot improve on what it learned.

Every release-path tool calls `begin()` before it writes anything and `finish()`
when it stops.  `begin()` refuses an ephemeral output path outright.  `finish()`
appends the *full argv*, the resolved outputs and the observation to
`ledger/ledger.jsonl`, so a command that produced an artifact is always in the
record, not in somebody's memory of it.

Refusal codes:

    ephemeral-path     an output points into a temp directory or a process temp dir
    work-unrecorded    a release claimed an artifact the ledger has no producing row for
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "ledger" / "ledger.jsonl"

TEMP_ROOTS = {
    Path(tempfile.gettempdir()).resolve(),
    Path(os.environ.get("TEMP", "")) .resolve() if os.environ.get("TEMP") else None,
    Path(os.environ.get("TMP", "")).resolve() if os.environ.get("TMP") else None,
    Path("C:/Windows/Temp"),
    Path("/tmp"),
    Path("/var/tmp"),
}


class WorkRefused(RuntimeError):
    """A tool refusing to run or to claim a result."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def refuse_ephemeral_paths(paths) -> None:
    """Raise `ephemeral-path` when an output lives somewhere that will be deleted."""
    offenders = []
    for item in paths:
        if not item:
            continue
        path = _resolved(Path(item))
        text = str(path).lower()
        if "codebuff-process-" in text or "-process-" in text and "temp" in text:
            offenders.append(str(path))
            continue
        for root in TEMP_ROOTS:
            if root is None:
                continue
            try:
                root_resolved = _resolved(root)
            except OSError:
                continue
            if str(root_resolved) and path.is_relative_to(root_resolved):
                offenders.append(str(path))
                break
    if offenders:
        raise WorkRefused(
            "ephemeral-path",
            f"{offenders[:4]} live in a temporary directory; work that disappears cannot be built on, "
            "so it is written to the repository's artifacts/ instead",
        )


def full_command(argv=None) -> str:
    """The command exactly as it ran, including the interpreter and its arguments."""
    argv = list(sys.argv if argv is None else argv)
    return " ".join(argv)


def finish(tool: str, outputs, observed: str, result: str = "pass", extra: dict | None = None) -> dict:
    """Append one ledger row carrying the command, its outputs and what was seen."""
    row = {
        "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "tool": tool,
        "command": full_command(),
        "cwd": str(Path.cwd()),
        "result": result,
        "observed": observed[:4000],
        "artifacts": [str(path) for path in outputs if path],
    }
    if extra:
        row.update(extra)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row) + "\n")
    return row


def rows() -> list[dict]:
    if not LEDGER.is_file():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def require_recorded(tool: str, outputs) -> None:
    """Raise `work-unrecorded` when no ledger row names this tool and these outputs."""
    wanted = {str(path) for path in outputs if path}
    if not wanted:
        return
    for row in rows():
        if row.get("tool") != tool:
            continue
        have = {str(item) for item in row.get("artifacts") or []}
        if wanted & have and row.get("command"):
            return
    raise WorkRefused(
        "work-unrecorded",
        f"no ledger row names {tool} producing {sorted(wanted)[:3]} with its command; "
        "an artifact whose command is not in the record cannot be reproduced and is not shipped",
    )
