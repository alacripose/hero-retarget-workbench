"""Measure the tail in the pinned release: chain, geometry, and clip drive.

The tail has been reported missing three times, each time for a different reason,
and each time the only evidence was somebody's eyes. This turns the question into
numbers a gate can hold:

1. **Chain** — the seven tail joints must exist in the shipped skeleton, hang off
   `pelvis` in order, and carry the model's own rest (the mesh is bound to that
   rest, so a moved rest collapses the tail into the body).
2. **Geometry** — the model must still declare `shiv_tail15.dmx`, and that mesh's
   own vertices must be weighted to the tail joints, not to the pelvis.
3. **Drive** — the shipped clips must carry the tail channels. Presence alone is
   not enough: a constant channel leaves the tail frozen at its rest pose.

It reads source data only — the skeleton DMX the release was compiled from, the
model's own mesh DMX, the modeldoc text, and the appended clips. It never decodes
a compiled resource.

  blender -b --python tools/tail_release_audit.py -- \
      --skeleton artifacts/skeleton/shiv_tailbones_release.dmx \
      --model artifacts/ab/skel-ours/models/heroes_staging/shiv/shiv_tail15.dmx \
      --vmdl artifacts/ab/skel-ours/models/heroes_staging/shiv/shiv.vmdl \
      --clips artifacts/shiv-appended2 --sample 12 \
      --tree artifacts/ab/release-tree --base-tree artifacts/ab/golden-skel \
      --report artifacts/receipts/tail-audit.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
TAIL = ("tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end")
VARIANCE_EPSILON = 1e-4


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--vmdl", default="")
    parser.add_argument("--clips", required=True)
    parser.add_argument("--sample", type=int, default=12)
    parser.add_argument("--tree", default="")
    parser.add_argument("--base-tree", default="")
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


def _md5(path: Path) -> str | None:
    if not path.is_file():
        return None
    handle = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            handle.update(block)
    return handle.hexdigest()


def _find(element, wanted: str):
    """Depth-first search for the first element of a given type."""
    if getattr(element, "type", "") == wanted:
        return element
    for key in element.keys():
        try:
            value = element[key]
        except Exception:  # a missing optional attribute is not a failure here
            continue
        for item in value if isinstance(value, (list, tuple)) else [value]:
            if hasattr(item, "keys"):
                found = _find(item, wanted)
                if found is not None:
                    return found
    return None


def _joint_table(datamodel, path: str) -> dict[str, dict]:
    """Every joint with its parent, rest head and rest orientation, in file order."""
    model = _find(datamodel.load(path).root, "DmeModel")
    order: list[str] = []
    rows: dict[str, dict] = {}

    def visit(element, parent: str | None) -> None:
        for child in element["children"] if "children" in element.keys() else []:
            if getattr(child, "type", "") != "DmeJoint":
                continue
            transform = child["transform"]
            order.append(child.name)
            rows[child.name] = {
                "parent": parent,
                "head": [round(float(value), 4) for value in transform["position"]],
                "orientation": [round(float(value), 4) for value in transform["orientation"]],
            }
            visit(child, child.name)

    visit(model, None)
    rows["__order__"] = {"order": order}
    return rows


def _delta(a: dict, b: dict) -> tuple[float, float]:
    distance = math.sqrt(sum((x - y) ** 2 for x, y in zip(a["head"], b["head"])))
    dot = abs(sum(x * y for x, y in zip(a["orientation"], b["orientation"])))
    dot = min(1.0, max(-1.0, dot))
    return distance, math.degrees(2.0 * math.acos(dot))


def _geometry(datamodel, path: str, joints: list[str]) -> dict:
    """Vertices of the model's tail mesh whose blend indices name a tail joint."""
    model = _find(datamodel.load(path).root, "DmeModel")
    mesh = _find(model, "DmeMesh")
    if mesh is None:
        return {"mesh": None}
    state = mesh["currentState"] if "currentState" in mesh.keys() else mesh["bindState"]
    indices = [int(value) for value in state["blendindices$0"]]
    weights = [float(value) for value in state["blendweights$0"]]
    tail_index = {index: name for index, name in enumerate(joints) if name in TAIL}
    counts = {name: 0 for name in TAIL}
    per_vertex = len(indices) // max(1, len(state["position$0"]))
    for vertex in range(len(state["position$0"])):
        used = set()
        for slot in range(per_vertex):
            position = vertex * per_vertex + slot
            if position >= len(indices):
                break
            if weights[position] <= 0.0:
                continue
            name = tail_index.get(indices[position])
            if name:
                used.add(name)
        for name in used:
            counts[name] += 1
    return {
        "mesh": mesh.name,
        "vertices": len(state["position$0"]),
        "joints_in_mesh": len(joints),
        "tail_vertices": counts,
        "tail_vertices_total": sum(counts.values()),
    }


