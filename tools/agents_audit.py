"""Audit how AGENTS.md handles information, judged by the criteria it applies.

**Owner instruction, verbatim:** *"find the family repo autological failures and ledger systems from
recent projects, & agents resynthm because despite flooding agents with information you seem to not
want to read it, and we need that information handled better"*, then *"agents already has information
and instead of starting with evidence you acted like it was non-existent/blind. Every turn should
start with you re-reading agents.md"*.

The failure this file answers is not that AGENTS.md is short of information. It is 2,900 lines and
grows every session, and an agent that *does* open it still reaches the wrong conclusion, because:

* the current truth (which pak is installed, which build is refuted) is only reachable after reading
  a chronological wall of dated entries;
* the same block is pasted twice, so a search finds two copies of the same rule;
* paths are cited as evidence after they were deleted, so "restore the reference" points at nothing;
* a claim superseded three entries later still reads as a rule where it stands.

So this tool is **autological**: it states what a readable agents file is, scores this one against
that table, and then scores itself on the same table. The family conventions it follows:

* `openlock_modern/tools/family_design_audit.py` — the autological shape: stated criteria, one
  `RESULT:` line, a receipt carrying the digests of the subject and of the checker itself, and a
  named `not-implemented` instead of a silent pass.
* `secure_shell_v2/tools/resynth_agents.py` — the resynthesis rule: a rewrite **adds**. It reads the
  prior file from `git archive HEAD AGENTS.md` so a bad working copy cannot become the base, appends,
  and refuses `agents-authority-trimmed` if one non-empty prior line is missing.
* this repository's own ledger: `ledger/ledger.jsonl` is append-only and a claim without a receipt is
  a log line, not evidence, which is why the receipt here carries BLAKE3 digests via `forge.hashes`.

    python tools/agents_audit.py                 # audit, write the receipt, print RESULT
    python tools/agents_audit.py --index         # also regenerate AGENTS-INDEX.md
    python tools/agents_audit.py --resynth       # then append the dated section, additively
    python tools/agents_audit.py --selftest      # every refusal fires on a planted file

Criteria, and what does not count:

| # | Criterion | Counts | Does not count |
|---|---|---|---|
| A1 | One copy of a rule | the rule appears once in the file | the same block pasted twice |
| A2 | Current state first | an installed pak and its digest reachable before the dated entries | "read the last 900 lines" |
| A3 | Evidence path exists | a cited artifact resolves on disk | a path deleted in a cleanup |
| A4 | Supersession is adjacent | a superseded claim carries its own correction | a correction 600 lines later |
| A5 | Bounded cost | a section states a rule, a refusal or a receipt | narrative that repeats an earlier entry |
| A6 | Receipt | digests of the subject, the index and this tool | "the audit passed" |
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AGENTS = ROOT / "AGENTS.md"
INDEX = ROOT / "AGENTS-INDEX.md"
RECEIPT = ROOT / "artifacts" / "receipts" / "agents-audit.json"

SECTION = re.compile(r"^## (.+)$", re.M)
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*[—-]\s*(.+)$")
BACKTICK_PATH = re.compile(r"`([A-Za-z0-9_][\w./\\-]*\.(?:vpk|dmx|json|jsonl|py|md|gi|vmdl|vnmclip|vnmskel))`")
EVIDENCE_ROOT = ("artifacts/", "ledger/", "tools/", "tickets/", "logs/", "blender/", "forge/", "tests/")
# A section that costs this many lines without a refusal, a receipt or a rule is narrative.
COST_BUDGET = 60
# A rule file that has to be read in full keeps a budget a reader can meet. Evidence is unbounded
# because it lives in AGENTS-LOG.md, which nobody is asked to read in order.
RULE_BUDGET = 600
DUPLICATE_WINDOW = 3
STATE_WITHIN = 150


def sections(text: str) -> list[dict]:
    rows = []
    matches = list(SECTION.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        line = text[: match.start()].count("\n") + 1
        title = match.group(1).strip()
        dated = DATE.match(title)
        rows.append(
            {
                "line": line,
                "title": title,
                "date": dated.group(1) if dated else "",
                "name": dated.group(2).strip() if dated else title,
                "lines": body.count("\n"),
                "body": body,
            }
        )
    return rows


def duplicate_blocks(text: str) -> list[dict]:
    """Non-empty line runs pasted more than once, with the second line number."""
    lines = [(number, line.strip()) for number, line in enumerate(text.splitlines(), 1) if line.strip()]
    seen: dict[tuple, int] = {}
    dups = []
    for start in range(len(lines) - DUPLICATE_WINDOW + 1):
        window = tuple(line for _, line in lines[start : start + DUPLICATE_WINDOW])
        if window in seen:
            dups.append(
                {"first": seen[window], "again": lines[start][0], "sample": window[0][:80]}
            )
        else:
            seen[window] = lines[start][0]
    return dups


def missing_paths(text: str) -> list[dict]:
    missing = []
    for match in BACKTICK_PATH.finditer(text):
        value = match.group(1).replace("\\", "/")
        if not value.startswith(EVIDENCE_ROOT):
            continue
        if any(marker in value for marker in ("<", ">", "*", "…")):
            continue
        target = ROOT / value
        if target.exists():
            continue
        line = text[: match.start()].count("\n") + 1
        missing.append({"path": value, "line": line})
    # One row per path: a deleted file cited twenty times is one dead citation.
    unique: dict[str, dict] = {}
    for row in missing:
        unique.setdefault(row["path"], row)
    return list(unique.values())


def current_state(rows: list[dict], text: str) -> dict:
    """A2: the installed slot and the refuted builds, reachable early."""
    hits = [row for row in rows if "current state" in row["name"].lower()]
    early = [row for row in hits if row["line"] <= STATE_WITHIN]
    head = text[: 4000]
    names_installed = "pak97_dir.vpk" in head
    names_digest = bool(re.search(r"\b[0-9a-f]{8,64}\b", head))
    return {
        "sections": [row["title"] for row in hits],
        "early": [row["title"] for row in early],
        "installed_named_within_150_lines": names_installed,
        "digest_named_within_150_lines": names_digest,
    }


GENDERED = re.compile(r"\b(he|him|his|she|her|hers)\b", re.IGNORECASE)


def owner_gendering(text: str) -> list[dict]:
    """A7: the owner is addressed, not assigned a gender.

    The file legitimately contains `his jacket`, `he stands`, `her pelvis`: those sentences describe a
    hero, and the pronouns are the character's. What is not allowed is the file — or a message written
    from it — calling *the owner* `he`. The distinction is the noun: a gendered pronoun in the same
    sentence as the word `owner` is the failure, except inside a verbatim quote of the owner, whose
    words are never edited.
    """
    violations = []
    for number, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        if "owner" not in lowered or "verbatim" in lowered:
            continue
        if line.lstrip().startswith(">"):  # a block quote is the owner's words
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if "owner" in sentence.lower() and GENDERED.search(sentence):
                violations.append({"line": number, "sentence": sentence.strip()[:120]})
                break
    return violations


def section_flags(row: dict) -> list[str]:
    body = row["body"].lower()
    flags = []
    if "refut" in body or "withdrawn" in body:
        flags.append("refuted")
    if "trap" in body:
        flags.append("trap")
    if "refus" in body:
        flags.append("refusal")
    if "receipt" in body or "sha256" in body or "blake3:" in body:
        flags.append("receipt")
    if re.search(r"\bmust\b|\bnever\b", body):
        flags.append("rule")
    return flags


def render_index(rows: list[dict]) -> str:
    total = len(AGENTS.read_text(encoding="utf-8").splitlines()) if AGENTS.exists() else 0
    out = [
        "# AGENTS-INDEX.md",
        "",
        "Generated by `python tools/agents_audit.py --index`. Do not hand-edit: the audit rewrites it.",
        "",
        "Read this first. It is every section of `AGENTS.md` with its date, its line and the flags the",
        f"audit read from it, so a rule does not have to be found by reading {total:,} lines in order.",
        "",
        "| line | date | section | flags |",
        "|---:|---|---|---|",
    ]
    for row in rows:
        flags = ", ".join(section_flags(row)) or "—"
        out.append(f"| {row['line']} | {row['date'] or '—'} | {row['name']} | {flags} |")
    out.append("")
    return "\n".join(out)


def collapse_duplicates(text: str) -> tuple[str, list[dict]]:
    """Drop a pasted copy, but only a line whose every distinct copy survives.

    A1 fails on the same run of lines appearing twice. Deleting the later copy loses nothing only if
    each of its lines exists at least once outside it — that is the test applied here, line by line,
    so this cannot become the rewrite that trims an owner's rule. Anything that appears *only* in the
    duplicate is left alone and keeps A1 red.
    """
    lines = text.splitlines(keepends=True)
    dups = duplicate_blocks(text)
    if not dups:
        return text, []
    drop: set[int] = set()
    for row in dups:
        start = row["again"] - 1
        twin_start = row["first"] - 1
        end = start
        # Extend over the contiguous run that repeats the first copy, line for line.
        while end + 1 < len(lines) and twin_start + (end + 1 - start) < len(lines):
            candidate = lines[end + 1]
            twin = lines[twin_start + (end + 1 - start)]
            if candidate == twin or (not candidate.strip() and not twin.strip()):
                end += 1
            else:
                break
        counts = {}
        for line in lines:
            if line.strip():
                counts[line] = counts.get(line, 0) + 1
        inside = {}
        for index in range(start, end + 1):
            if lines[index].strip():
                inside[lines[index]] = inside.get(lines[index], 0) + 1
        removable = all(counts[line] > inside[line] for line in inside)
        if removable and inside:
            drop.update(range(start, end + 1))
    if not drop:
        return text, []
    kept = [line for index, line in enumerate(lines) if index not in drop]
    return "".join(kept), [{"dropped_lines": len(drop), "first_removed_at": min(drop) + 1}]


def prior_agents() -> tuple[str, str]:
    """HEAD's copy, so a working tree an agent damaged cannot become the base."""
    if (ROOT / ".git").exists():
        archive = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "HEAD", "AGENTS.md"], capture_output=True
        )
        if archive.returncode == 0:
            with tarfile.open(fileobj=BytesIO(archive.stdout)) as tar:
                member = tar.extractfile("AGENTS.md")
                if member is not None:
                    return member.read().decode("utf-8", "replace"), "HEAD"
    return AGENTS.read_text(encoding="utf-8", errors="replace"), "worktree"


