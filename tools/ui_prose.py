"""Stop-slop, declauding and the two-second budget for strings a user reads.

The project's writing rules come from two skills: `stop-slop`
(github.com/hardikpandya/stop-slop) and `declauding` (github.com/oaustegard/claude-skills),
and from Brass Meridian's two-second rule (`F:/Documents/brass-meridian/docs/PROSE.md`,
`tools/prose.mjs`): one sentence carries one idea, at most 24 words; a UI string is at
most 18 words and 92 characters. The owner's standing instruction is that anything in the
UI which cannot be scanned in two seconds is simplified, not explained.

This tool reads the addon's Python with `ast`, so comments and identifiers do not count.
Two passes run:

* every string literal in the addon is checked for the shared bans: em-dash drama, filler
  openers, intensifier adverbs, "not just X" staging, and the stock marketing words;
* every string the user reads is checked against the budget as well: operator labels and
  descriptions, property names and tooltips, `hint`/`bubble`/`section`/`stat` text, status
  messages and confirmation dialogs. A visible string with a conditional ("if ... then")
  is refused, because that is the phrasing the owner named.

Refusal and error messages raised by the engine are diagnostics, not prose: they stay
exact and are not under the budget.

    python tools/ui_prose.py             # list hits
    python tools/ui_prose.py --check     # exit 1 when any hit remains
    python tools/ui_prose.py --json      # machine-readable hits
    python tools/ui_prose.py --selftest  # planted over-budget strings must be refused

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

# Brass Meridian's two-second rule.
MAX_SENTENCE_WORDS = 24
MAX_UI_WORDS = 18
MAX_UI_CHARS = 92

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
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’/.:%+-]*")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
CONDITIONAL_RE = re.compile(r"\bif\b[^.;]{0,60}\bthen\b", re.I)

# Calls whose string arguments are drawn or reported to the user.
VISIBLE_HELPERS = {
    "hint",
    "bubble",
    "micro",
    "section",
    "title",
    "page",
    "stat",
    "label",
    "operator",
    "prop",
    "prop_enum",
    "invoke_confirm",
    "report",
}
# Keywords that carry a string the user reads.
VISIBLE_KEYWORDS = {
    "text",
    "description",
    "detail",
    "message",
    "title",
    "confirm_text",
    "bl_label",
    "bl_description",
    "name",
}
# Operator and panel attributes read straight by Blender.
VISIBLE_ATTRIBUTES = {"bl_label", "bl_description"}
# The add-on's own entry in Preferences.
BL_INFO_KEYS = {"name", "description", "location", "category"}


def _count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def _sentences_of(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT.split(text) if _count_words(part) > 0]


def _literals(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node


def _visible(tree: ast.AST):
    """Every string literal Blender or a hint helper puts in front of the user."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in VISIBLE_ATTRIBUTES:
                    for literal in _literals(node.value):
                        yield literal.lineno, literal.value
                if isinstance(target, ast.Name) and target.id == "bl_info":
                    if isinstance(node.value, ast.Dict):
                        for key, value in zip(node.value.keys, node.value.values):
                            if isinstance(key, ast.Constant) and key.value in BL_INFO_KEYS:
                                for literal in _literals(value):
                                    yield literal.lineno, literal.value
        if isinstance(node, ast.keyword) and node.arg == "items":
            # Enum items are (id, label, description); the last two are read.
            for element in ast.walk(node.value):
                if isinstance(element, ast.Tuple) and len(element.elts) > 1:
                    for part in element.elts[1:]:
                        for literal in _literals(part):
                            yield literal.lineno, literal.value
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            values: list[str] = []
            keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
            if name in VISIBLE_HELPERS or keywords & VISIBLE_KEYWORDS:
                for argument in node.args:
                    for literal in _literals(argument):
                        values.append(literal.value)
                for keyword in node.keywords:
                    if keyword.arg in VISIBLE_KEYWORDS:
                        for literal in _literals(keyword.value):
                            values.append(literal.value)
            for value in values:
                yield node.lineno, value


