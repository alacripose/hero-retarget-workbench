"""Point a compiled AnimGraph 2 skeleton at a tail-bearing DMX and widen its masks.

The VPK must not carry a ``.vnmskel_c``.  The game's model skeleton already has
the tail bones, so only the clip compiler needs a skeleton that can resolve the
new tracks.  This rewrites the *source* DMX reference and adds the tail chain to
the full-body bone masks, then the compiled ``.vnmclip_c`` files can be packed
without the skeleton resource.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _list_end(text: str, start: int) -> int:
    """Index of the ``]`` closing the list that starts at or after ``start``."""
    index = text.index("[", start)
    depth = 0
    for position in range(index, len(text)):
        if text[position] == "[":
            depth += 1
        elif text[position] == "]":
            depth -= 1
            if depth == 0:
                return position
    raise ValueError("unterminated list")


def _append_list(text: str, marker: str, values: list[str], start: int = 0) -> tuple[str, int]:
    index = text.index(marker, start)
    end = _list_end(text, index)
    body = text[index:end]
    indent = "\n\t\t\t\t\t"
    if "\n" in body:
        indent = body.rsplit("\n", 1)[0].rsplit("\n", 1)[-1]
        if indent.strip():
            indent = "\n\t\t\t\t\t"
    addition = "".join(f'{indent}"{value}",' for value in values)
    text = text[:end] + addition + "\n" + text[end:]
    return text, end + len(addition) + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--source", required=True, help="tail-bearing skeleton/model DMX, game-relative")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tail", default="tail_0,tail_1,tail_2,tail_3,tail_4,tail_5,tail_end")
    parser.add_argument("--report", default="")
    options = parser.parse_args()

    text = Path(options.skeleton).read_text(encoding="utf-8")
    tails = [item.strip() for item in options.tail.split(",") if item.strip()]
    text = re.sub(r'm_sourceFilename = "[^"]*"', f'm_sourceFilename = "{options.source}"', text, count=1)

    # High-LOD bones are a subset; adding tail bones keeps the whole chain in the
    # high-detail pose instead of dropping it at the first LOD threshold.
    marker = "m_highLODBones = "
    end = _list_end(text, text.index(marker))
    insertion = "".join(f'\n\t\t"{tail}",' for tail in tails) + "\n\t"
    text = text[:end] + insertion + text[end:]

    changed = []
    # Body masks that own the pelvis are the ones that must move the tail.  The
    # upper-body-only masks intentionally keep the tail following the lower body.
    pattern = re.compile(r'm_ID = "([^"]+)"')
    search_from = text.index("m_boneMaskSetDefinitions = ")
    matches = list(pattern.finditer(text, search_from))
    for match in reversed(matches):
        name = match.group(1)
        block_start = match.start()
        block_end = text.find("\n\t\t},", block_start)
        if block_end < 0:
            block_end = len(text)
        block = text[block_start:block_end]
        if '"pelvis"' not in block:
            continue
        ids_start = block_start + block.index("m_boneIDs = ")
        end = _list_end(text, ids_start)
        body = text[ids_start:end]
        indent = "\n\t\t\t\t\t"
        addition = "".join(f'{indent}"{tail}",' for tail in tails)
        text = text[:end] + addition + "\n" + text[end:]
        weights_start = text.index("m_weights = ", block_start)
        end = _list_end(text, weights_start)
        addition = "".join(f"{indent}1.0," for _ in tails)
        text = text[:end] + addition + "\n" + text[end:]
        changed.append(name)

    output = Path(options.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    report = {
        "skeleton": str(output),
        "source": options.source,
        "tail": tails,
        "masks": changed,
        "bytes": output.stat().st_size,
    }
    if options.report:
        target = Path(options.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
