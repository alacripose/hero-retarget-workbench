"""Splice the model's own `Skeleton` section into the addon vmdl, from the compiled resource.

`Source2Viewer-CLI -i <pak> -f models/heroes_staging/haze/haze.vmdl_c -o -` prints the modeldoc the
game loads, and that document's `Skeleton` is the model's real bone list: 120 bones on Haze,
carrying `weapon_hand_L`, `weapon_hand_R`, `weaponHier_*` and the 18 `*_end` leaves. The same tool's
`-d` decompile writes a *different* 120-bone `haze.vmdl` that omits all of those, so a vmdl rebuilt
from the `-d` text is not the model the game ships.

`--append-from` copies each `origin`/`angles` of a bone whose name starts with `--append-prefix` out
of another vmdl (the tail chain) and nests them under `--append-parent`, in name order, so the
model's tree matches the skeleton's (`tail_0 <- pelvis`, `tail_n <- tail_(n-1)`).

Usage:

    python tools/model_skeleton_from_compiled.py --print <modeldoc print.txt> --vmdl <haze.vmdl> \
        [--append-from <vmdl>] [--append-prefix tail] [--append-parent pelvis] [--report <json>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BONE_FIELD = re.compile(r"^\s*(origin|angles|do_not_discard)\s*=")
NEWLINE = chr(10)


def _skeleton_start(lines: list[str], what: str) -> int:
    start = next((i for i, line in enumerate(lines) if line.strip() == '_class = "Skeleton"'), None)
    if start is None:
        raise SystemExit(f"model-skeleton-from-compiled: {what} declares no Skeleton section")
    return start


def _section_span(lines: list[str], start: int) -> tuple[int, int]:
    children_at = next((i for i in range(start, len(lines)) if lines[i].strip() == "children ="), None)
    if children_at is None:
        raise SystemExit("model-skeleton-from-compiled: the Skeleton section has no children array")
    open_at = children_at + 1
    if lines[open_at].strip() != "[":
        raise SystemExit("model-skeleton-from-compiled: the children array does not open here")
    depth = 0
    for index in range(open_at, len(lines)):
        depth += lines[index].count("[") - lines[index].count("]")
        if depth == 0:
            return open_at, index
    raise SystemExit("model-skeleton-from-compiled: the children array never closes")


def _names(lines: list[str], span: tuple[int, int]) -> list[str]:
    return [
        match.group(1)
        for line in lines[span[0] + 1 : span[1]]
        if (match := re.match(r'\s*name = "([^"]+)"', line))
    ]


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


def _reindent(lines: list[str], delta: int) -> list[str]:
    out = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        out.append("\t" * max(0, _indent_of(line) + delta) + line.lstrip("\t"))
    return out


def _expand_inline_children(lines: list[str]) -> list[str]:
    """Turn `children = [  ]` into a three-line empty array, so nesting can insert into it."""
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("children") and "[" in line and "]" in line:
            pad = "\t" * _indent_of(line)
            out.extend([pad + "children = " + NEWLINE, pad + "[" + NEWLINE, pad + "]" + NEWLINE])
            continue
        out.append(line)
    return out


def _flat_bones(text: str, prefix: str) -> list[tuple[str, list[str]]]:
    """Every `name = "<prefix>…"` bone's name and its own scalar fields, in document order."""
    bones: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r'\s*name = "(' + re.escape(prefix) + r'[^"]*)"', line)
        if not match or match.group(1) in seen:
            continue
        name = match.group(1)
        fields = []
        for follow in lines[index + 1 : index + 8]:
            if follow.strip().startswith("}"):
                break
            if BONE_FIELD.match(follow):
                fields.append(follow.strip())
        if fields:
            bones.append((name, fields))
            seen.add(name)
    return bones


def _chain_text(bones: list[tuple[str, list[str]]], indent: int) -> list[str]:
    """Nest `bones` in order: the first under the parent, each later one under its predecessor."""

    def block(index: int, depth: int) -> list[str]:
        name, fields = bones[index]
        pad = "\t" * depth
        lines = [pad + "{" + NEWLINE, pad + '\t_class = "Bone"' + NEWLINE]
        lines.append(pad + '\tname = "' + name + '"' + NEWLINE)
        for field in fields:
            lines.append(pad + "\t" + field + NEWLINE)
        if index + 1 < len(bones):
            lines.append(pad + "\tchildren = " + NEWLINE)
            lines.append(pad + "\t[" + NEWLINE)
            lines.extend(block(index + 1, depth + 2))
            lines.append(pad + "\t]" + NEWLINE)
        lines.append(pad + "}," + NEWLINE)
        return lines

    return block(0, indent)