def _clip_variance(datamodel, path: Path) -> dict:
    """Do this clip's tail channels actually move?"""
    model = datamodel.load(str(path))
    animations = model.root["animationList"]["animations"]
    clip = animations[0]
    seen = {}
    for channel in clip["channels"]:
        target = channel.get("toElement")
        name = getattr(target, "name", "")
        if name not in TAIL:
            continue
        attribute = str(channel.get("toAttribute", ""))
        layers = channel["log"]["layers"]
        values = layers[0]["values"] if layers else []
        flat = []
        for value in values:
            flat.append([float(part) for part in value] if isinstance(value, (list, tuple)) else [float(value)])
        if not flat:
            continue
        span = max(
            max(row[index] for row in flat) - min(row[index] for row in flat)
            for index in range(len(flat[0]))
        )
        seen[f"{name}.{attribute}"] = round(span, 6)
    ordered = [key for key in seen]
    return {
        "channels": len(seen),
        "moving": sorted(key for key, span in seen.items() if span > VARIANCE_EPSILON),
        "spread": seen,
    }


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel

    release = _joint_table(datamodel, args.skeleton)
    model = _joint_table(datamodel, args.model)
    release_order = release.pop("__order__")["order"]
    model_order = model.pop("__order__")["order"]

    chain = {name: release[name] for name in TAIL if name in release}
    parents = {name: chain[name]["parent"] for name in chain}
    present = [name for name in TAIL if name in chain]
    parenting_ok = (
        len(present) == len(TAIL)
        and parents.get("tail_0") == "pelvis"
        and all(parents.get(TAIL[index + 1]) == TAIL[index] for index in range(len(TAIL) - 1))
    )
    rest = {}
    for name in present:
        if name in model:
            distance, angle = _delta(chain[name], model[name])
            rest[name] = {"distance": round(distance, 4), "angle": round(angle, 3)}
    worst_rest = max((row["distance"] for row in rest.values()), default=None)
    worst_angle = max((row["angle"] for row in rest.values()), default=None)

    geometry = _geometry(datamodel, args.model, model_order)

    clips = sorted(Path(args.clips).glob("*.dmx"))
    with_channels = [clip.name for clip in clips if all(name.encode() in clip.read_bytes() for name in TAIL)]
    sampled = clips[: args.sample]
    variance = {clip.name: _clip_variance(datamodel, clip) for clip in sampled}
    moving = [name for name, row in variance.items() if row["moving"]]
    # A clip whose body carries no tail channels cannot drive a tail at all; the
    # question "does the shipped tail move" only applies to the clips that have the
    # channels in the first place, so the two are counted separately.
    sampled_with_channels = [name for name in variance if variance[name]["channels"] > 0]
    sampled_with_channels_moving = [name for name in sampled_with_channels if variance[name]["moving"]]

    packed = {}
    if args.tree and args.base_tree:
        relative = Path("models/heroes_staging/shiv/shiv.vmdl_c")
        packed = {
            "release_vmdl_md5": _md5(Path(args.tree) / relative),
            "base_vmdl_md5": _md5(Path(args.base_tree) / relative),
        }
        packed["identical_to_base"] = (
            packed["release_vmdl_md5"] is not None
            and packed["release_vmdl_md5"] == packed["base_vmdl_md5"]
        )

    declared = None
    if args.vmdl and Path(args.vmdl).is_file():
        text = Path(args.vmdl).read_text(encoding="utf-8", errors="replace")
        declared = {
            "render_mesh_files": text.count("RenderMeshFile"),
            "tail_mesh_declared": "shiv_tail15" in text,
        }

    receipt = {
        "schema": "hero-retarget-workbench.tail-audit/1",
        "skeleton": args.skeleton,
        "model": args.model,
        "chain_present": present,
        "chain_parents": parents,
        "chain_parenting_ok": parenting_ok,
        "chain_in_skeleton_order": [name for name in release_order if name in TAIL],
        "rest_vs_model": rest,
        "rest_worst_distance": worst_rest,
        "rest_worst_angle": worst_angle,
        "geometry": geometry,
        "modeldoc": declared,
        "clips_total": len(clips),
        "clips_with_tail_channels": len(with_channels),
        "variance_sampled": len(sampled),
        "variance_moving_clips": len(moving),
        "variance_static_clips": sorted(name for name in variance if name not in moving),
        "variance_sampled_with_channels": len(sampled_with_channels),
        "variance_sampled_with_channels_moving": len(sampled_with_channels_moving),
        "variance_sample": {clip.name: variance[clip.name]["spread"] for clip in sampled},
        "packed": packed,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        "TAIL "
        f"chain={len(present)}/7 parenting_ok={parenting_ok} "
        f"rest_worst={worst_rest}u/{worst_angle}deg "
        f"tail_vertices={geometry.get('tail_vertices_total')}/{geometry.get('vertices')} "
        f"clips_with_channels={len(with_channels)}/{len(clips)} "
        f"moving={len(moving)}/{len(sampled)} with_channels_moving={len(sampled_with_channels_moving)}/{len(sampled_with_channels)} "
        f"vmdl_identical={packed.get('identical_to_base')} "
        f"mesh_declared={(declared or {}).get('tail_mesh_declared')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