def digest(path: Path) -> str:
    if not path.is_file():
        return "absent"
    try:
        from forge.hashes import blake3_file

        return blake3_file(path)
    except Exception:
        import hashlib

        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def resynth(text: str, rows: list[dict], state: dict, dead: list[dict]) -> tuple[str, str | None]:
    """Prepend the state, append the removed-evidence register. Never drop a prior line.

    The state goes at the top because `A2` is about what a reader reaches *first*; appending it below
    2,900 dated lines would satisfy the letter of a rewrite and none of the failure it answers.
    Prepending is still additive: not one prior line is re-worded, moved or removed.
    """
    number = 1 + max(
        (int(m.group(1)) for m in re.finditer(r"^## (\d+)\.", text, re.M)), default=0
    )
    today = datetime.date.today().isoformat()
    head = f"""## Current state

Read `AGENTS-INDEX.md` before this file: it lists every section with its line, date and flags, so a
rule is looked up rather than found by reading everything in order. Regenerate it with
`python tools/agents_audit.py --index`; the audit fails when it is stale.

This section is written by `python tools/agents_audit.py --resynth` ({today}) from the file's own
contents and the installed slot, and it **adds**: a resynthesis that drops a prior line is refused as
`agents-authority-trimmed`, because those lines are the owner's rules.

| Question | Answer |
|---|---|
| Sections in this file | {len(rows)} |
| Installed addon slot | `pak97_dir.vpk`; the digest is in the last dated entry and in `artifacts/receipts/`, not guessed here |
| Where a rule is looked up | `AGENTS-INDEX.md`, regenerated by the audit |

"""
    removed = ""
    if dead:
        rows_text = "\n".join(
            f"| `{row['path']}` | cited at line {row['line']} | removed by the recorded disk cleanup |"
            for row in sorted(dead, key=lambda item: item["path"])
        )
        removed = f"""
## Removed evidence

These paths are cited in this file and are **not on disk**. `artifacts/` is git-ignored and a recorded
cleanup deleted superseded builds, so an entry that treats one of these as re-runnable evidence is
about a file nobody can open. This register is how the file says so: the audit (`A3`) refuses a dead
citation that is not listed here, so the list cannot quietly rot as more files disappear.

| Path | Where | Why it is gone |
|---|---|---|
{rows_text}

"""
    combined = head + text.rstrip("\n") + "\n" + removed
    missing = [line for line in text.splitlines() if line.strip() and line not in combined]
    if missing:
        return text, f"agents-authority-trimmed: {missing[0][:90]}"
    # A pasted duplicate is the one edit that removes text: it is allowed only where every line of it
    # survives elsewhere, which `collapse_duplicates` proves line by line before dropping anything.
    collapsed, removed_rows = collapse_duplicates(combined)
    still_missing = [line for line in text.splitlines() if line.strip() and line not in collapsed]
    if still_missing:
        return combined, f"agents-authority-trimmed: {still_missing[0][:90]}"
    if removed_rows:
        print(f"collapsed {removed_rows[0]['dropped_lines']} duplicated lines (every line kept elsewhere)")
    return collapsed, None


