"""Build the hero vmdl copy that declares the tail source's tail component.

The tail is not a body replacement and not a competing body-group choice.  This
keeps the hero's RenderMeshList and existing default choice, appends ``tail`` to
the default choice, and adds the tail source's cloth chain as a new Softbody
section.  It never writes the original extraction.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import modeldoc

EXTRACTIONS = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "Blender Foundation"
    / "Blender"
    / "5.4"
    / "datafiles"
    / "hero_retarget_workbench"
    / "artifacts"
    / "extractions"
)



def args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero", required=True, help="the hero .vmdl to copy")
    parser.add_argument("--source", required=True, help="the tail source .vmdl")
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def block(lines: list[str], klass: str, name: str | None = None) -> tuple[int, int]:
    for index, line in enumerate(lines):
        if line.strip() == f'_class = "{klass}"':
            start = index - 1
            while start >= 0 and not lines[start].strip().endswith("{"):
                start -= 1
            depth = 0
            for end in range(start, len(lines)):
                depth += modeldoc._brace_delta(lines[end])
                if depth == 0:
                    if name is None or any(
                        lines[item].strip() == f'name = "{name}"'
                        for item in range(start, end + 1)
                    ):
                        return start, end
                    break
    raise ValueError(f"block-missing: {klass} {name or ''}")


def with_comma(lines: list[str]) -> list[str]:
    """Return a block whose closing line has exactly one trailing comma."""
    block_lines = list(lines)
    block_lines[-1] = block_lines[-1].rstrip().rstrip(",") + ","
    return block_lines


def main() -> int:
    options = args()
    hero = Path(options.hero)
    source = Path(options.source)
    report = {"checks": {}, "errors": []}
    text = hero.read_text(encoding="utf-8", errors="replace")
    # A hero may carry no body groups at all (Haze has twelve always-drawn
    # meshes and no BodyGroupList), so the tail is only a choice when the hero
    # already has the group; otherwise it is a plain render mesh.
    existing = [item.name for item in modeldoc.body_groups(text)]
    group_name = "default" if "default" in existing else ""
    merged = modeldoc.add_render_mesh_file(
        text,
        name="tail",
        filename="/".join(hero.parts[hero.parts.index("models"):-1]) + f"/{hero.stem}_tail.dmx",
        bodygroup=group_name,
        choice="body",
    )
    text = merged.text
    report["checks"]["tail_render_mesh"] = "tail" in [item.name for item in modeldoc.render_mesh_files(text)]
    if group_name:
        group = next(item for item in modeldoc.body_groups(text) if item.name == group_name)
        report["checks"]["tail_in_default_choice"] = "tail" in group.meshes
    else:
        report["checks"]["tail_in_default_choice"] = True

    # RenderMeshList membership alone is not enough: a mesh outside every
    # LODGroup is compiled but never drawn. Add the same tail mesh to every
    # source LOD level so it stays visible at all camera distances.
    lines = text.splitlines()
    lod_section = modeldoc.sections(text).get("LODGroupList")
    lod_count = 0
    if lod_section is not None:
        for start, end in modeldoc._blocks(lines, lod_section, "LODGroup"):
            open_index = modeldoc._list_open(lines, start, end, "mesh_references")
            if open_index is None:
                continue
            mesh_lines = [
                item.strip()
                for item in lines[open_index + 1 : modeldoc._list_close(lines, open_index)]
                if 'mesh_name = "tail"' in item
            ]
            if mesh_lines:
                lod_count += 1
                continue
            indent = modeldoc._indent(lines[open_index]) + "\t"
            modeldoc._insert_in_list(
                lines,
                open_index,
                [f"{indent}{{", f'{indent}\tmesh_name = "tail"', f"{indent}}},"],
            )
            lod_count += 1
    text = "\n".join(lines)
    report["checks"]["tail_in_lod_groups"] = lod_count

    shape_blocks = []
    source_text = source.read_text(encoding="utf-8", errors="replace")
    # The tail source may carry no cloth at all (Tengu has no tail_stiffen); the
    # tail mesh still renders, so the softbody transplant is best effort.
    # A tail source carries a cloth chain in its own vmdl; the stiffen node is
    # optional and named per hero, so it is transplanted only when present.
    has_cloth = (
        '_class = "ClothParams"' in source_text
        and '_class = "ClothChain"' in source_text
    )
    report["checks"]["source_cloth"] = has_cloth
    if has_cloth:
        wolf_text = source.read_text(encoding="utf-8", errors="replace")
        wolf_lines = wolf_text.splitlines()
        hero_names = set(
            name.decode("ascii", "ignore")
            for name in re.findall(rb"[A-Za-z0-9_.-]{2,80}", hero.with_name(f"{hero.stem}_body.dmx").read_bytes())
        )
        params = block(wolf_lines, "ClothParams")
        chain = block(wolf_lines, "ClothChain", "tail_0")
        try:
            stiffen = block(wolf_lines, "ClothEffectStiffen", "tail_stiffen")
        except ValueError:
            stiffen = None
        shapes = []
        for index, line in enumerate(wolf_lines):
            if line.strip().startswith('_class = "ClothShape'):
                klass = line.strip().split('"')[1]
                name = next(
                    (
                        item.strip().split('"')[1]
                        for item in wolf_lines[index + 1 : index + 8]
                        if item.strip().startswith("name = ")
                    ),
                    None,
                )
                start, end = block(wolf_lines, klass, name)
                parent = next(
                    (item.strip().split('"')[1] for item in wolf_lines[start:end + 1] if item.strip().startswith("parent_bone =")),
                    "",
                )
                if parent and parent in hero_names:
                    shapes.append((start, end))
        shape_blocks = []
        seen = set()
        for start, end in shapes:
            body = "\n".join(wolf_lines[start:end + 1])
            if body not in seen:
                seen.add(body)
                shape_blocks.append(with_comma(wolf_lines[start:end + 1]))

        children = []
        children.extend(with_comma(wolf_lines[params[0]:params[1] + 1]))
        children.extend([
            "\t\t\t\t\t{",
            '\t\t\t\t\t\t_class = "Folder"',
            "\t\t\t\t\t\tchildren = ",
            "\t\t\t\t\t\t[",
            *[f"\t{line}" for line in with_comma(wolf_lines[chain[0]:chain[1] + 1])],
            "\t\t\t\t\t\t]",
            '\t\t\t\t\t\tname = "cloth"',
            "\t\t\t\t\t},",
        ])
        for shape in shape_blocks:
            children.extend(shape)
        if stiffen is not None:
            children.extend(with_comma(wolf_lines[stiffen[0]:stiffen[1] + 1]))
        section = [
            "\t\t\t{",
            '\t\t\t\t_class = "Softbody"',
            "\t\t\t\tchildren = ",
            "\t\t\t\t[",
            *children,
            "\t\t\t\t]",
            "\t\t\t},",
        ]
        lines = text.splitlines()
        close = modeldoc._root_close(lines)
        previous = close - 1
        while previous >= 0 and not lines[previous].strip():
            previous -= 1
        if previous >= 0 and not lines[previous].rstrip().endswith((",", "{")):
            lines[previous] = lines[previous].rstrip() + ","
        lines[close:close] = section
        text = "\n".join(lines)

    # no source cloth: the tail is a render mesh only
    report["checks"]["softbody_added"] = False
    report["checks"]["tail_cloth_chain"] = False
    report["checks"]["tail_stiffen"] = False
    report["checks"]["collision_shapes"] = 0
    out = Path(options.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    softbody = modeldoc.sections(text).get("Softbody")
    report["checks"]["softbody_added"] = softbody is not None
    report["checks"]["tail_cloth_chain"] = softbody is not None and 'name = "tail_0"' in softbody.text
    report["checks"]["tail_stiffen"] = softbody is not None and 'name = "tail_stiffen"' in softbody.text
    report["checks"]["collision_shapes"] = len(shape_blocks)
    report["checks"]["body_unchanged"] = f'name = "body"' in text and f"{hero.stem}_body.dmx" in text
    report["original"] = str(hero)
    report["output"] = str(out)
    # Cloth is optional; the tail being declared and drawn is not.
    report["ok"] = (
        not report["errors"]
        and report["checks"]["tail_render_mesh"]
        and report["checks"]["tail_in_default_choice"]
        and report["checks"]["tail_in_lod_groups"] > 0
    )
    Path(options.report).parent.mkdir(parents=True, exist_ok=True)
    Path(options.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
