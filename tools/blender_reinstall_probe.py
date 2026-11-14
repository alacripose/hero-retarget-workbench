"""Install the built zip twice into one enabled profile and register both times.

The owner's report: installing the CI zip over an enabled copy raised
``register_class(...): already registered as a subclass 'DMF_BoneEntry'``.
Blender re-enables the module in the same process, so the second register() has
to release the classes the first one left behind.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from pathlib import Path

import bpy

MODULE = "hero_retarget_workbench"
CHECKS: dict[str, dict[str, object]] = {}


def _check(name: str, ok: bool, observed: object) -> None:
    CHECKS[name] = {"pass": bool(ok), "observed": observed}
    print(f"REINSTALL {'PASS' if ok else 'FAIL'} {name}: {observed}", flush=True)


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


def main() -> int:
    args = _arguments()
    report: dict[str, object] = {"zip": args.zip, "checks": CHECKS, "errors": []}

    def install_and_enable(round_name: str, *, allow_locked: bool = False) -> bool:
        try:
            installed = bpy.ops.preferences.addon_install(filepath=str(Path(args.zip).resolve()))
            enabled = bpy.ops.preferences.addon_enable(module=MODULE)
            addon = importlib.import_module(MODULE)
            # On Windows an install over an enabled copy cannot overwrite the
            # loaded blake3 .pyd, so Blender answers CANCELLED and leaves the
            # files alone. That is a file-lock limit, not a registration bug:
            # what must hold is that the module still enables and registers.
            installed_ok = installed == {"FINISHED"}
            _check(
                round_name,
                installed_ok and enabled == {"FINISHED"},
                {
                    "install": str(installed),
                    "enable": str(enabled),
                    "surface": getattr(addon, "SURFACE", ""),
                    "file": getattr(addon, "__file__", ""),
                },
            )
            return enabled == {"FINISHED"}
        except Exception as error:  # recorded
            report["errors"].append(traceback.format_exc())
            _check(
                round_name,
                False,
                f"{type(error).__name__}: {error}",
            )
            return False

    install_and_enable("first-install")
    # The state the owner hit: the module is enabled, then the zip is installed
    # again without restarting Blender.
    install_and_enable("second-install", allow_locked=True)
    panels = sorted(name for name in dir(bpy.types) if name.startswith("DMF_PT_"))
    _check("panels-after-reinstall", len(panels) >= 20, len(panels))
    _check("no-register-errors", not report["errors"], len(report["errors"]))

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"REINSTALL {'PASS' if all(c['pass'] for c in CHECKS.values()) else 'FAIL'} "
        f"{sum(1 for c in CHECKS.values() if c['pass'])}/{len(CHECKS)} checks",
        flush=True,
    )
    return 0 if all(c["pass"] for c in CHECKS.values()) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