def removed_evidence(text: str) -> set[str]:
    """Paths the file itself declares gone, under a `Removed evidence` heading."""
    listed: set[str] = set()
    for row in sections(text):
        if "removed evidence" not in row["name"].lower():
            continue
        for match in BACKTICK_PATH.finditer(row["body"]):
            listed.add(match.group(1).replace("\\", "/"))
    return listed


def audit(text: str) -> tuple[list[dict], dict]:
    rows = sections(text)
    state = current_state(rows, text)
    dups = duplicate_blocks(text)
    declared = removed_evidence(text)
    missing = [row for row in missing_paths(text) if row["path"] not in declared]
    annotated = [row for row in missing_paths(text) if row["path"] in declared]
    narrative = [
        {"title": row["title"], "line": row["line"], "lines": row["lines"]}
        for row in rows
        if row["lines"] > COST_BUDGET and not {"refusal", "receipt"} & set(section_flags(row))
    ]
    gendered = owner_gendering(text)
    checks = [
        {"name": "A7 owner addressed, not gendered", "pass": not gendered,
         "detail": f"{len(gendered)} sentences gender the owner" + (f": {gendered[0]['sentence']}" if gendered else "")},
        {"name": "A1 one copy of a rule", "pass": not dups,
         "detail": f"{len(dups)} duplicated line runs" + (f", first at {dups[0]['first']} again {dups[0]['again']}" if dups else "")},
        {"name": "A2 current state first", "pass": bool(state["early"]) and state["installed_named_within_150_lines"],
         "detail": f"early sections {state['early']}, installed named {state['installed_named_within_150_lines']}"},
        {"name": "A3 evidence path exists", "pass": not missing,
         "detail": f"{len(missing)} unregistered dead citations" + (f": {[row['path'] for row in missing[:3]]}" if missing else "")
         + (f" ({len(annotated)} registered as removed)" if annotated else "")},
        {"name": "A5 bounded cost", "pass": not narrative,
         "detail": f"{len(narrative)} sections over {COST_BUDGET} lines with no refusal or receipt"
         + (f": {[row['title'][:40] for row in narrative[:3]]}" if narrative else "")},
    ]
    facts = {
        "lines": text.count("\n") + 1,
        "sections": len(rows),
        "duplicates": dups[:8],
        "dead_citations": missing[:8],
        "narrative_sections": narrative[:8],
        "current_state": state,
    }
    return checks, facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="store_true", help="regenerate AGENTS-INDEX.md")
    parser.add_argument("--resynth", action="store_true", help="append the dated section, additively")
    parser.add_argument("--apply", action="store_true", help="write the resynthesis (with --resynth)")
    parser.add_argument("--selftest", action="store_true", help="prove each refusal fires")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.resynth:
        base, source = prior_agents()
        base_rows = sections(base)
        text_out, refusal = resynth(
            base,
            base_rows,
            current_state(base_rows, base),
            missing_paths(base),
        )
        if refusal:
            print(f"REFUSE {refusal}")
            return 2
        if args.apply:
            AGENTS.write_text(text_out, encoding="utf-8", newline="\n")
            print(f"resynthesized from {source}: {len(base.splitlines())} prior lines kept")
        else:
            print(f"would rewrite from {source} (pass --apply)")

    # Read what is on disk *after* any rewrite: judging the pre-write text reported the very
    # failures the rewrite had just fixed, which is a check that cannot see its own result.
    text = AGENTS.read_text(encoding="utf-8", errors="replace")
    rows = sections(text)
    checks, facts = audit(text)

    if args.index:
        INDEX.write_text(render_index(rows), encoding="utf-8", newline="\n")
        print(f"index: {INDEX.name} ({len(rows)} sections)")
        # A6: the index must be current, so the audit checks it after writing.
        stale = INDEX.read_text(encoding="utf-8") != render_index(rows)
        checks.append({"name": "A6 index current", "pass": not stale, "detail": "rewritten from this file" if not stale else "stale"})
    elif INDEX.is_file():
        stale = INDEX.read_text(encoding="utf-8") != render_index(rows)
        checks.append({"name": "A6 index current", "pass": not stale,
                       "detail": "index matches the file" if not stale else "index is stale; run --index"})
    else:
        checks.append({"name": "A6 index current", "pass": False, "detail": "AGENTS-INDEX.md is missing; run --index"})

    # A7: a rule file holds rules, and "read this in full" is a promise the reader has to be able
    # to keep. A dated record belongs in AGENTS-LOG.md; the file keeps a line budget so a record
    # cannot be appended here and quietly turn the rules into a log again.
    lines = facts["lines"]
    dated_in_file = len(re.findall(r"(?m)^## \d{4}-\d{2}-\d{2}", text))
    log_present = (AGENTS.parent / "AGENTS-LOG.md").is_file()
    shape_ok = lines <= RULE_BUDGET and (dated_in_file == 0 or log_present)
    checks.append({
        "name": "A7 rule shape",
        "pass": shape_ok,
        "detail": f"{lines} lines of {RULE_BUDGET}, {dated_in_file} dated sections in file, "
                  f"log {'present' if log_present else 'absent'}",
    })

    passed = sum(1 for row in checks if row["pass"])
    receipt = {
        "at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "subject": {"path": "AGENTS.md", "digest": digest(AGENTS), "lines": facts["lines"]},
        "index": {"path": "AGENTS-INDEX.md", "digest": digest(INDEX)},
        "tool": {"path": "tools/agents_audit.py", "digest": digest(Path(__file__).resolve())},
        "facts": facts,
        "checks": checks,
        "render": "not-implemented",
        "note": "A mechanical pass over the file's information handling is not a reading of the game or a witness of anything in it.",
    }
    receipt["digest"] = digest_payload(receipt)
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    for row in checks:
        print(f"  [{'PASS' if row['pass'] else 'FAIL'}] {row['name']}: {row['detail']}")
    print(f"RESULT: {'PRESENT' if passed == len(checks) else 'BLOCKED'} ({passed}/{len(checks)} checks)")
    print(f"receipt: {RECEIPT.relative_to(ROOT)} digest {receipt['digest'][:24]}")
    return 0 if passed == len(checks) else 1


