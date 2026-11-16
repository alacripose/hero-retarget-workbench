"""Stop-slop and declauding checks for the strings a user reads.

The project's writing rules come from two skills: `stop-slop`
(github.com/hardikpandya/stop-slop) and `declauding`
(github.com/oaustegard/claude-skills). Their shared bans, applied to Blender
strings: em-dash drama, filler openers, intensifier adverbs, "not just X" and
"isn't just" staging, and the stock marketing words. This reads the addon's
string literals with `ast`, so comments and identifiers do not count and every
hit carries the line the user would see.

    python tools/ui_prose.py             # list hits
    python tools/ui_prose.py --check     # exit 1 when any hit remains
    python tools/ui_prose.py --json      # machine-readable hits

A path, a symbol or a one-word label is skipped: the rules are about sentences.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "blender" / "hero_retarget_workbench"

WORDS = (
    "seamless",
    "robust",
    "powerful",
    "effortless",
    "leverage",
    "utilize",
    "delve",
    "elevate",
    "unlock",
    "unleash",
    "streamline",
    "cutting-edge",
    "game-changer",
    "revolutionary",
    "holistic",
    "synergy",
    "best-in-class",
    "world-class",
    "state-of-the-art",
    "simply",
    "very",
    "really",
    "actually",
    "basically",
    "literally",
    "extremely",
    "highly",
    "truly",
    "quickly",
    "easily",
)
PHRASES = (
    "in order to",
    "it is worth noting",
    "it's worth noting",
    "note that",
    "please note",
    "needless to say",
    "at the end of the day",
    "not just",
    "isn't just",
    "is not just",
    "not only",
    "more than just",
    "little more than",
)
WORDS_RE = re.compile(r"\b(" + "|".join(re.escape(word) for word in WORDS) + r")\b", re.I)
PHRASES_RE = re.compile("|".join(re.escape(phrase) for phrase in PHRASES), re.I)
DASH_RE = re.compile("[—–]")
SENTENCE_RE = re.compile(r"[A-Za-z]{2,}\s+[A-Za-z]")


def _sentences(path: Path):
    tree = ast.parse(path.read_bytes())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if len(text) < 8 or not SENTENCE_RE.search(text):
                continue
            if "/" in text or "\\" in text:
                continue
            yield node.lineno, text


def scan(paths: list[Path]) -> list[dict]:
    hits: list[dict] = []
    for path in paths:
        for line, text in _sentences(path):
            for match in DASH_RE.finditer(text):
                hits.append({"file": path.name, "line": line, "rule": "em-dash", "text": text.strip()})
                break
            for match in PHRASES_RE.finditer(text):
                hits.append(
                    {"file": path.name, "line": line, "rule": f"phrase: {match.group(0).lower()}", "text": text.strip()}
                )
            for match in WORDS_RE.finditer(text):
                hits.append(
                    {"file": path.name, "line": line, "rule": f"word: {match.group(0).lower()}", "text": text.strip()}
                )
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when a hit remains")
    parser.add_argument("--json", action="store_true", help="print hits as JSON")
    parser.add_argument("--glob", default="*.py", help="files inside the addon to scan")
    args = parser.parse_args(argv)

    paths = sorted(ADDON.glob(args.glob))
    hits = scan(paths)
    if args.json:
        print(json.dumps(hits, indent=2))
    else:
        for hit in hits:
            print(f"{hit['file']}:{hit['line']} [{hit['rule']}] {hit['text'][:110]}")
        print(f"{len(hits)} hits in {len(paths)} files")
    if args.check and hits:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
