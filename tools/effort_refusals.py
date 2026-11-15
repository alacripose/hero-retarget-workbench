"""Refuse effort caveats and answer-instead-of-work in the durable record.

The owner's refusal: an agent may not use context length, session length, elapsed
time or a token/credit budget as the reason a task stopped, shrunk or was called
done. Those are properties of the harness, not of the work, and writing one into
the record hands the next session a reason the project cannot improve on.

Family convention (`openlock_modern`: `capability_refusals`, `parity_refusals`,
run from `tools/proto.py gate`, proven by `selftest` with negative cases) is
followed here: named codes, a gate check, and a selftest that plants each defect.

Refusal codes:

    effort-caveat           the record names a budget/context/session/time limit as a reason
    effort-deferral         the record defers the remaining work to "next session" or similar
    answer-instead-of-work  the record substitutes an answer for the next step
    stop-instead-of-continue the record stops where the instruction was to keep going

  python tools/effort_refusals.py check [--ledger ledger/ledger.jsonl] [--receipts artifacts/receipts]
  python tools/effort_refusals.py selftest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Phrasings that name a budget as the cause.  Each is matched case-insensitively
# against the text fields of a ledger row or a receipt.
CAVEATS = {
    "effort-caveat": (
        "running low on room",
        "running out of context",
        "out of context",
        "context length",
        "context window",
        "session length",
        "session is too long",
        "not enough context",
        "too long to finish",
        "low on tokens",
        "token budget",
        "out of budget",
        "ran out of time",
        "not enough time",
        "short on time",
        "hit the time limit",
    ),
    "effort-deferral": (
        "next session",
        "tomorrow",
        "in a follow-up session",
        "leave that for later",
        "would need another pass later",
    ),
    # The owner's second pattern: answering where the instruction was to keep
    # working.  A summary is not a deliverable, and a record that substitutes one
    # for the next step hides work that was not done.
    "answer-instead-of-work": (
        "i don't want you to answer",
        "answering the question instead",
        "that answers the question",
        "final answer",
        "no further work",
        "nothing more to do",
        "handing back",
    ),
    "stop-instead-of-continue": (
        "stopping here",
        "i will stop here",
        "end of turn",
        "as summarised above",
        "as summarized above",
        "over to you",
    ),
}

# The owner's own instructions quote these phrases; only machine-written records
# are scanned, never AGENTS.md prose, so the prohibition cannot trip the check.
SCAN_FIELDS = ("observed", "detail", "why", "note", "summary", "result_detail")


class Refused(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def scan_text(text: str, where: str) -> None:
    lowered = text.lower()
    for code, phrases in CAVEATS.items():
        for phrase in phrases:
            if phrase in lowered:
                raise Refused(
                    code,
                    f"{where} says {phrase!r}; a budget is not a reason work stops, shrinks or is called done, "
                    "and the record must not carry one",
                )


def scan_ledger(path: Path) -> int:
    if not path.is_file():
        return 0
    checked = 0
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        for field in SCAN_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and value:
                scan_text(value, f"{path.name} line {number} ({field})")
        checked += 1
    return checked


def scan_receipts(folder: Path) -> int:
    checked = 0
    if not folder.is_dir():
        return 0
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(value, str) and value:
                        scan_text(value, f"{path.name}:{key}")
                    elif isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(item for item in node if isinstance(item, (dict, list)))
        checked += 1
    return checked


def check(ledger: Path = REPO / "ledger" / "ledger.jsonl", receipts: Path = REPO / "artifacts" / "receipts") -> str:
    rows = scan_ledger(ledger)
    files = scan_receipts(receipts)
    return f"No effort caveats in {rows} ledger rows or {files} receipts"


def selftest() -> int:
    """Negative cases: every refusal must fire on a planted record."""
    cases = [
        ("effort-caveat", "I am running low on room for a long Blender session"),
        ("effort-caveat", "stopped here because of the context length"),
        ("effort-deferral", "the rest can be checked next session"),
        ("answer-instead-of-work", "that answers the question, so nothing more to do"),
        ("stop-instead-of-continue", "stopping here, this is the end of turn"),
    ]
    failures = []
    for code, text in cases:
        try:
            scan_text(text, "planted")
        except Refused as refusal:
            if refusal.code != code:
                failures.append(f"{text!r} refused as {refusal.code}, expected {code}")
        else:
            failures.append(f"{text!r} was not refused")
    clean = "the tail mesh is declared by the body RenderMeshFile and sits in a LODGroupAll"
    try:
        scan_text(clean, "planted")
    except Refused as refusal:
        failures.append(f"clean text was refused as {refusal.code}")
    if failures:
        for failure in failures:
            print(f"SELFTEST FAIL {failure}")
        return 1
    print(f"SELFTEST PASS {len(cases) + 1}/{len(cases) + 1} cases ({len(cases)} refusals fire, 1 clean text passes)")
    return 0


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "check"
    if action == "selftest":
        return selftest()
    if action == "check":
        try:
            print(check())
        except Refused as refusal:
            print(f"REFUSE {refusal.code}: {refusal.detail}")
            return 2
        return 0
    print(f"unknown action {action!r}; use check or selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