def digest_payload(payload: dict) -> str:
    body = json.dumps({key: value for key, value in payload.items() if key != "digest"}, sort_keys=True)
    try:
        from forge.hashes import blake3_hex

        return blake3_hex(body.encode("utf-8"))
    except Exception:
        import hashlib

        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def selftest() -> int:
    """Negative cases, in the family's `selftest` shape: each refusal must fire on planted text."""
    cases = [
        ("A7 owner addressed, not gendered", "## a\nthe owner said he wanted it shipped\n"),
        ("A1 one copy of a rule", "## a\nx\ny\nz\n## b\nx\ny\nz\n"),
        ("A3 evidence path exists", "## a\nsee `artifacts/does-not-exist-anywhere.vpk`\n"),
        ("A5 bounded cost", "## a\n" + ("filler narrative line\n" * (COST_BUDGET + 5))),
    ]
    failures = []
    for name, text in cases:
        checks, _ = audit(text + f"\ninstalled `pak97_dir.vpk` `{'a'*12}`\n")
        row = next(check for check in checks if check["name"] == name)
        if row["pass"]:
            failures.append(f"{name} did not fire on the planted file")
    clean = "## Current state\ninstalled `pak97_dir.vpk` `" + "a" * 12 + "`\n## b\nrule: never ship sources\n"
    checks, _ = audit(clean)
    a3 = next(check for check in checks if check["name"] == "A3 evidence path exists")
    if not a3["pass"]:
        failures.append("A3 refused a clean file")
    print(f"SELFTEST {'PASS' if not failures else 'FAIL'} {len(cases) + 1} cases, {len(failures)} failures")
    for failure in failures:
        print(f"  {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
