"""Append the authored tail to a clip by copying channels, never a pose.

Every earlier merge imported the game's clip into Blender, wrote the tail action
and exported the body again. That round trip re-expresses each rotation against
the rig's rest, and the game's own values do not survive it: the sweep measures
bones up to 3.142 away on the family whose pelvis carries a fixed rotation, and
the owner sees the body lift when Shiv looks up, lift when he walks, and the
slide break on transition.

The body does not need to be touched at all. This reads the clip the game already
plays and the authored tail clip, and writes a third file that is the first one
plus the seven tail joints and their channel logs, copied value for value. Every
body channel in the output is the same element data as the input, so no axis
convention can drift.

  blender -b --python tools/dmx_tail_append.py -- \
      --body <game clip.dmx> --tail <authored clip.dmx> --out <merged.dmx> [--report <json>]

The tail joints are attached under the same parent they have in the tail clip
(`pelvis`), with that clip's rest transforms, so the tail's own basis is kept.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
# A tail chain is whatever the authored clip declares: Shiv carries tail_0..tail_5
# plus tail_end, Tengu tail_0..tail_7 plus tail_end.  The set is read from the
# tail clip, never assumed, so a port is not limited to one source's chain.
TAIL_BONES = ("tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end")
TAIL_NAME = re.compile(r"tail_(?:[0-9]+|end)$")
CHANNEL_ATTRS = ("position", "orientation", "scale")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", default="")
    parser.add_argument("--tail", default="")
    parser.add_argument("--out", default="")
    # Batch: one Blender session for a whole set, since a session costs far more
    # than the edit does.
    parser.add_argument("--bodies", default="", help="folder of game clip DMX")
    parser.add_argument("--tails", default="", help="folder of authored tail clip DMX")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--encoding", default="binary", choices=("binary", "binary_proto", "keyvalues2"))
    # The tail chain hangs off `pelvis`. Its rest and its channels were authored
    # against the old pelvis frame, which the game's pelvis differs from by a
    # 120-degree rotation about (1,1,1); without this the tail sits inside the
    # body until a clip moves it, and stretches out of the body when one does.
    parser.add_argument("--tail-rotate", default="", help="x,y,z,w applied to every tail channel")
    # The datamodel's own format version (22 here) is the model format, not the
    # binary DMX encoding version these clip files use.
    parser.add_argument("--encoding-ver", type=int, default=9)
    return parser.parse_args(argv)


def _quaternion(text: str):
    if not text:
        return None
    parts = [float(part) for part in text.replace(";", ",").split(",") if part.strip()]
    if len(parts) != 4:
        raise SystemExit("--tail-rotate needs x,y,z,w")
    return parts


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _rotate_vector(q, vector):
    x, y, z, w = q
    vx, vy, vz = (float(vector[0]), float(vector[1]), float(vector[2]))
    # v' = v + 2w(q x v) + 2 q x (q x v), with q already unit length.
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def _apply_tail_frame(layer, attribute: str, q) -> None:
    """Re-express one copied tail channel in the game's pelvis frame."""
    if q is None:
        return
    values = list(layer["values"])
    if attribute == "orientation":
        layer["values"] = _MAKE_ARRAY([tuple(_qmul(q, tuple(float(v) for v in value))) for value in values], type(values[0]))
    elif attribute == "position":
        layer["values"] = _MAKE_ARRAY([tuple(_rotate_vector(q, value)) for value in values], type(values[0]))


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _joints(root):
    skeleton = root["skeleton"]
    return skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]


def _clip(root):
    animations = root["animationList"]["animations"]
    return animations[0] if animations else None


def _clone(model, element, remap: dict, keep_name: bool = True):
    """Deep-copy `element` into `model`, resolving references through `remap`."""
    if element is None:
        return None
    if element in remap:
        return remap[element]
    clone = model.add_element(element.name if keep_name else "", element.type)
    remap[element] = clone
    for key in element.keys():
        value = element[key]
        clone[key] = _copy_value(model, value, remap)
    return clone


