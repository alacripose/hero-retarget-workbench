"""Re-express a clip's local bone rotations in the shipped skeleton's frames.

A clip's channel values are local transforms in the frames of the bones they were authored
on.  This port's clips come from two sources: the game's own body clips (authored on
`haze_skel.dmx`'s frames) and the Tengu tail donor (authored on Tengu's tail frames).  The
shipped skeleton has *our* frames for the same joints, and the head, the arms and the whole
tail therefore read every sample through a different frame: the owner sees it as a head and
arms rotated wrong and a tail that curls in on itself.

The mapping is the standard bind-relative one, applied to rotations only:

    world_source(j, t)  = world_source(parent(j), t) * local_source(j, t)
    world_target(j, t)  = world_source(j, t) * inv(rest_world_source(j)) * rest_world_target(j)
    local_target(j, t)  = inv(world_target(parent(j), t)) * world_target(j, t)

Positions are left exactly as authored: the complaints are rotational, and rewriting
translations is a second change with its own failure modes.

  blender -b --factory-startup --python tools/clip_retarget_frames.py -- \\
      --target <haze_tailbones.dmx> --bodies <dir> --tails <dir> --clips <dir> --out-dir <dir>
"""

from __future__ import annotations
import os

import argparse
import json
import math
import sys
from pathlib import Path

PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _model(root):
    return root["skeleton"] if "skeleton" in root.keys() else root


def _joints_with_transforms(model):
    """name -> (parent, transform element) for every joint in the tree."""
    rows: dict[str, tuple[str | None, object]] = {}

    def visit(element, parent):
        for child in element["children"] if "children" in element.keys() else []:
            if getattr(child, "type", "") != "DmeJoint":
                continue
            transform = child["transform"] if "transform" in child.keys() else None
            rows[child.name] = (parent, transform)
            visit(child, child.name)

    visit(model, None)
    return rows


# --- quaternion helpers (x, y, z, w) -------------------------------------------------


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _qconj(a):
    return (-a[0], -a[1], -a[2], a[3])


def _qnorm(a):
    length = math.sqrt(sum(component * component for component in a)) or 1.0
    return tuple(component / length for component in a)


def _qidentity():
    return (0.0, 0.0, 0.0, 1.0)


def _as_quat(item):
    return _qnorm(tuple(float(value) for value in item))


def _rest_quat(transform):
    if transform is None or "orientation" not in transform.keys():
        return _qidentity()
    return _qnorm(tuple(float(value) for value in transform["orientation"]))


def _rest_world(rows) -> dict[str, tuple]:
    """World rest rotation of every joint, from the document's own rests and parents."""
    out: dict[str, tuple] = {}
    for name in rows:
        chain, cursor = [], name
        while cursor is not None and cursor not in out:
            chain.append(cursor)
            cursor = rows[cursor][0]
        for joint in reversed(chain):
            parent, transform = rows[joint]
            base = out[parent] if parent in out else _qidentity()
            out[joint] = _qnorm(_qmul(base, _rest_quat(transform)))
    return out


def _channel_log(channel):
    """(times, values, stride) for a position/orientation channel."""
    log = channel["log"] if "log" in channel.keys() else None
    if log is None:
        return None
    layers = log["layers"] if "layers" in log.keys() else None
    if layers is None or not len(layers):
        return None
    layer = layers[0]
    times = [float(value) for value in layer["times"]] if "times" in layer.keys() else []
    # The log holds one value object per sample (a `Quaternion` for orientation, a vector for
    # position), not a flat float array; flattening them raised
    # "float() argument ... not 'Quaternion'".
    values = list(layer["values"]) if "values" in layer.keys() else []
    kind = getattr(log, "type", "")
    is_quat = "Quaternion" in kind or "quaternion" in kind
    return times, values, (4 if is_quat else 3)