def _readable(text: str) -> bool:
    """True for a phrase a person reads, not a path, id or identifier."""
    if len(text) < 8 or not SENTENCE_RE.search(text):
        return False
    return "/" not in text and "\\" not in text


def _bans(text: str) -> list[str]:
    rules: list[str] = []
    if DASH_RE.search(text):
        rules.append("em-dash")
    for match in PHRASES_RE.finditer(text):
        rules.append(f"phrase: {match.group(0).lower()}")
    for match in WORDS_RE.finditer(text):
        rules.append(f"word: {match.group(0).lower()}")
    return rules


def scan(paths: list[Path]) -> list[dict]:
    hits: list[dict] = []
    for path in paths:
        tree = ast.parse(path.read_bytes())
        for literal in _literals(tree):
            text = literal.value.strip()
            if len(text) < 8 or not SENTENCE_RE.search(text) or "/" in text or "\\" in text:
                continue
            for rule in _bans(text):
                hits.append({"file": path.name, "line": literal.lineno, "rule": rule, "text": text})
        for line, raw in _visible(tree):
            text = " ".join(raw.split())
            if not _readable(text):
                continue
            words = _count_words(text)
            if words > MAX_UI_WORDS or len(text) > MAX_UI_CHARS:
                hits.append(
                    {
                        "file": path.name,
                        "line": line,
                        "rule": f"ui-budget: {words} words / {len(text)} chars",
                        "text": text,
                    }
                )
            for sentence in _sentences_of(text):
                count = _count_words(sentence)
                if count > MAX_SENTENCE_WORDS:
                    hits.append(
                        {
                            "file": path.name,
                            "line": line,
                            "rule": f"sentence-budget: {count} words",
                            "text": sentence,
                        }
                    )
            match = CONDITIONAL_RE.search(text)
            if match:
                hits.append(
                    {
                        "file": path.name,
                        "line": line,
                        "rule": f"conditional: {match.group(0).lower()[:40]}",
                        "text": text,
                    }
                )
    return hits


def selftest() -> int:
    """Planted strings: the budget and the conditional rule must refuse them."""
    checks = 0
    planted = [
        ('hint(layout, "one two three four five six seven eight nine ten eleven twelve '
         'thirteen fourteen fifteen sixteen seventeen eighteen nineteen")', "ui-budget"),
        ('hint(layout, "This sentence runs on and on and keeps adding one more clause after '
         'another until the reader has lost the point entirely and has to start again")', "sentence-budget"),
        ('hint(layout, "If the file is missing then the scan stops and nothing is written")', "conditional"),
        ('operator("dmf.x", text="seamless conversion")', "word: seamless"),
        ('weight = EnumProperty(items=[("A", "Label", "one two three four five six seven '
         'eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen")])', "ui-budget"),
        ('bl_info = {"description": "one two three four five six seven eight nine ten eleven '
         'twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen"}', "ui-budget"),
        ('layout.label(text="Pick a pair.")', None),
    ]
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "planted.py"
        for source, expected in planted:
            path.write_text(source + "\n", encoding="utf-8")
            rules = [hit["rule"] for hit in scan([path])]
            if expected is None:
                if rules:
                    raise SystemExit(f"selftest FAILED: a clean string was refused: {rules}")
            elif not any(rule.startswith(expected) for rule in rules):
                raise SystemExit(f"selftest FAILED: {expected} was not refused: {rules}")
            checks += 1
    print(f"ui-prose selftest OK {checks} checks")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when a hit remains")
    parser.add_argument("--json", action="store_true", help="print hits as JSON")
    parser.add_argument("--selftest", action="store_true", help="planted over-budget strings must be refused")
    parser.add_argument("--glob", default="*.py", help="files inside the addon to scan")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

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