_MAKE_ARRAY = None
_ELEMENT_TYPE = None
_TAIL_FRAME = None


def _is_element(value) -> bool:
    # PulseSrcOps' Element is an OrderedDict; Vector/Array values are lists and
    # also carry a `type`, so identity of the container is what separates them.
    return isinstance(value, dict) and hasattr(value, "datamodel")


def _copy_value(model, value, remap: dict):
    if isinstance(value, list) and value and _is_element(value[0]):
        return _MAKE_ARRAY([_clone(model, item, remap) for item in value], _ELEMENT_TYPE)
    if _is_element(value):
        return _clone(model, value, remap)
    if isinstance(value, list):
        if type(value) is list:
            # A generic list needs the datamodel's own array wrapper, chosen from
            # what it holds: element references or scalars.
            if value and _is_element(value[0]):
                return _MAKE_ARRAY([_clone(model, item, remap) for item in value], _ELEMENT_TYPE)
            kind = float if value and isinstance(value[0], float) else int
            return _MAKE_ARRAY([kind(item) for item in value], kind)
        return value
    return value


def _body_times(clip) -> list[float]:
    """The clip's own time base, taken from the first position channel that has one."""
    for channel in clip["channels"]:
        bone, attribute = _channel_target(channel)
        if attribute != "position" or not bone:
            continue
        layers = channel["log"]["layers"]
        if layers and layers[0]["times"]:
            return [float(value) for value in layers[0]["times"]]
    return []


def _sample_at(times: list[float], values: list, when: float):
    """Linear sample of a channel at `when`, for scalars and for vectors."""
    if not values:
        return None
    if when <= times[0]:
        return values[0]
    if when >= times[-1]:
        return values[-1]
    low = 0
    high = len(times) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if times[middle] <= when:
            low = middle
        else:
            high = middle
    span = times[high] - times[low]
    blend = 0.0 if span <= 0 else (when - times[low]) / span
    left, right = values[low], values[high]
    if isinstance(left, (list, tuple)):
        return type(left)([a + (b - a) * blend for a, b in zip(left, right)])
    return left + (right - left) * blend


def _rebase(layer, times: list[float]) -> None:
    """Put a copied channel on the body's time base.

    An aim document is a matrix: the compiler builds its samples from the source's
    own time range. A tail channel that spans 0.0..1.041 while the body spans
    -0.1..0.833 widens that range, and the matrix comes out mapped to the wrong
    pitch - which is the body rotating off the ground when Shiv looks up.
    """
    source_times = [float(value) for value in layer["times"]]
    if not source_times or not times:
        return
    values = list(layer["values"])
    resampled = [_sample_at(source_times, values, when) for when in times]
    curves = list(layer["curvetypes"]) if "curvetypes" in layer else []
    layer["times"] = _MAKE_ARRAY(list(times), float)
    layer["values"] = _MAKE_ARRAY(resampled, type(resampled[0]))
    if curves:
        layer["curvetypes"] = _MAKE_ARRAY([curves[0]] * len(times), int)


def _channel_target(channel) -> tuple[str, str]:
    element = channel.get("toElement")
    return (getattr(element, "name", ""), str(channel.get("toAttribute", "")))


def _append_one(datamodel, body_path: Path, tail_path: Path, out: Path) -> dict:
    """Append `tail_path`'s seven tail joints and channels to `body_path`."""
    args = argparse.Namespace(body=str(body_path), tail=str(tail_path), out=str(out), encoding="binary", encoding_ver=9)
    return _run(datamodel, args)