def _rotate_clip(datamodel, target: Path, source_docs, clip_path: Path, out: Path) -> dict:
    target_rows = _joints_with_transforms(_model(datamodel.load(str(target)).root))
    target_rest_world = _rest_world(target_rows)

    document = datamodel.load(str(clip_path))
    clip_rows = _joints_with_transforms(_model(document.root))
    clip_rest_world = _rest_world(clip_rows)

    # Source hierarchy: where each joint's channel values were authored.
    source_rows: dict[str, tuple[str | None, object]] = {}
    source_rest_world: dict[str, tuple] = {}
    for path in source_docs:
        if path is None or not Path(path).is_file():
            continue
        rows = _joints_with_transforms(_model(datamodel.load(str(path)).root))
        for name in rows:
            source_rows.setdefault(name, rows[name])
        for name, quat in _rest_world(rows).items():
            source_rest_world.setdefault(name, quat)

    transform_to_joint = {
        id(transform): name for name, (_, transform) in clip_rows.items() if transform is not None
    }
    animations = document.root["animationList"]["animations"]
    rewritten = 0
    samples_out = 0
    for clip in animations:
        channels = clip["channels"] if "channels" in clip.keys() else []
        orientation = {}
        for channel in channels:
            if "toAttribute" not in channel.keys() or channel["toAttribute"] not in ("orientation", "o"):
                continue
            joint = transform_to_joint.get(id(channel["toElement"]))
            if joint is None:
                continue
            parsed = _channel_log(channel)
            if parsed is None:
                continue
            orientation[joint] = (channel, parsed)
        if not orientation:
            continue
        count = max(len(parsed[0]) for _, parsed in orientation.values())
        if not count:
            continue

        local: dict[str, list[tuple]] = {}
        for sample in range(count):
            world_source: dict[str, tuple] = {}
            world_target: dict[str, tuple] = {}
            ordered = [name for name in clip_rows]
            for name in ordered:
                if name in orientation:
                    _, (times, values, stride) = orientation[name]
                    index = min(sample, len(values) - 1)
                    quat = _as_quat(values[index]) if stride == 4 else _rest_quat(clip_rows[name][1])
                else:
                    quat = _rest_quat(clip_rows[name][1])
                parent = clip_rows[name][0]
                parent_world = world_source.get(parent, _qidentity())
                world_source[name] = _qnorm(_qmul(parent_world, quat))

                source_rest = source_rest_world.get(name, clip_rest_world.get(name, _qidentity()))
                target_rest = target_rest_world.get(name, clip_rest_world.get(name, _qidentity()))
                delta = _qmul(_qconj(source_rest), target_rest)
                world_target[name] = _qnorm(_qmul(world_source[name], delta))

                target_parent = target_rows[name][0] if name in target_rows else parent
                parent_target_world = world_target.get(target_parent, world_source.get(parent, _qidentity()))
                local.setdefault(name, []).append(
                    _qnorm(_qmul(_qconj(parent_target_world), world_target[name]))
                )

        for name, (channel, (times, values, stride)) in orientation.items():
            if stride != 4 or not values:
                continue
            frames = local.get(name, [])
            if not frames:
                continue
            # A `Quaternion` here is a `list` subclass (`Vector4`), four floats in x,y,z,w order,
            # with no attribute access and a two-argument constructor; the values are written by
            # slice assignment on the sample objects already in the layer.
            for index, sample in enumerate(values):
                quat = frames[min(index, len(frames) - 1)]
                sample[:] = [float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])]
            rewritten += 1
            samples_out += len(values)

    out.parent.mkdir(parents=True, exist_ok=True)
    document.write(str(out), "binary", 9)
    return {"clip": clip_path.name, "channels_rewritten": rewritten, "samples": samples_out}


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="the shipped skeleton document")
    parser.add_argument("--bodies", required=True, help="directory of the game's own clip bodies")
    parser.add_argument("--tails", required=True, help="directory of the tail donor documents")
    parser.add_argument("--clips", required=True, help="clip documents whose channels are rewritten")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    datamodel = _datamodel()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from work_record import finish, refuse_ephemeral_paths  # noqa: WPS433

    refuse_ephemeral_paths([args.out_dir, args.report])
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, failed = [], []
    for clip in sorted(Path(args.clips).glob("*.dmx")):
        sources = [Path(args.bodies) / clip.name, Path(args.tails) / clip.name]
        try:
            rows.append(_rotate_clip(datamodel, Path(args.target), sources, clip, out_dir / clip.name))
        except Exception as error:  # noqa: BLE001 - report the clip, keep the batch
            failed.append({"clip": clip.name, "error": f"{type(error).__name__}: {error}"})

    total = sum(row["channels_rewritten"] for row in rows)
    print(f"RETARGET {len(rows)} clips, {total} orientation channels re-expressed, {len(failed)} failed", flush=True)
    for row in failed[:5]:
        print(f"RETARGET FAIL {row['clip']}: {row['error']}", flush=True)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"target": args.target, "clips": rows, "failed": failed}, indent=2) + "\n", encoding="utf-8")
    finish(
        "clip_retarget_frames",
        [out_dir, args.report],
        f"re-expressed {total} orientation channels over {len(rows)} clips in {Path(args.target).name} frames, {len(failed)} failed",
        "pass" if rows and not failed else "fail",
        {"target": args.target},
    )
    return 0 if rows and not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
