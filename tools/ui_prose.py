"""Stop-slop, declauding and the two-second budget for strings a user reads.

The project's writing rules come from two skills: `stop-slop`
(github.com/hardikpandya/stop-slop) and `declauding` (github.com/oaustegard/claude-skills),
and from Brass Meridian's two-second rule (`F:/Documents/brass-meridian/docs/PROSE.md`,
`tools/prose.mjs`): one sentence carries one idea, at most 24 words; a UI string is at
most 18 words and 92 characters. The owner's standing instruction is that anything in the
UI which cannot be scanned in two seconds is simplified, not explained.

This tool reads the addon's Python with `ast`, so comments and identifiers do not count.
It checks:

* every string literal in the addon for the shared bans: em-dash drama, filler openers,
  intensifier adverbs, "not just X" staging, and the stock marketing words;
* every string the user reads against the budget: operator labels and descriptions,
  property names and tooltips, enum items, `bl_info`, and the arguments of the surface
  helpers. An f-string is read as one template with each placeholder counted as a word,
  because a hint assembled from short fragments is still one long hint on screen;
* the professional-copy rules the owner named: no semicolon, no parenthetical aside, no
  mouse mechanics in a tooltip, no assistant voice, no hedge, no self-explanation, one
  sentence for a hint, two at most for a status line, and no trailing period on a label
  or a one-sentence tooltip;
* the viewport text drawn with `nudge_view._text`, which sits next to the model and was
  invisible to the old gate.

Refusal and error messages raised by the engine are diagnostics, not prose: they stay
exact and are not under the budget. `report(...)` status lines keep a closing period.

    python tools/ui_prose.py             # list hits
    python tools/ui_prose.py --check     # exit 1 when any hit or coverage loss remains
    python tools/ui_prose.py --json      # machine-readable hits
    python tools/ui_prose.py --selftest  # planted strings must be refused

A whole path, a symbol or a one-word label is skipped: the rules are about sentences.
`MIN_VISIBLE_STRINGS` is a ratchet. It is the count the extractor read when this rule set
landed, so a change that blinds the extractor refuses `gate-blinded` instead of passing
with fewer strings.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "blender" / "hero_retarget_workbench"

# Brass Meridian's two-second rule.
MAX_SENTENCE_WORDS = 24
MAX_UI_WORDS = 18
MAX_UI_CHARS = 92
MAX_VIEWPORT_WORDS = 14
MAX_VIEWPORT_CHARS = 80

# The coverage ratchet: raise it when the extractor legitimately reads more strings.
MIN_VISIBLE_STRINGS = 1040

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
SEMICOLON_RE = re.compile(";")
PARENTHETICAL_RE = re.compile(r"\([^)]*\s[^)]*\)")
MOUSE_RE = re.compile(r"\b(click|clicking|press|pressing|hover|hovering|right-click|left-click|mouse)\b", re.I)
VOICE_RE = re.compile(
    r"\b(you can|you'll|you will|lets you|let you|allows you|use this to|this will|"
    r"so you|helps you)\b",
    re.I,
)
HEDGE_RE = re.compile(r"\b(may|might|probably|usually|generally|optionally)\b", re.I)
SELF_RE = re.compile(
    r"\b(this (button|panel|section|field|option|control)|the following|below)\b",
    re.I,
)

# Kinds: how the string reaches the user, which decides the sentence limit.
KIND_HINT = "hint"
KIND_TOOLTIP = "tooltip"
KIND_LABEL = "label"
KIND_ENUM = "enum"
KIND_STATUS = "status"
KIND_VIEWPORT = "viewport"
KIND_INFO = "info"

# Calls whose string arguments are drawn or reported to the user.
HINT_HELPERS = {"hint", "bubble"}
LABEL_HELPERS = {
    "micro",
    "section",
    "title",
    "page",
    "stat",
    "label",
    "text",
    "primary",
    "path_row",
    "job",
    "glyphs",
    "row",
    "chip",
    "button",
    "field",
}
TOOLTIP_HELPERS = {"invoke_confirm"}
STATUS_HELPERS = {"report"}
# Keywords that carry a string the user reads.
LABEL_KEYWORDS = {"text", "name", "title"}
TOOLTIP_KEYWORDS = {"description", "detail", "message", "confirm_text"}
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


def _template(node: ast.AST) -> str | None:
    """One readable string from a literal, an f-string or a constant join.

    A placeholder becomes `X`, so an f-string is measured as the line it draws,
    not as its short literal fragments. That was the old gate's blind spot.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("X")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _template(node.left), _template(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _templates(node: ast.AST):
    """Every readable template in an expression, including f-string fields."""
    text = _template(node)
    if text is not None:
        yield text


