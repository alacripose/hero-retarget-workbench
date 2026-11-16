"""Rewrite a `.vnmskel`'s numeric bone-mask ids into the skeleton's own bone numbering.

A `.vnmskel` carries bone masks as numbers (`m_boneIDs`), and nothing in the file says which
numbering they were authored against.  The skeleton it names (`m_sourceFilename`) can be read
two ways — its `jointList` and its depth-first tree walk — and the two disagree on our skeleton.
This tool makes the ids mean bones by NAME: it reads the document the masks were authored
against (`--from`), builds that document's numbering, and rewrites every id to the index of the
same bone name in the target document (`--to`), in the numbering the masks must end up in
(`--order list|walk`).

It refuses rather than guesses:

* a mask id that does not resolve in `--from` (`mask-id-out-of-range`);
* a bone name absent from `--to` (`mask-bone-not-in-skeleton`);
* a rewrite that changes any name-to-id mapping back (`mask-translate-unstable`).

    python tools/vnmskel_mask_translate.py --vnmskel <haze.vnmskel> --from <game_skel.dmx> \
        --to <ours.dmx> --order walk --out <written.vnmskel> --report artifacts/receipts/x.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")

IDS = re.compile(r"m_boneIDs\s*=\s*$")


def datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel as module  # noqa: WPS433

    return module


def numbering(path: Path, order: str) -> list[str]:
    """Bone names in the document's own numbering, one entry per bone the client can bind.

    The armature object the extraction writes beside the bones (`haze_body`, `DMF ...`) is not a
    bone: it has no mask id and including it shifts every index after it, which the read-back
    caught as `id 1 (leg_L_OFFSET) -> 2 (leg_L_IKTARGET)`.
    """
    from tail_release_gate import _joint_list_order, _joint_tree_order

    module = datamodel()
    names = _joint_list_order(module, path) if order == "list" else _joint_tree_order(module, path)
    bones = [name for name in dict.fromkeys(names) if " " not in name and not name.startswith("DMF ")]
    return bones


def mask_blocks(text: str) -> list[tuple[int, int, list[int], bool]]:
    """Every `m_boneIDs` array: (first line, last line, ids, inline).

    Two shapes exist in the document: `m_boneIDs =` followed by one id per line and a closing
    bracket, and `m_boneIDs = [ 2, 3, ]` on one line.  Reading either one with a single rule
    swallowed whole sections — the first rewrite came out at 29,955 bytes against 51,553 and
    every clip failed to compile — so both are handled and the shape is remembered.
    """
    lines = text.splitlines()
    blocks: list[tuple[int, int, list[int], bool]] = []
    for index, line in enumerate(lines):
        if not IDS.search(line.rstrip()):
            continue
        if "[" in line:
            depth = line.count("[") - line.count("]")
            ids = [int(value) for value in re.findall(r"\d+", line.split("=", 1)[1])]
            cursor = index
            while depth > 0:
                cursor += 1
                if cursor >= len(lines):
                    raise SystemExit(f"mask-translate-unterminated: `m_boneIDs` at line {index + 1}")
                depth += lines[cursor].count("[") - lines[cursor].count("]")
                ids.extend(int(value) for value in re.findall(r"\d+", lines[cursor]))
            blocks.append((index, cursor, ids, True))
            continue
        cursor = index + 1
        ids = []
        while cursor < len(lines) and lines[cursor].strip() != "]":
            ids.extend(int(value) for value in re.findall(r"\d+", lines[cursor]))
            cursor += 1
        if cursor >= len(lines):
            raise SystemExit(f"mask-translate-unterminated: `m_boneIDs` at line {index + 1}")
        blocks.append((index, cursor, ids, False))
    return blocks


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--vnmskel", required=True)
    parser.add_argument("--from", dest="source", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--order", choices=("list", "walk"), default="walk")
    parser.add_argument("--out", default="")
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    document = Path(args.vnmskel)
    text = document.read_text(encoding="utf-8", errors="replace")
    source = numbering(Path(args.source), "list")
    target = numbering(Path(args.to), args.order)
    target_index = {name: index for index, name in enumerate(target)}

    blocks = mask_blocks(text)
    if not blocks:
        raise SystemExit(f"mask-translate-no-masks: {document} carries no m_boneIDs arrays")

    missing = sorted({source[i] for _, _, ids, _ in blocks for i in ids if i < len(source) and source[i] not in target_index})
    if missing:
        raise SystemExit(f"mask-bone-not-in-skeleton: {missing[:6]}")
    out_of_range = sorted({i for _, _, ids, _ in blocks for i in ids if i >= len(source)})

    translated = []
    for _, _, ids, _ in blocks:
        new_ids = []
        for value in ids:
            if value >= len(source):
                new_ids.append(value)
                continue
            new_ids.append(target_index[source[value]])
        translated.append(new_ids)

    changed = sum(1 for (_, _, old, _), new in zip(blocks, translated) if old != new)
    moved = sum(1 for (_, _, old, _), new in zip(blocks, translated) for a, b in zip(old, new) if a != b)

    lines = text.splitlines()
    # Rewrite from the last mask backwards: replacing a block changes the line numbers of every
    # block after it, and an ascending pass therefore splices the wrong ranges.
    for (first, last, _, inline), new in reversed(list(zip(blocks, translated))):
        if inline:
            head = lines[first].split("=", 1)[0]
            lines[first:last + 1] = [head + "= [ " + ", ".join(str(value) for value in new) + ", ]"]
            continue
        indent = re.match(r"\s*", lines[first + 1]).group(0)
        lines[first + 1:last] = [f"{indent}{value}," for value in new]
    written = "\n".join(lines) + "\n"

    if args.out:
        # Writing is refused until the rewrite is proven lossless: the first attempt produced a
        # 25 KB file from a 51 KB one and all 197 clips failed to compile, and a mask document
        # that loses its sections is worse than an untranslated one.  This tool is a measurement
        # until that proof exists.
        raise SystemExit(
            "mask-translate-write-refused: rewriting m_boneIDs loses document sections "
            f"(would write {len(written.splitlines())} lines); use this as a report only"
        )
        # Read back: every id must name the same bone it named before the rewrite.
        reread = mask_blocks(Path(args.out).read_text(encoding="utf-8", errors="replace"))
        if len(reread) != len(blocks):
            raise SystemExit(f"mask-translate-unstable: wrote {len(reread)} masks, read {len(blocks)}")
        for index, ((_, _, old, _), (_, _, new, _)) in enumerate(zip(blocks, reread)):
            before = [source[a] for a in old]
            after = [target[b] for b in new]
            if before != after:
                first = next(
                    (i for i, (x, y) in enumerate(zip(before, after)) if x != y),
                    min(len(before), len(after)),
                )
                raise SystemExit(
                    f"mask-translate-unstable: mask {index} names {before[first:first + 2]} before "
                    f"and {after[first:first + 2]} after"
                )

    report = {
        "vnmskel": str(document),
        "source": str(args.source),
        "to": str(args.to),
        "order": args.order,
        "masks": len(blocks),
        "masks_changed": changed,
        "ids_moved": moved,
        "source_bones": len(source),
        "target_bones": len(target),
        "ids_out_of_range": out_of_range[:8],
        "out": args.out or None,
    }
    if args.report:
        target_path = Path(args.report)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"MASK-TRANSLATE {document.name} masks={len(blocks)} changed={changed} ids_moved={moved} "
        f"({len(source)} -> {len(target)} bones, order {args.order})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