def _nest_under(lines: list[str], parent: str, addition: list[str]) -> list[str]:
    """Insert `addition` inside the `parent` bone's `children` array, creating it if absent."""
    start = next((i for i, line in enumerate(lines) if line.strip() == f'name = "{parent}"'), None)
    if start is None:
        raise SystemExit(f"model-skeleton-from-compiled: the print has no `{parent}` bone")
    parent_indent = _indent_of(lines[start])
    # The block's own `{` sits above the name line, so the brace count has to start there; counting
    # from the name line pairs a nested `{}` and puts the insertion point inside another bone.
    block_open = max(i for i in range(0, start) if lines[i].strip() == "{")
    end = None
    depth = 0
    for index in range(block_open, len(lines)):
        depth += lines[index].count("{") - lines[index].count("}")
        if depth == 0 and index > block_open:
            end = index
            break
    if end is None:
        raise SystemExit(f"model-skeleton-from-compiled: `{parent}` never closes")

    children_at = next(
        (i for i in range(start, end) if lines[i].strip().startswith("children")), None
    )
    if children_at is None:
        pad = "\t" * (parent_indent + 1)
        inserted = [pad + "children = " + NEWLINE, pad + "[" + NEWLINE]
        return lines[:end] + inserted + addition + [pad + "]" + NEWLINE] + lines[end:]

    depth = 0
    for index in range(children_at + 1, end + 1):
        depth += lines[index].count("[") - lines[index].count("]")
        if depth == 0:
            return lines[:index] + addition + lines[index:]
    raise SystemExit(f"model-skeleton-from-compiled: `{parent}` children array never closes")


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", required=True, help="Source2Viewer print of the compiled model")
    parser.add_argument("--vmdl", required=True)
    parser.add_argument("--append-from", default="")
    parser.add_argument("--append-prefix", default="tail")
    parser.add_argument("--append-parent", default="pelvis")
    parser.add_argument("--out", default="")
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    print_path, vmdl_path = Path(args.print), Path(args.vmdl)
    print_lines = print_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    print_span = _section_span(print_lines, _skeleton_start(print_lines, "the print"))
    print_names = _names(print_lines, print_span)
    if len(print_names) < 100:
        raise SystemExit(
            f"model-skeleton-from-compiled: the print's Skeleton has {len(print_names)} bones; a "
            "model with fewer than 100 is not the compiled document"
        )

    vmdl_lines = vmdl_path.read_text(encoding="utf-8", errors="surrogateescape").splitlines(keepends=True)
    vmdl_span = _section_span(vmdl_lines, _skeleton_start(vmdl_lines, "the vmdl"))
    vmdl_names = _names(vmdl_lines, vmdl_span)

    shift = _indent_of(vmdl_lines[vmdl_span[0] + 1]) - _indent_of(print_lines[print_span[0] + 1])
    body = _expand_inline_children(
        _reindent(print_lines[print_span[0] + 1 : print_span[1]], shift)
    )

    appended_names: list[str] = []
    if args.append_from:
        source_text = Path(args.append_from).read_text(encoding="utf-8", errors="surrogateescape")
        bones = [
            (name, fields)
            for name, fields in _flat_bones(source_text, args.append_prefix)
            if name not in print_names
        ]
        bones.sort(key=lambda pair: (len(pair[0]), pair[0]))
        if not bones:
            raise SystemExit(
                f"model-skeleton-from-compiled: no `{args.append_prefix}` bone in the append source"
            )
        parent_line = next(
            i for i, line in enumerate(body) if line.strip() == f'name = "{args.append_parent}"'
        )
        chain = _chain_text(bones, _indent_of(body[parent_line]) + 1)
        body = _nest_under(body, args.append_parent, chain)
        appended_names = [name for name, _ in bones]

    out_lines = vmdl_lines[: vmdl_span[0] + 1] + body + vmdl_lines[vmdl_span[1] :]
    out_path = Path(args.out) if args.out else vmdl_path
    out_path.write_text("".join(out_lines), encoding="utf-8", errors="surrogateescape")

    check_lines = out_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    check_names = _names(check_lines, _section_span(check_lines, _skeleton_start(check_lines, "the output")))
    text_out = "".join(out_lines)
    report = {
        "print": str(print_path),
        "vmdl": str(vmdl_path),
        "out": str(out_path),
        "bones_in_print": len(print_names),
        "bones_before": len(vmdl_names),
        "bones_after": len(check_names),
        "appended": appended_names,
        "order_matches": check_names == print_names + appended_names,
        "added": [name for name in print_names if name not in vmdl_names],
        "removed": [name for name in vmdl_names if name not in set(print_names) | set(appended_names)],
        "braces_balanced": text_out.count("{") == text_out.count("}"),
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(
        f"MODEL-SKELETON bones {len(vmdl_names)} -> {len(check_names)} "
        f"order_matches={report['order_matches']} appended={len(appended_names)} "
        f"removed={len(report['removed'])} braces={report['braces_balanced']}"
    )
    if check_names != print_names + appended_names or not report["braces_balanced"]:
        raise SystemExit("model-skeleton-from-compiled: the written section does not read back cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
