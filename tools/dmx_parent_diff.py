"""List every joint whose parent differs between two skeleton documents.

A joint's parent decides the frame its rotation is applied in. `weaponHand_L`
parented to `hand_L` instead of `arm_L_IKTARGET` reads the same numbers through a
different frame: in game the hands and everything hanging off them point the wrong
way while the mesh stays intact. Counting rest deltas does not show this; the
parent does.

  blender -b --python tools/dmx_parent_diff.py -- --a <stock.dmx> --b <grafted.dmx> --report <json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
for candidate in (PULSE_DIR, REPO / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)
    from pulse_src_ops import datamodel
    from tail_release_audit import _joint_table

    a = _joint_table(datamodel, args.a)
    b = _joint_table(datamodel, args.b)
    a_order, b_order = a["__order__"]["order"], b["__order__"]["order"]
    shared = [name for name in b_order if name in set(a_order)]
    diffs = [
        {"joint": name, "a_parent": a[name]["parent"], "b_parent": b[name]["parent"]}
        for name in shared
        if a[name]["parent"] != b[name]["parent"]
    ]
    print(f"PARENTS shared={len(shared)} differing={len(diffs)}", flush=True)
    for row in diffs[:20]:
        print(f"  {row['joint']:24s} {row['a_parent']} -> {row['b_parent']}", flush=True)
    tail = [name for name in b_order if name.startswith("tail_")]
    print("TAIL " + ", ".join(f"{name}<-{(b[name]['parent'])}" for name in tail), flush=True)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"a": args.a, "b": args.b, "shared": len(shared), "differing": diffs,
                                      "tail_chain": [(n, b[n]["parent"]) for n in tail]}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
