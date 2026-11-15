"""Tile per-pose four-view renders into one side-by-side comparison sheet.

Columns are the builds being compared (shipped pak, pinned build, game pak01) and
rows are the four cardinal views the probe rendered.  The scale is identical in
every cell because the probe uses one orthographic scale, so silhouettes can be
compared by eye.

  python tools/pose_tile.py --dir artifacts/visual/shiv-compare \
      --pose idle:40 idle-pin:40 --out artifacts/visual/shiv-compare
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VIEWS = (0, 90, 180, 270)
COLUMN_TITLES = {"shipped": "shipped pak", "game": "game pak01", "pin": "pinned build"}


def _label(image: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(14, image.width // 40))
    draw.rectangle([0, 0, image.width, int(font.size * 1.9)], fill=(20, 20, 20))
    draw.text((6, 4), text, fill=(235, 235, 235), font=font)


def _cell(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--pose", nargs="+", required=True, help="label:frame [label:frame ...]")
    parser.add_argument("--out", required=True)
    parser.add_argument("--columns", default="shipped,pin,game")
    args = parser.parse_args()

    directory = Path(args.dir)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    columns = [value.strip() for value in args.columns.split(",")]

    for spec in args.pose:
        label, frame = spec.split(":", 1)
        grid = []
        for view in VIEWS:
            row = []
            for column in columns:
                # The pinned control is rendered as its own pose label, so its
                # files live under "<label>-pin-shipped-<view>.png".
                file_label = f"{label}-pin" if column == "pin" else label
                file_side = "shipped" if column == "pin" else column
                path = directory / f"{file_label}-{file_side}-{view:03d}.png"
                if not path.exists():
                    raise SystemExit(f"missing render {path}")
                cell = _cell(path)
                _label(cell, f"{COLUMN_TITLES.get(column, column)}  frame {frame}  view {view}\N{DEGREE SIGN}")
                row.append(cell)
            grid.append(row)
        width = sum(cell.width for cell in grid[0])
        height = sum(row[0].height for row in grid)
        sheet = Image.new("RGB", (width, height), (32, 32, 32))
        y = 0
        for row in grid:
            x = 0
            for cell in row:
                sheet.paste(cell, (x, y))
                x += cell.width
            y += row[0].height
        target = output / f"{label}-compare.png"
        sheet.save(target, optimize=True)
        print(f"tiled {target} {sheet.size[0]}x{sheet.size[1]} {target.stat().st_size} b")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
