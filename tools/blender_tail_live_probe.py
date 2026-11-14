"""Scan every live hero skeleton for real tail chains.

  blender --background --factory-startup --python tools/blender_tail_live_probe.py -- \
      --cache artifacts/tail-skeletons --report artifacts/receipts/tail-live.json

The cache is produced by `forge.live.extract_tail_skeletons`. The probe is
name-level only; it does not import a model or need PulseSrcOps. It proves the
scanner reaches heroes that were never extracted by hand and rejects the two
false-positive families the owner found: face ``detail`` bones and Hornet's
hair braid / coat tails.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "blender" / "hero_retarget_workbench"
RESULT: dict = {"checks": {}, "failed": []}


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", default=str(REPO / "artifacts" / "tail-skeletons"))
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "tail-live.json"))
    return parser.parse_args(argv)


def check(name: str, ok: bool, observed) -> None:
    RESULT["checks"][name] = {"pass": bool(ok), "observed": observed}
    if not ok:
        RESULT["failed"].append(name)
    print(f"TAILLIVE {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)


def load_addon():
    spec = importlib.util.spec_from_file_location(
        "dmf_tail_live_probe",
        PACKAGE / "__init__.py",
        submodule_search_locations=[str(PACKAGE)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dmf_tail_live_probe"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def finish(code: int | None = None) -> None:
    if code is None:
        code = 0 if not RESULT["failed"] else 1
    RESULT["summary"] = (
        f"{sum(1 for item in RESULT['checks'].values() if item['pass'])}/{len(RESULT['checks'])} checks"
    )
    target = Path(RESULT["report"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(RESULT, indent=2), encoding="utf-8")
    print(f"TAILLIVE FINISH {RESULT['summary']} {target}", flush=True)
    bpy.ops.wm.quit_blender()


def main() -> int:
    args = arguments()
    cache = Path(args.cache).resolve()
    RESULT["report"] = str(Path(args.report).resolve())
    RESULT["cache"] = str(cache)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from forge import live

    files = live.tail_skeleton_files(cache)
    check("skeleton-cache", len(files) >= 30, {"files": len(files), "cache": str(cache)})
    if not files:
        finish(1)
        return 1

    load_addon()
    tailops = sys.modules["dmf_tail_live_probe.tailops"]
    settings = bpy.context.scene.dmf
    settings.project_root = str(REPO)
    settings.extraction_dir = ""
    settings.tail_scan_dir = ""
    count = tailops.discover(settings, live_files=files)
    labels = [option.label for option in settings.tail_options]
    text = "\n".join(labels).lower()
    check("tail-options", count > 0, {"count": count, "rows": len(labels)})
    check("live-source", all(option.source == "LIVE" for option in settings.tail_options), sorted({option.source for option in settings.tail_options}))
    for wanted in ("viper", "familiar", "tengu", "vindicta", "nano"):
        check(f"found-{wanted}", wanted in text, [label for label in labels if wanted in label.lower()][:4])
    for unwanted in ("hornet", "artist", "magician", "wraith", "mcginnis"):
        check(f"no-{unwanted}", unwanted not in text, [label for label in labels if unwanted in label.lower()][:4])
    for forbidden in ("detail", "braid", "coattail", "ponytail", "cloak_tail"):
        check(f"no-{forbidden}", forbidden not in text, [label for label in labels if forbidden in label.lower()][:4])
    check("no-duplicate-labels", len(labels) == len({label.lower() for label in labels}), len(labels))
    started = time.perf_counter()
    note = tailops.start_discover(settings)
    elapsed = time.perf_counter() - started
    check("start-discover-nonblocking", elapsed < 1.0, {"seconds": round(elapsed, 3), "note": note})
    finish()
    return 0


if __name__ == "__main__":
    main()