def _argument_strings(node: ast.AST):
    """Templates passed through a container or a nested call, not an f-string split."""
    text = _template(node)
    if text is not None:
        yield text
        return
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            yield from _argument_strings(element)
    elif isinstance(node, ast.Dict):
        for value in node.values:
            yield from _argument_strings(value)
    elif isinstance(node, ast.Call):
        for argument in node.args:
            yield from _argument_strings(argument)
        for keyword in node.keywords:
            yield from _argument_strings(keyword.value)


def _visible(tree: ast.AST):
    """Every string Blender, a surface helper or the viewport puts in front of the user."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in VISIBLE_ATTRIBUTES:
                    kind = KIND_TOOLTIP if target.id == "bl_description" else KIND_LABEL
                    for text in _templates(node.value):
                        yield node.lineno, text, kind
                if isinstance(target, ast.Name) and target.id == "bl_info":
                    if isinstance(node.value, ast.Dict):
                        for key, value in zip(node.value.keys, node.value.values):
                            if isinstance(key, ast.Constant) and key.value in BL_INFO_KEYS:
                                for text in _templates(value):
                                    yield node.lineno, text, KIND_INFO
        if isinstance(node, ast.keyword) and node.arg == "items":
            # Enum items are (id, label, description); the last two are read.
            for element in ast.walk(node.value):
                if isinstance(element, ast.Tuple) and len(element.elts) > 1:
                    for part in element.elts[1:]:
                        for text in _templates(part):
                            yield node.lineno, text, KIND_ENUM
        if isinstance(node, ast.Call):
            raw = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            # The addon's private wrappers (`_hint`, `_section`, `_path_row`) are
            # the actual drawing surface; the unprefixed name is the same helper.
            name = raw.lstrip("_") if raw else raw
            kind = KIND_LABEL
            if name in HINT_HELPERS:
                kind = KIND_HINT
            elif name in TOOLTIP_HELPERS:
                kind = KIND_TOOLTIP
            elif name in STATUS_HELPERS:
                kind = KIND_STATUS
            elif raw in {"_text", "text"}:
                kind = KIND_VIEWPORT
            keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
            if name in HINT_HELPERS | LABEL_HELPERS | TOOLTIP_HELPERS | STATUS_HELPERS:
                for argument in node.args:
                    for text in _argument_strings(argument):
                        yield node.lineno, text, kind
                for keyword in node.keywords:
                    if keyword.arg in {"items"}:
                        continue
                    for text in _argument_strings(keyword.value):
                        yield node.lineno, text, kind
            elif keywords & (LABEL_KEYWORDS | TOOLTIP_KEYWORDS):
                for keyword in node.keywords:
                    if keyword.arg in LABEL_KEYWORDS:
                        for text in _templates(keyword.value):
                            yield node.lineno, text, KIND_LABEL
                    elif keyword.arg in TOOLTIP_KEYWORDS:
                        for text in _templates(keyword.value):
                            yield node.lineno, text, KIND_TOOLTIP


def _readable(text: str) -> bool:
    """True for a phrase a person reads, not a path, id or identifier."""
    if len(text) < 8 or not SENTENCE_RE.search(text):
        return False
    if " " not in text and ("/" in text or "\\" in text):
        return False
    return True


def _bans(text: str) -> list[str]:
    rules: list[str] = []
    if DASH_RE.search(text):
        rules.append("em-dash")
    for match in PHRASES_RE.finditer(text):
        rules.append(f"phrase: {match.group(0).lower()}")
    for match in WORDS_RE.finditer(text):
        rules.append(f"word: {match.group(0).lower()}")
    return rules


def _hit(path: Path, line: int, rule: str, text: str, kind: str) -> dict:
    return {"file": path.name, "line": line, "rule": rule, "text": text, "kind": kind}


def scan(paths: list[Path]) -> tuple[list[dict], int]:
    """Return every refusal and the number of visible strings the extractor read."""
    hits: list[dict] = []
    visible = 0
    seen: set[tuple[str, int, str, str]] = set()
    for path in paths:
        tree = ast.parse(path.read_bytes())
        for literal in _literals(tree):
            text = " ".join(literal.value.split())
            if not _readable(text):
                continue
            for rule in _bans(text):
                hits.append(_hit(path, literal.lineno, rule, text, KIND_INFO))
        for line, raw, kind in _visible(tree):
            text = " ".join(raw.split())
            if not _readable(text):
                continue
            key = (path.name, line, text, kind)
            if key in seen:
                continue
            seen.add(key)
            visible += 1
            words = _count_words(text)
            limit_words = MAX_VIEWPORT_WORDS if kind == KIND_VIEWPORT else MAX_UI_WORDS
            limit_chars = MAX_VIEWPORT_CHARS if kind == KIND_VIEWPORT else MAX_UI_CHARS
            if words > limit_words or len(text) > limit_chars:
                hits.append(_hit(path, line, f"ui-budget: {words} words / {len(text)} chars", text, kind))
            for sentence in _sentences_of(text):
                count = _count_words(sentence)
                if count > MAX_SENTENCE_WORDS:
                    hits.append(_hit(path, line, f"sentence-budget: {count} words", sentence, kind))
            match = CONDITIONAL_RE.search(text)
            if match:
                hits.append(_hit(path, line, f"conditional: {match.group(0).lower()[:40]}", text, kind))
            if SEMICOLON_RE.search(text):
                hits.append(_hit(path, line, "punctuation:semicolon", text, kind))
            match = PARENTHETICAL_RE.search(text)
            if match:
                hits.append(_hit(path, line, f"aside-parenthetical: {match.group(0)[:36]}", text, kind))
            match = MOUSE_RE.search(text)
            if match:
                hits.append(_hit(path, line, f"instruction:mouse: {match.group(0).lower()}", text, kind))
            match = VOICE_RE.search(text)
            if match:
                hits.append(_hit(path, line, f"voice:assistant: {match.group(0).lower()}", text, kind))
            match = HEDGE_RE.search(text)
            if match:
                hits.append(_hit(path, line, f"hedge: {match.group(0).lower()}", text, kind))
            match = SELF_RE.search(text)
            if match:
                hits.append(_hit(path, line, f"self-explain: {match.group(0).lower()}", text, kind))
            sentences = _sentences_of(text)
            limit_sentences = 1 if kind in {KIND_HINT, KIND_LABEL, KIND_ENUM, KIND_VIEWPORT, KIND_INFO} else 2
            if len(sentences) > limit_sentences:
                hits.append(_hit(path, line, f"sentences: {len(sentences)}", text, kind))
            if kind != KIND_STATUS and text.endswith("."):
                hits.append(_hit(path, line, "punctuation:trailing-period", text, kind))
    return hits, visible


def check(paths: list[Path]) -> tuple[list[dict], int, list[str]]:
    hits, visible = scan(paths)
    failures: list[str] = []
    if visible < MIN_VISIBLE_STRINGS:
        failures.append(
            f"gate-blinded: read {visible} visible strings, floor is {MIN_VISIBLE_STRINGS}; "
            "this gate is required to read the drawn copy, not fewer strings than it did before"
        )
    return hits, visible, failures


def selftest() -> int:
    """Planted strings: every rule must refuse its case, and clean copy must pass."""
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
        ('layout.label(text="Pick a pair")', None),
        ('hint(layout, "Join the meshes; the rig stays")', "punctuation:semicolon"),
        ('hint(layout, "Import the other meshes (hair, jacket) onto the rig")', "aside-parenthetical"),
        ('operator("dmf.x", description="Click the bone to select it")', "instruction:mouse"),
        ('hint(layout, "This will write the clips to disk")', "voice:assistant"),
        ('hint(layout, "The scan may take a minute")', "hedge: may"),
        ('hint(layout, "This panel imports the model")', "self-explain"),
        ('hint(layout, f"Join {count} meshes into the export and keep the rest of the scene '
         'untouched while the addon writes the file in the background")', "ui-budget"),
        ('hint(layout, "Stop the queue. Imported clips keep their actions.")', "sentences: 2"),
        ('operator("dmf.x", description="Join the meshes.")', "punctuation:trailing-period"),
        ('hint(layout, "Join the decimated meshes so export reuses them")', None),
        ('_text("chain: picked bone and its mapped ancestors and every bone below it in the rig", 1, 2, 9)',
         "ui-budget"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "planted.py"
        for source, expected in planted:
            path.write_text(source + "\n", encoding="utf-8")
            rules = [hit["rule"] for hit in scan([path])[0]]
            if expected is None:
                if rules:
                    raise SystemExit(f"selftest FAILED: a clean string was refused: {rules}")
            elif not any(rule.startswith(expected) for rule in rules):
                raise SystemExit(f"selftest FAILED: {expected} was not refused: {rules}")
            checks += 1
        # The extractor must see the f-string as one template, not as fragments.
        path.write_text('hint(layout, f"Join {count} meshes")\n', encoding="utf-8")
        seen = list(_visible(ast.parse(path.read_bytes())))
        if not seen or "X" not in seen[0][1]:
            raise SystemExit(f"selftest FAILED: the f-string template was not read: {seen}")
        checks += 1
    print(f"ui-prose selftest OK {checks} checks")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when a hit or a coverage loss remains")
    parser.add_argument("--json", action="store_true", help="print hits as JSON")
    parser.add_argument("--selftest", action="store_true", help="planted strings must be refused")
    parser.add_argument("--glob", default="*.py", help="files inside the addon to scan")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    paths = sorted(ADDON.glob(args.glob))
    hits, visible, failures = check(paths)
    if args.json:
        print(json.dumps({"hits": hits, "visible": visible, "failures": failures}, indent=2))
    else:
        for hit in hits:
            print(f"{hit['file']}:{hit['line']} [{hit['rule']}] {hit['text'][:110]}")
        for failure in failures:
            print(failure)
        print(f"{len(hits)} hit(s), {visible} visible string(s) in {len(paths)} file(s)")
    if args.check and (hits or failures):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
