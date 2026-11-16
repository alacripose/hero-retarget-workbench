"""Page parity for the Workbench: which page draws which action.

The UI grew page by page, so the same action could be drawn twice while another
page owned nothing. This reads the addon's own source instead of a hand-kept
list: panel classes, the page map in ``ui_props.py`` and every declared operator.

    python tools/ui_parity.py            # table, duplicates and undrawn actions
    python tools/ui_parity.py --check    # exit 1 on a cross-page duplicate or an empty page
    python tools/ui_parity.py --receipt artifacts/receipts/ui-parity.json
    python tools/ui_parity.py --markdown # table for docs/UI-PASS.md

An action may be drawn more than once on its own page (a minus and a plus button
are the same operator). Drawing it on two pages is what this refuses.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "blender" / "hero_retarget_workbench"

# Navigation is a surface, not a feature: the header and the Setup page both
# offer a way back to the workbench editor on purpose.
NAVIGATION = {"dmf.open_workbench", "dmf.clear_job", "dmf.cancel_weight_job"}

PANEL_RE = re.compile(r"^class (DMF_PT_\w+)\(Panel\):", re.M)
HELPER_RE = re.compile(r"^def (_\w+)\(", re.M)
OP_RE = re.compile(r'"(dmf\.[a-z_0-9]+)"')
DECL_RE = re.compile(r'bl_idname\s*=\s*"(dmf\.[a-z_0-9]+)"')

# Panels that draw at the root of both surfaces rather than owning a page.
ROOTS = {"DMF_PT_main", "DMF_PT_props_main"}


def _literal(name: str, source: Path):
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit(f"ui-parity-needs-{name.lower()}: {source} does not define {name}")


def page_map() -> tuple[dict[str, str], tuple[str, ...]]:
    source = ADDON / "ui_props.py"
    return _literal("PAGE_BY_ID", source), tuple(_literal("PAGES", source))


def _helper_ops(text: str) -> dict[str, set[str]]:
    """Module-level draw helpers, so a row built by `_hero_picker` still counts.

    Spans come from `ast`, not from the next top-level `def`: a helper followed by
    the panels would otherwise own every line to the end of the file and lend its
    whole op list to every page that calls it.
    """
    tree = ast.parse(text)
    lines = text.splitlines()
    helpers: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_"):
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])
            helpers[node.name] = set(OP_RE.findall(body))
    return helpers


def panels() -> dict[str, list[str]]:
    """Each panel class's own span, from `ast`, plus the draw helpers it calls.

    A regex run to the next `class` swallowed the module-level helpers defined
    between two panels, so Rules inherited the tail section's buttons.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(ADDON.glob("ui*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        helpers = _helper_ops(text)
        for node in ast.parse(text).body:
            if not isinstance(node, ast.ClassDef) or not node.name.startswith("DMF_PT_"):
                continue
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])
            names = set(OP_RE.findall(body))
            for helper, ops in helpers.items():
                if re.search(rf"\b{re.escape(helper)}\(", body):
                    names |= ops
            found[node.name] = sorted(names)
    return found


def declared() -> dict[str, str]:
    ops: dict[str, str] = {}
    for path in sorted(ADDON.glob("*.py")):
        for name in DECL_RE.findall(path.read_text(encoding="utf-8")):
            ops[name] = path.name
    return ops


def survey() -> dict:
    pages, order = page_map()
    drawn = panels()
    ops = declared()
    by_page: dict[str, list[str]] = defaultdict(list)
    by_operator: dict[str, list[str]] = defaultdict(list)
    unmapped: list[str] = []
    for panel, names in drawn.items():
        page = pages.get(panel)
        if page is None:
            if panel not in ROOTS:
                unmapped.append(panel)
            continue
        by_page[page].append(panel)
        for name in names:
            by_operator[name].append(page)
    duplicates = {
        name: sorted(set(found))
        for name, found in by_operator.items()
        if name not in NAVIGATION and len(set(found)) > 1
    }
    empty = [page for page in order if page not in by_page]
    missing = [name for name in by_operator if name not in ops]
    undrawn = sorted(name for name in ops if name not in by_operator and name not in NAVIGATION)
    return {
        "pages": list(order),
        "panels": {page: sorted(by_page.get(page, [])) for page in order},
        "actions": {page: sorted({op for panel in by_page.get(page, []) for op in drawn[panel]}) for page in order},
        "operator_pages": {name: sorted(set(found)) for name, found in sorted(by_operator.items())},
        "duplicates": duplicates,
        "empty_pages": empty,
        "unmapped_panels": sorted(unmapped),
        "unknown_actions": sorted(missing),
        "undrawn_actions": undrawn,
    }


def markdown(report: dict) -> str:
    lines = ["| Page | Panels | Actions |", "|---|---|---|"]
    for page in report["pages"]:
        actions = report["actions"].get(page, [])
        lines.append(
            f"| {page} | {', '.join(report['panels'][page]) or '-'} | "
            f"{', '.join(f'`{name}`' for name in actions) or '-'} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on duplicates or empty pages")
    parser.add_argument("--receipt", default="", help="write the survey as JSON")
    parser.add_argument("--markdown", action="store_true", help="print a table for the docs")
    args = parser.parse_args(argv)

    report = survey()
    if args.markdown:
        print(markdown(report))
    else:
        for page in report["pages"]:
            actions = report["actions"][page]
            print(f"{page:12} {len(report['panels'][page])} panels, {len(actions)} actions")
        print()
        print(f"duplicates: {report['duplicates'] or 'none'}")
        print(f"empty pages: {report['empty_pages'] or 'none'}")
        print(f"unmapped panels: {report['unmapped_panels'] or 'none'}")
        print(f"unknown actions: {report['unknown_actions'] or 'none'}")
        print(f"undrawn actions: {len(report['undrawn_actions'])}")
    if args.receipt:
        target = ROOT / args.receipt
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.check and (report["duplicates"] or report["empty_pages"] or report["unknown_actions"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
