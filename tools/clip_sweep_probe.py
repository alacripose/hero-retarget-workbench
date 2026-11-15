"""Compare many clip pairs in one Blender session.

`tools/dmx_track_diff_probe.py` starts Blender per pair, which costs about ten
seconds of startup for two seconds of work; a full-set check is 181 pairs.  This
runs every pair inside one session, printing and integrating a result per clip so
a crash keeps what it already measured.

  blender -b --python tools/clip_sweep_probe.py -- --pairs <pairs.json> --report <json>

`pairs.json` is a list of ``{"clip": name, "a": path, "b": path}``.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
IGNORED_BONES = {"pelvis"}


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "clip-sweep.json"))
    parser.add_argument("--threshold", type=float, default=0.05)
    return parser.parse_args(argv)


def _probe():
    spec = importlib.util.spec_from_file_location("dmx_diff", REPO / "tools" / "dmx_track_diff_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compare(module, a: dict, b: dict, tolerance: float, presence: set[str]) -> dict[str, dict[str, float]]:
    """Per bone, the worst position and the worst rotation delta.

    They are kept apart because they mean different things: an IK goal's position
    is what the solver chases, while a rotation written as a different Euler
    triple can be the very same orientation.
    """
    keys = sorted(set(a["tracks"]) | set(b["tracks"]))
    worst: dict[str, dict[str, float]] = {}
    for key in keys:
        ta = a["tracks"].get(key)
        tb = b["tracks"].get(key)
        bone, prop, _axis = key.split("|")
        slot = "location" if prop == "location" else "rotation"
        row = worst.setdefault(bone, {"location": 0.0, "rotation": 0.0})
        if ta is None or tb is None:
            # A channel on one side only is a rig difference (our skeleton carries
            # leaf bones and scale channels the stock clips omit), not a pose
            # change, so it is counted separately instead of as a delta.
            presence.add(bone)
            continue
        for frame, value in ta.items():
            other = tb.get(frame)
            if other is None:
                continue
            delta = abs(value - other)
            # A rotation written a whole turn higher is the same orientation; the
            # compilers emit one or the other depending on the Euler wrap.
            if slot == "rotation":
                turns = round(delta / (2.0 * 3.141592653589793))
                if turns and abs(delta - turns * 2.0 * 3.141592653589793) <= 1e-3:
                    continue
            if delta > tolerance and delta > row[slot]:
                row[slot] = delta
    return worst


def main() -> int:
    args = _arguments()
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    module = _probe()
    module._enable_pulse()
    report: dict[str, object] = {"clips": [], "failed": []}
    target = Path(args.report)
    for pair in pairs:
        clip = pair["clip"]
        try:
            a = module._dump(Path(pair["a"]))
            b = module._dump(Path(pair["b"]))
        except Exception as error:  # one unreadable clip must not end the sweep
            report["failed"].append({"clip": clip, "why": f"{type(error).__name__}: {error}"})
            print(f"SWEEP-FAIL {clip}: {error}", flush=True)
            continue
        presence: set[str] = set()
        worst = _compare(module, a, b, 1e-5, presence)
        body = {bone: row for bone, row in worst.items() if bone not in IGNORED_BONES and not bone.startswith("tail_")}
        loc = {bone: round(row["location"], 3) for bone, row in body.items() if row["location"] > 1e-5}
        rot = {bone: round(row["rotation"], 3) for bone, row in body.items() if row["rotation"] > 1e-5}
        over = {bone: value for bone, value in loc.items() if value > args.threshold}
        tails = {bone: round(row["rotation"], 3) for bone, row in worst.items() if bone.startswith("tail_")}
        report["clips"].append(
            {
                "clip": clip,
                "positions_over_threshold": over,
                "worst_position": max(loc.values()) if loc else 0.0,
                "worst_rotation": max(rot.values()) if rot else 0.0,
                "rotation_outliers": {bone: value for bone, value in rot.items() if value > args.threshold},
                "tail_rotation_max": max(tails.values()) if tails else 0.0,
                "presence_only": sorted(presence),
            }
        )
        print(
            f"SWEEP {clip} pos_max={max(loc.values()) if loc else 0.0:.3f} rot_max={max(rot.values()) if rot else 0.0:.3f} over={len(over)}",
            flush=True,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    clips = report["clips"]
    bad = [row for row in clips if row["positions_over_threshold"]]
    print(f"SWEEP done {len(clips)} clips, {len(bad)} with a body bone over {args.threshold}, {len(report['failed'])} failed", flush=True)
    return 0 if not bad and not report["failed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
