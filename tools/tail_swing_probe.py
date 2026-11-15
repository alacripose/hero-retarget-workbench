"""Report how far the tail chain actually moves in each clip of a folder.

A tail that is present in every clip is not a tail that animates in every clip:
several authored clips carry the chain at its rest pose.  This measures the
swing per clip so a "tail extended" comparison is made on a clip where the tail
really moves, and so the number of clips with a static tail is a known quantity
rather than an assumption.

  blender -b --python tools/tail_swing_probe.py -- --folder <dir> --report <json>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TAIL_BONES = ("tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5")


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "tail-swing.json"))
    return parser.parse_args(argv)


def main() -> int:
    args = _arguments()
    spec = importlib.util.spec_from_file_location("dmx_diff", REPO / "tools" / "dmx_track_diff_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._enable_pulse()
    report: dict[str, object] = {"clips": [], "failed": []}
    target = Path(args.report)
    for path in sorted(Path(args.folder).glob("*.dmx")):
        try:
            dumped = module._dump(path)
        except Exception as error:
            report["failed"].append({"clip": path.name, "why": f"{type(error).__name__}: {error}"})
            print(f"TAIL-FAIL {path.name}: {error}", flush=True)
            continue
        swing = 0.0
        total = 0.0
        for key, series in dumped["tracks"].items():
            bone, prop, _axis = key.split("|")
            if bone not in TAIL_BONES or prop != "rotation_euler":
                continue
            values = [value for value in series.values() if value is not None]
            if not values:
                continue
            total = max(total, max(abs(value) for value in values))
            swing = max(swing, max(values) - min(values))
        report["clips"].append({"clip": path.stem, "tail_swing": round(swing, 4), "tail_abs_max": round(total, 4)})
        print(f"TAIL {path.stem} swing={swing:.3f}", flush=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    clips = report["clips"]
    moving = [row for row in clips if row["tail_swing"] > 0.05]
    print(f"TAIL done {len(clips)} clips, {len(moving)} with a moving tail, {len(report['failed'])} failed", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