def main() -> int:
    args = _arguments()
    datamodel = _datamodel()
    global _MAKE_ARRAY, _ELEMENT_TYPE
    _MAKE_ARRAY = datamodel.make_array
    _ELEMENT_TYPE = datamodel.Element
    global _TAIL_FRAME
    _TAIL_FRAME = _quaternion(args.tail_rotate)

    if args.bodies and args.tails and args.out_dir:
        bodies = Path(args.bodies)
        tails = Path(args.tails)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        done, failed = [], []
        for clip_file in sorted(bodies.glob("*.dmx")):
            tail_file = tails / clip_file.name
            if not tail_file.is_file():
                # No authored tail for this clip: ship the game's body unchanged
                # rather than dropping the clip.
                target = out_dir / clip_file.name
                target.write_bytes(clip_file.read_bytes())
                done.append({"clip": clip_file.stem, "body_only": True})
                print(f"BATCH-COPY {clip_file.stem} no tail, body unchanged", flush=True)
                continue
            try:
                report = _append_one(datamodel, clip_file, tail_file, out_dir / clip_file.name)
            except Exception as error:
                failed.append({"clip": clip_file.stem, "why": f"{type(error).__name__}: {error}"})
                continue
            done.append(report)
            print(f"BATCH {clip_file.stem} {report['bytes']}b joints={report['joints']}", flush=True)
        payload = {"appended": done, "failed": failed}
        if args.report:
            target = Path(args.report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"BATCH done {len(done)} appended, {len(failed)} failed")
        return 0 if done else 1

    if not (args.body and args.tail and args.out):
        print("APPEND-FAIL give --body/--tail/--out or --bodies/--tails/--out-dir")
        return 2
    report = _run(datamodel, args)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


