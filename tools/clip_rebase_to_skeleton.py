"""Rebuild a clip's joint list to the skeleton the port ships.

A clip is bound to a skeleton by index.  The Haze port shipped 107-joint clips
against a 131-joint skeleton, and in game that rotated the head and arms and
dropped the tail out of the bind, even though the model and the skeleton were
both correct on their own.

This rewrites each clip's `skeleton` element to be a copy of the shipped
skeleton's tree, in the shipped order, and re-points every channel at the joint
with the same name.  Channel logs and times are untouched.

  blender -b --python tools/clip_rebase_to_skeleton.py -- \
      --skeleton <haze_model_tail.dmx> --clips artifacts/haze-tail/merged2 \
      --out-dir artifacts/haze-tail/merged3 [--report <json>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--clips", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def _joints(skeleton):
    """The joint ELEMENTS, from the children tree.

    A clip document's `skeleton.jointList` is a string array of names, not elements, so reading it
    here made every rebase fail with `'str' object has no attribute 'name'`.
    """
    return list(skeleton["children"]) if "children" in skeleton.keys() else []


def _rebase(datamodel, skeleton_model, clip_path: Path, out: Path) -> dict:
    from dmx_tail_append import _clone, _copy_value  # noqa: WPS433

    import dmx_tail_append as append_module

    append_module._MAKE_ARRAY = datamodel.make_array
    append_module._ELEMENT_TYPE = datamodel.Element

    clip = datamodel.load(str(clip_path))
    root = clip.root
    old_skeleton = root["skeleton"]
    old_joints = list(_joints(old_skeleton))

    remap: dict = {}
    source_skeleton = skeleton_model.root["skeleton"]
    source_joints = list(_joints(source_skeleton))

    clones: dict[str, object] = {}
    for joint in source_joints:
        clones[joint.name] = _clone(clip, joint, remap)
    for joint in source_joints:
        kids = list(joint["children"]) if "children" in joint.keys() else []
        clones[joint.name]["children"] = datamodel.make_array(
            [clones[child.name] for child in kids if child.name in clones], datamodel.Element
        )

    # The clip's own skeleton becomes the shipped skeleton: same joints, same order, same names.
    # Only the ROOTS go in `children`; listing every joint there made a flat tree and the
    # compiler answered `No animation data present` for all 197 clips.
    child_names = set()
    for joint in source_joints:
        for child in joint["children"] if "children" in joint.keys() else []:
            child_names.add(child.name)
    roots = [joint.name for joint in source_joints if joint.name not in child_names]
    old_skeleton["children"] = datamodel.make_array(
        [clones[name] for name in roots if name in clones], datamodel.Element
    )
    if "jointList" in old_skeleton.keys():
        old_skeleton["jointList"] = datamodel.make_array(
            [joint.name for joint in source_joints], str
        )

    channels = 0
    animation = root["animation"] if "animation" in root else None
    if animation is not None:
        for channel in animation["channels"]:
            target = channel.get("toElement", None)
            name = getattr(target, "name", "")
            if name in clones:
                channel["toElement"] = clones[name]
                channels += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    clip.write(str(out), "binary", 9)
    written = datamodel.load(str(out)).root["skeleton"]
    names = [joint.name for joint in _joints(written)]
    return {
        "clip": out.name,
        "joints_before": len(old_joints),
        "joints_after": len(names),
        "channels_repointed": channels,
        "matches_skeleton": names == [joint.name for joint in source_joints],
    }


def main() -> int:
    args = _arguments()
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    skeleton_model = datamodel.load(args.skeleton)
    clips = sorted(Path(args.clips).glob("*.dmx"))
    if not clips:
        raise SystemExit(f"no clips in {args.clips}")
    out_dir = Path(args.out_dir)
    rows = []
    failed = []
    for clip in clips:
        try:
            rows.append(_rebase(datamodel, skeleton_model, clip, out_dir / clip.name))
        except Exception as error:  # one bad clip must not stop the set
            failed.append({"clip": clip.name, "error": f"{type(error).__name__}: {error}"})
    report = {
        "skeleton": args.skeleton,
        "clips": len(clips),
        "rebased": len(rows),
        "failed": failed,
        "sample": rows[:3],
    }
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"REBASE {len(rows)} rebased, {len(failed)} failed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
