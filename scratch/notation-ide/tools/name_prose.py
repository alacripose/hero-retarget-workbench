"""Every name the owner reads is prose, and shorthand in a name is the same refusal.

The first version of this gate read `#[test]` names only. That was a scope reduction: the
same shorthand sits in section headings, in refusal and error strings, and in the labels a
tool prints. This scanner reads every surface it can find in a repository and classifies
each name on the same ladder: whole, annotated, lossy, shorthand.

Surfaces:
    heading   markdown section headings in AGENTS.md and docs
    test      #[test] fn, def test_, test(" and it(" names
    message   the string inside raise/panic/report/refusal calls
    code      a printed receipt kind such as WASM-BUILD or entry-present

A code is an interface and is recorded, never refused: renaming one breaks a receipt the
family already reads. That exemption is named here so it is not silent.

    python tools/name_prose.py --selftest
    python tools/name_prose.py --repo . --check
    python tools/name_prose.py --family --json artifacts/name-judge.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MIN_WORDS = 6
SLOP_STEMS = ("test_", "tests_", "it_", "should_", "tmp_", "temp_", "misc_", "foo_", "bar_", "baz_")
SLOP_WORDS = {"misc", "etc", "tmp", "temp", "foo", "bar", "baz", "stuff", "thing", "things", "tbd", "x", "y", "z"}
CLAIM_WORDS = {
    "is", "are", "was", "were", "has", "have", "had", "does", "do", "did", "can", "cannot",
    "refuses", "refused", "reports", "keeps", "clears", "holds", "shows", "names", "draws",
    "passes", "fails", "lands", "stays", "ends", "starts", "returns", "counts", "classifies",
    "resolves", "removes", "survives", "wins", "moves", "opens", "closes", "reads", "writes",
    "treats", "earns", "serves", "owns", "finds", "needs", "takes", "gives", "becomes",
}

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}\s*[—-]\s*")
# "donor" ends in the letters of "or" and is not a dangling conjunction, so the
# conjunction needs a word boundary before it.
DANGLING = re.compile(r"(?:[,;|—–]|\b(?:and|or))\s*$")
RUST_TEST = re.compile(r"#\[test\]\s*\n\s*(?:#\[[^\]]*\]\s*\n\s*)*fn\s+([a-z0-9_]+)\s*\(", re.M)
PY_TEST = re.compile(r"^\s*def\s+(test_[a-z0-9_]+)\s*\(", re.M)
JS_TEST = re.compile(r"""\b(?:it|test)\(\s*["']([^"']+)["']""")
HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
MESSAGE = re.compile(r"""(?:raise\s+\w+\s*\(|panic!\(|report\(|refuse\()\s*[frb]*["'](.+?)["']""", re.S)
CODE = re.compile(r"""["']([A-Z][A-Z0-9]*(?:-[a-z0-9]+)+)["']""")


ARTICLES = {"a", "an", "i"}


def words_of(text: str) -> list[str]:
    return [word for word in re.split(r"[^A-Za-z0-9]+", text) if word]


def abbreviates(words: list[str]) -> bool:
    # "a" and "i" are words. One letter tokens outside them are abbreviations.
    return any(len(word) == 1 and word.lower() not in ARTICLES for word in words)


def judge(name: str, surface: str) -> tuple[str, list[str]]:
    problems: list[str] = []
    words = words_of(NAME_CASE.sub(" ", name))
    ladder_words = [word.lower() for word in words]

    if surface == "test":
        if len(words) < MIN_WORDS:
            problems.append(f"test-name-short: {len(words)} words, needs {MIN_WORDS}")
        if any(char.isdigit() for char in name):
            problems.append("test-name-digit: a number in the name hides the claim")
        if abbreviates(words):
            problems.append("test-name-letter: a one letter word abbreviates something")
        if name.startswith(SLOP_STEMS):
            problems.append("test-name-stem: a filler stem stands where the subject belongs")
        if set(ladder_words) & SLOP_WORDS:
            problems.append("test-name-slop: a placeholder stands where the subject belongs")
        if not set(ladder_words) & CLAIM_WORDS:
            problems.append("test-name-noun-only: the name never says what the test establishes")

    elif surface == "heading":
        body = DATE.sub("", name).strip()
        head_words = words_of(body)
        # A heading is a title, so a short one is a title and not a refusal. What is refused
        # is a title that says nothing: a bare number, a placeholder, or an abbreviation.
        if head_words and all(word.isdigit() for word in head_words):
            problems.append("heading-bare-number: the title is a number and nothing else")
        if abbreviates(head_words):
            problems.append("heading-letter: a one letter word abbreviates something")
        if set(word.lower() for word in head_words) & SLOP_WORDS:
            problems.append("heading-slop: a placeholder stands where the subject belongs")

    elif surface == "message":
        if name.count(";") >= 2:
            problems.append("message-semicolon: clauses fused into one line")
        if DANGLING.search(name.strip()):
            problems.append("message-truncated: the sentence ends mid-thought")
        if name.strip().startswith("**") and name.strip().endswith("**"):
            problems.append("message-lead-only: the lead survived, the rule did not")

    elif surface == "code":
        if any(len(part) == 1 for part in re.split(r"[-_]", name) if part):
            problems.append("code-letter: a one letter segment abbreviates something")

    count = len(problems)
    ladder = "whole" if count == 0 else "annotated" if count == 1 else "lossy" if count == 2 else "shorthand"
    return ladder, problems


NAME_CASE = re.compile(r"(?<=[a-z])(?=[A-Z])|_")


def scan_text(text: str, relative: str) -> list[dict]:
    rows: list[dict] = []
    surfaces = [
        ("test", RUST_TEST),
        ("test", PY_TEST),
        ("test", JS_TEST),
        ("heading", HEADING),
        ("message", MESSAGE),
        ("code", CODE),
    ]
    for surface, pattern in surfaces:
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            if not name:
                continue
            # An f-string carries quotes inside its braces, so a capture with unbalanced braces
            # is a parse fragment and not a message. Judging it produced six false refusals on
            # the first run, which is the gate reporting its own parser and not the prose.
            if name.count("{") != name.count("}"):
                continue
            line = text.count("\n", 0, match.start()) + 1
            ladder, problems = judge(name, surface)
            rows.append(
                {
                    "surface": surface,
                    "file": relative,
                    "line": line,
                    "name": name[:160],
                    "ladder": ladder,
                    "problems": problems,
                }
            )
    return rows


def scan_repo(repo: Path) -> list[dict]:
    rows: list[dict] = []
    targets: list[Path] = []
    for name in ("AGENTS.md", "README.md"):
        if (repo / name).exists():
            targets.append(repo / name)
    for folder in ("docs", "tools", "core/src", "src"):
        base = repo / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix in {".md", ".rs", ".py", ".js", ".mjs", ".ts"} and path.is_file():
                targets.append(path)
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            relative = str(path.relative_to(repo))
        except ValueError:
            relative = str(path)
        rows.extend(scan_text(text, relative))
    return rows


def selftest() -> int:
    cases = [
        ("a_counter_dump_is_shorthand", "test", True),
        ("a_dump_is_shorthand", "test", True),
        ("test_the_thing", "test", True),
        ("misc_works", "test", True),
        ("a_bold_lead_with_no_rule_under_it_is_refused_as_a_lossy_line", "test", False),
        ("a_cancelled_compile_ends_as_cancelled_and_never_as_done", "test", False),
        ("4.2", "heading", True),
        ("tmp notes", "heading", True),
        ("Lost the flags", "heading", False),
        ("2026-11-20 — the copy gate reads the wrappers and the pages were swept", "heading", False),
        ("The dock is hidden while the strip is held, and restored on quit; it polls 2s; it ends.", "message", True),
        ("WASM-BUILD", "code", False),
        ("entry-present", "code", False),
    ]
    failures = 0
    for name, surface, should_refuse in cases:
        _, problems = judge(name, surface)
        if bool(problems) != should_refuse:
            failures += 1
            print(f"  [FAIL] {surface}: {name} -> {problems}")
    print(f"name-prose selftest {'OK' if failures == 0 else 'FAILED'} {len(cases) - failures}/{len(cases)}")
    return 1 if failures else 0


def discover() -> list[Path]:
    roots = [Path("<home>/Documents"), Path("F:/Documents")]
    repos = []
    for root in roots:
        if not root.exists():
            continue
        for child in sorted(root.iterdir()):
            if (child / "AGENTS.md").exists():
                repos.append(child)
    return repos


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", action="append", default=[])
    parser.add_argument("--family", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    repos = [Path(item) for item in args.repo] or (discover() if args.family else [Path(".")])
    everything: list[dict] = []
    for repo in repos:
        rows = scan_repo(repo)
        refused = [row for row in rows if row["problems"] and row["surface"] != "code"]
        everything.extend({"repo": str(repo), **row} for row in rows)
        by_surface: dict[str, int] = {}
        for row in refused:
            by_surface[row["surface"]] = by_surface.get(row["surface"], 0) + 1
        print(f"{repo.name:<28} {len(rows):>5} names  {len(refused):>4} refused  {by_surface}")

    refused = [row for row in everything if row["problems"] and row["surface"] != "code"]
    for row in refused[:40]:
        print(f"HIT  {row['surface']:<8} {row['file']}:{row['line']}  {row['name']}")
        for problem in row["problems"]:
            print(f"     {problem}")
    if len(refused) > 40:
        print(f"... {len(refused) - 40} more refused rows; use --json for the full table")

    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"schema": "notation.name-judge/1", "rows": everything}, indent=2) + "\n", encoding="utf-8")
        # The family hashes with blake3, so the artifact carries a blake3 digest beside it.
        try:
            import blake3

            digest = blake3.blake3(target.read_bytes()).hexdigest()
            sidecar = target.with_suffix(".blake3")
            sidecar.write_text(f"blake3:{digest}\n", encoding="utf-8")
            print(f"wrote {target} blake3:{digest}")
        except ImportError:
            print(f"wrote {target} (no blake3 module, no digest written)")

    refused_total = sum(1 for row in everything if row["problems"] and row["surface"] != "code")
    return 1 if refused_total and args.check else 0


if __name__ == "__main__":
    sys.exit(main())