def _run(datamodel, args) -> dict:
    """Append the tail to one clip and return what was written."""
    body = datamodel.load(args.body)
    tail = datamodel.load(args.tail)

    body_root = body.root
    tail_root = tail.root
    body_joints = _joints(body_root)
    tail_joints = _joints(tail_root)
    tail_by_name = {joint.name: joint for joint in tail_joints}
    chain = _tail_chain(tail_joints)
    if not chain:
        raise RuntimeError("tail clip declares no tail chain")
    missing = [name for name in chain if name not in tail_by_name]
    if missing:
        raise RuntimeError(f"tail clip lacks {missing}")

    body_clip = _clip(body_root)
    tail_clip = _clip(tail_root)
    if body_clip is None or tail_clip is None:
        raise RuntimeError("a clip has no animation")

    # The parent the authored tail hangs from, and its own chain order.
    parent_name = None
    for joint in tail_joints:
        for child in joint.get("children", []):
            if getattr(child, "name", "") == chain[0]:
                parent_name = joint.name
                break
        if parent_name:
            break
    body_by_name = {joint.name: joint for joint in body_joints}
    if parent_name not in body_by_name:
        raise RuntimeError(f"body clip has no parent joint {parent_name!r}")

    # Channels the tail clip authors for the tail bones, by (bone, attribute).
    tail_channels: dict[tuple[str, str], object] = {}
    for channel in tail_clip["channels"]:
        bone, attribute = _channel_target(channel)
        if bone in chain and attribute in CHANNEL_ATTRS:
            tail_channels[(bone, attribute)] = channel
    # A clip may stop one bone short of the chain: the authored tails carry 8 bones and 16 channels
    # while the tail MESH is skinned to 9 (`tail_end` is the tip).  Dropping the tip is not an
    # option — the owner's rule is that nothing the game binds may be dropped — so the tip inherits
    # the last segment's channels and is recorded in the receipt.
    inherited_tip: list[str] = []
    authored_attrs = {
        attribute for (bone, attribute) in tail_channels if bone in chain
    }
    for index, name in enumerate(chain):
        missing = [attr for attr in authored_attrs if (name, attr) not in tail_channels]
        if not missing:
            continue
        if index != len(chain) - 1:
            raise RuntimeError(
                f"tail clip authored no {missing} channel for {name}, which is not the chain tip"
            )
        donor = chain[index - 1]
        for attr in missing:
            source_channel = tail_channels.get((donor, attr))
            if source_channel is None:
                raise RuntimeError(f"tail clip authored no {attr} channel for {donor} to inherit")
            tail_channels[(name, attr)] = source_channel
        inherited_tip.append(name)
    if len(tail_channels) < len(chain) * 2:
        raise RuntimeError(f"tail clip authored only {len(tail_channels)} tail channels")

    remap: dict = {}
    parent = body_by_name[parent_name]
    added = []
    for name in chain:
        if name in body_by_name:
            # The body clip already declares it (a stock clip that carries the
            # tail); only its channels are needed.
            joint = body_by_name[name]
            added.append({"bone": name, "joint": "existing"})
        else:
            tail_joint = tail_by_name[name]
            joint = _clone(body, tail_joint, remap)
            # A clone carries its whole authored subtree.  The chain is rebuilt one
            # level per joint below, so a clone that keeps its children declares the
            # tail twice: the merged clip then holds 353 joint elements for 106 bones
            # and the compiled clip is bound by index into a 132-joint skeleton.
            if "children" in joint.keys():
                kids = joint["children"]
                while len(kids):
                    kids.pop()
            parent["children"].append(joint)
            # `jointList` is the flat list every consumer reads; attaching a
            # child to `pelvis` alone leaves the new joint unreachable.
            body_joints.append(joint)
            added.append({"bone": name, "joint": "added"})
        # Chain the tail: tail_0 under pelvis, tail_n under tail_(n-1).  Every joint
        # parented straight to `pelvis` keeps its rest at the pelvis origin, so the
        # chain collapses and the tail lies on the ground in every clip.
        parent = joint

    new_transform = {}
    for name in chain:
        joint = body_by_name.get(name) or remap[tail_by_name[name]]
        new_transform[name] = joint["transform"]

    body_channels = body_clip["channels"]
    body_times = _body_times(body_clip)
    copied = []
    for name in chain:
        for attribute in CHANNEL_ATTRS:
            source = tail_channels.get((name, attribute))
            if source is None:
                continue
            channel = body.add_element("", source.type)
            for key in source.keys():
                if key == "toElement":
                    channel[key] = new_transform[name]
                else:
                    channel[key] = _copy_value(body, source[key], remap)
            for layer in channel["log"]["layers"]:
                _rebase(layer, body_times)
                _apply_tail_frame(layer, attribute, _TAIL_FRAME)
            body_channels.append(channel)
            copied.append(
                {
                    "bone": name,
                    "attribute": attribute,
                    "samples": _samples(source),
                    "rebased_to": len(body_times),
                }
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # `format` is the datamodel's own name ('model'); `write` wants an encoding.
    body.write(str(out), args.encoding, args.encoding_ver)

    report = {
        "body": args.body,
        "tail": args.tail,
        "out": str(out),
        "encoding": args.encoding,
        "encoding_ver": args.encoding_ver,
        "bytes": out.stat().st_size,
        "parent": parent_name,
        "joints": len(_joints(datamodel.load(str(out)).root)),
        "added": added,
        "channels_copied": copied,
        "inherited_tip": inherited_tip,
    }
    print(
        f"APPEND {out.name} {report['bytes']}b joints={report['joints']} "
        f"tail_channels={len(copied)} encoding={args.encoding}/{args.encoding_ver}",
        flush=True,
    )
    return report


def _tail_chain(tail_joints) -> list[str]:
    """The authored clip's tail joints, root first and leaf last."""
    names = [joint.name for joint in tail_joints if TAIL_NAME.match(joint.name)]
    return sorted(names, key=lambda name: (name.endswith("_end"), int(name.split("_")[-1]) if not name.endswith("_end") else 0))


def _samples(channel) -> int:
    try:
        layers = channel["log"]["layers"]
        return len(layers[0]["values"]) if layers else 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
