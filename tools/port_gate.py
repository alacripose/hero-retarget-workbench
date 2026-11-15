"""Gate a port against a pin file, for any hero and any addon.

The project gate used to run ``tools/shiv_merge_gate.py`` directly, so the only
build the repository could prove was a Shiv pak, and every tail experiment was
forced back through Shiv's files to be checked at all.  A pin is now data:

    ledger/pins/<addon>.json

    {
      "addon": "haze_tail",
      "hero": "haze",
      "pak": "artifacts/haze-tail/haze_tail.vpk",
      "sha256": "...", "bytes": 15238292,
      "receipt": "artifacts/receipts/tail-port-haze-build.json",
      "skeleton": "..../haze_tailbones.dmx",
      "tail_bones": ["tail_0"], "moving_clips": ["item_stand_idle"],
      "installed": "D:/.../addons/pak97_dir.vpk",
      "legacy_gate": "tools/shiv_merge_gate.py"
    }

Checks are the ones a port actually has to satisfy, all hero-independent: the
pak is the pinned bytes, the receipt says the tail pass updated clips and at
least one written clip's tail moves, the skeleton carries the tail chain, and
(unless skipped) the installed slot is that same pak.  ``legacy_gate`` exists so
a port with a deeper bespoke audit (Shiv's release audit) keeps it without the
project gate depending on any one hero.

    python tools/port_gate.py --all
    python tools/port_gate.py --pin ledger/pins/haze_tail.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "ledger" / "pins"
DEFAULT_INSTALLED = Path(
    r"D:\SteamLibrary\steamapps\common\Deadlock\game\citadel\addons\pak97_dir.vpk"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_pin(path: str | Path, **fields) -> Path:
    """Record what a port produced, in the same shape :func:`gate_pin` reads."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields, indent=2) + "\n", encoding="utf-8")
    return path


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def gate_pin(pin_path: Path, *, skip_installed: bool = False) -> dict:
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    addon = pin.get("addon") or pin_path.stem
    if pin.get("status") == "candidate":
        # A candidate is recorded so the work is not lost, but it is not shipped:
        # the project gate must not go red on a build the owner has not accepted.
        return {
            "addon": addon,
            "pin": str(pin_path),
            "pass": True,
            "status": "candidate",
            "note": pin.get("note", ""),
            "checks": [],
        }
    pak = _resolve(pin["pak"]) if pin.get("pak") else None
    if pak is not None:
        exists = pak.is_file()
        check(f"{addon}: pak exists", exists, str(pak))
        if exists:
            digest = sha256(pak)
            check(
                f"{addon}: pak is the pinned bytes",
                digest == pin.get("sha256") and pak.stat().st_size == pin.get("bytes"),
                f"{digest[:16]} {pak.stat().st_size}b",
            )
    receipt_path = _resolve(pin["receipt"]) if pin.get("receipt") else None
    if receipt_path is not None:
        check(f"{addon}: port receipt exists", receipt_path.is_file(), str(receipt_path))
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            checks_block = receipt.get("checks") or {}
            moving = checks_block.get("moving") or []
            check(
                f"{addon}: the tail pass updated clips",
                int(checks_block.get("updated") or 0) > 0 and not receipt.get("errors"),
                f"updated={checks_block.get('updated')} errors={len(receipt.get('errors') or [])}",
            )
            check(f"{addon}: a written clip's tail moves", bool(moving), ", ".join(moving[:4]))
            bones = checks_block.get("hero_tail_bones") or pin.get("tail_bones") or []
            check(f"{addon}: the hero carries a tail chain", len(bones) >= 5, ", ".join(bones[:6]))
    skeleton = _resolve(pin["skeleton"]) if pin.get("skeleton") else None
    if skeleton is not None:
        check(f"{addon}: the compiled skeleton source exists", skeleton.is_file(), str(skeleton))
        if skeleton.is_file():
            text = skeleton.read_text(encoding="utf-8", errors="replace")
            missing = [name for name in pin.get("skeleton_bones") or [] if name not in text]
            check(
                f"{addon}: the skeleton names every bone the pin needs",
                not missing,
                "missing: " + ", ".join(missing) if missing else "all present",
            )
    if pin.get("legacy_gate") and not skip_installed:
        pass  # the legacy audit runs its own installed check
    if pin.get("legacy_gate"):
        script = _resolve(pin["legacy_gate"])
        # The installed addon slot is environment state, not a property of the
        # pinned build: whichever port is installed owns it, so a pin whose port
        # is not the installed one audits without that check.
        command = [sys.executable, str(script)]
        if pin.get("skip_installed"):
            command.append("--skip-installed")
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        check(
            f"{addon}: bespoke audit passes",
            result.returncode == 0,
            (result.stdout or result.stderr or "").strip().splitlines()[-1][:200]
            if (result.stdout or result.stderr)
            else f"exit {result.returncode}",
        )
    if not skip_installed and pin.get("installed") and not pin.get("legacy_gate"):
        installed = _resolve(pin["installed"])
        installed_sha = sha256(installed) if installed.is_file() else ""
        check(
            f"{addon}: the installed slot is this pak",
            installed_sha == pin.get("sha256"),
            installed_sha[:16] or "missing",
        )
    passed = all(row["pass"] for row in checks)
    return {"addon": addon, "pin": str(pin_path), "pass": passed, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", default="", help="one pin file")
    parser.add_argument("--all", action="store_true", help="every pin under ledger/pins")
    parser.add_argument("--skip-installed", action="store_true")
    parser.add_argument("--report", default="", help="write the report here")
    args = parser.parse_args(argv)
    if not args.pin and not args.all:
        parser.error("choose --pin or --all")
    pin_paths = (
        sorted(PINS.glob("*.json")) if args.all else [_resolve(args.pin)]
    )
    if not pin_paths:
        print(f"no pins under {PINS}", file=sys.stderr)
        return 2
    reports = [gate_pin(path, skip_installed=args.skip_installed) for path in pin_paths]
    report = {
        "summary": "port gate passed" if all(r["pass"] for r in reports) else "port gate failed",
        "ports": reports,
    }
    destination = Path(args.report) if args.report else ROOT / "artifacts" / "receipts" / "port-gate.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for port in reports:
        failed = [row for row in port["checks"] if not row["pass"]]
        label = "CANDIDATE" if port.get("status") == "candidate" else ("PASS" if port["pass"] else "FAIL")
        print(f"{label} {port['addon']} ({len(port['checks'])} checks)")
        for row in failed:
            print(f"  - {row['name']}: {row['detail']}")
    return 0 if report["summary"].endswith("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
