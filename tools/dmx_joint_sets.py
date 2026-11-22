"""Compare a clip's joint list with its skeleton, and calibrate the refusal.

`tools/tail_release_gate.py` refuses `clip-joint-list-differs` when a clip does not
declare the same joints as the skeleton document, on the reasoning that the client
binds a clip by index. That reasoning came from a shipped failure, but the
threshold was never checked against a **pak that works**: if the game's own Shiv
clips also carry fewer joints than the Shiv skeleton, the rule as written refuses
shipped data and has to be narrowed rather than tightened.

This probe answers only that question. It reads joints through
`tools.tail_release_audit._joint_table`, which is the reader the gate uses, so the
comparison cannot drift from the check being calibrated.

    blender -b --python tools/dmx_joint_sets.py -- \
      --pair artifacts/.../dmx/animation/item_stand_idle.dmx=artifacts/.../shiv_tailbones.dmx \
      --report artifacts/receipts/joint-sets.json
"""

from __future__ import annotations
import os

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PULSE_DIR = Path(os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))
sys.path.insert(0, str(REPO / "tools"))
for _path in (PULSE_DIR, REPO / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", action="append", default=[], help="clip.dmx=skeleton.dmx")
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def compare(clip: Path, skeleton: Path) -> dict:
    from pulse_src_ops import datamodel  # noqa: WPS433  (Blender-only module)
    from tail_release_audit import _joint_table  # noqa: WPS433

    clip_rows = _joint_table(datamodel, str(clip))
    skeleton_rows = _joint_table(datamodel, str(skeleton))
    clip_order = clip_rows["__order__"]["order"]
    skeleton_order = skeleton_rows["__order__"]["order"]
    clip_set, skeleton_set = set(clip_order), set(skeleton_order)
    missing = [name for name in skeleton_order if name not in clip_set]
    extra = [name for name in clip_order if name not in skeleton_set]
    # An order subsequence: every clip joint appears in the skeleton, in the same
    # relative order. The client reads the clip's table against the skeleton's.
    positions = {name: index for index, name in enumerate(skeleton_order)}
    subsequence = not extra and all(
        positions[clip_order[i]] < positions[clip_order[i + 1]] for i in range(len(clip_order) - 1)
    )
    return {
        "clip": str(clip),
        "skeleton": str(skeleton),
        "clip_joints": len(clip_order),
        "skeleton_joints": len(skeleton_order),
        "missing_from_clip": missing,
        "missing_count": len(missing),
        "extra_in_clip": extra,
        "order_subsequence": subsequence,
        "equal_set": clip_set == skeleton_set,
    }


def main() -> int:
    options = _arguments()
    rows = []
    for pair in options.pair:
        clip, _, skeleton = pair.partition("=")
        rows.append(compare(Path(clip), Path(skeleton)))
        row = rows[-1]
        print(
            f"JOINTS {Path(clip).stem}: clip {row['clip_joints']} vs skeleton {row['skeleton_joints']} "
            f"missing {row['missing_count']} extra {len(row['extra_in_clip'])} "
            f"subsequence {row['order_subsequence']} equal {row['equal_set']}",
            flush=True,
        )
        if row["missing_from_clip"]:
            print(f"  missing: {row['missing_from_clip'][:12]}", flush=True)
    if options.report:
        target = Path(options.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
