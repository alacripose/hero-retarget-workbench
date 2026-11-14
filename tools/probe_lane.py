"""Run the Blender probes as a gate lane, with explicit skips and receipts.

The ordinary gate is fast and headless. These probes are not: they need Blender,
PulseSrcOps and real S2V extractions. They are therefore a separate lane whose
result is reported as PASS, FAIL or SKIP instead of being mistaken for a passing
unit test. A probe that previously passed and now fails is a regression.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProbeSpec:
    name: str
    script: str
    receipt: str
    args: tuple[str, ...] = ()
    requires: tuple[str, ...] = ("blender", "extraction")
    gui: bool = False
    factory_startup: bool = False
    timeout: int = 300
    default: bool = True
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Check:
    name: str
    status: str  # pass, fail, skip, warn
    detail: str = ""


# Only probes that are useful on every development machine belong in the default
# lane. The clip/workbench probes stay listed so `--probes all` can run them, but
# they are not required for a normal gate.
PROBES: tuple[ProbeSpec, ...] = (
    ProbeSpec(
        "probe: cloth",
        "tools/blender_cloth_probe.py",
        "artifacts/receipts/probe-cloth.json",
        ("--extraction", "{extraction:shiv}", "--report", "artifacts/receipts/probe-cloth.json",
         "--log", "artifacts/receipts/probe-cloth.log"),
        requires=("blender", "extraction:shiv"),
    ),
    ProbeSpec(
        "probe: pages",
        "tools/blender_pages_gui_probe.py",
        "artifacts/receipts/probe-pages.json",
        ("--extraction", "{extraction:shiv}", "--report", "artifacts/receipts/probe-pages.json",
         "--log", "artifacts/receipts/probe-pages.log",
         "--screenshot", "artifacts/receipts/probe-pages.png"),
        requires=("blender", "extraction:shiv"),
        gui=True,
    ),
    ProbeSpec(
        "probe: tail-ui",
        "tools/blender_tail_ui_probe.py",
        "artifacts/receipts/probe-tail-ui.json",
        ("--extraction", "{extraction:familiar}", "--report", "artifacts/receipts/probe-tail-ui.json",
         "--screenshot", "artifacts/receipts/probe-tail-ui.png"),
        requires=("blender", "extraction:familiar"),
        gui=True,
    ),
    ProbeSpec(
        "probe: tail live roster",
        "tools/blender_tail_live_probe.py",
        "artifacts/receipts/tail-live.json",
        ("--cache", "artifacts/tail-skeletons", "--report", "artifacts/receipts/tail-live.json"),
        requires=("blender",),
        factory_startup=True,
    ),
    ProbeSpec(
        "probe: installed zip",
        "tools/blender_installed_zip_probe.py",
        "artifacts/receipts/probe-zip.json",
        ("--zip", "{zip}", "--report", "artifacts/receipts/probe-zip.json", "--expect", "sidebar"),
        requires=("blender", "zip"),
        factory_startup=True,
        env={"BLENDER_USER_SCRIPTS": "artifacts/probe-profile/scripts"},
    ),
    ProbeSpec(
        "probe: clip export",
        "tools/blender_clip_export_probe.py",
        "artifacts/receipts/probe-clip-export.json",
        ("--report", "artifacts/receipts/probe-clip-export.json"),
        default=False,
    ),
    ProbeSpec(
        "probe: workbench",
        "tools/blender_workbench_probe.py",
        "artifacts/receipts/probe-workbench.json",
        default=False,
    ),
    ProbeSpec(
        "probe: bone rules",
        "tools/blender_bone_rules_pose_probe.py",
        "artifacts/receipts/probe-bone-rules.json",
        default=False,
    ),
    ProbeSpec(
        "probe: custom tail",
        "tools/blender_custom_chain_tail_probe.py",
        "artifacts/receipts/probe-custom-tail.json",
        default=False,
    ),
)


def find_blender(explicit: str = "") -> str:
    for candidate in (explicit, os.environ.get("BLENDER", "")):
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    return shutil.which("blender") or ""


def find_zip() -> str:
    candidates = sorted(
        (ROOT / "dist").glob("hero_retarget_workbench-*.zip"),
        key=lambda path: path.stat().st_mtime,
    )
    return str(candidates[-1]) if candidates else ""


def extraction_root(explicit: str = "") -> str:
    candidate = explicit or os.environ.get("DMF_EXTRACTIONS", "")
    return str(Path(candidate)) if candidate and Path(candidate).is_dir() else ""


def resolve_arg(value: str, *, blender: str, extractions: str, zip_path: str) -> str:
    if "{extraction:" in value:
        for token in value.split():
            if token.startswith("{extraction:"):
                name = token[len("{extraction:") : -1]
                if not extractions:
                    return ""
                path = Path(extractions) / name
                if not path.is_dir():
                    return ""
                value = value.replace(token, str(path))
    return value.replace("{zip}", zip_path)


def missing_requirements(spec: ProbeSpec, *, blender: str, extractions: str, zip_path: str) -> list[str]:
    missing = []
    for requirement in spec.requires:
        if requirement == "blender" and not blender:
            missing.append("Blender (set --blender or BLENDER)")
        elif requirement == "zip" and not zip_path:
            missing.append("dist addon zip")
        elif requirement.startswith("extraction:"):
            name = requirement.split(":", 1)[1]
            if not extractions:
                missing.append("extraction root (set --extractions or DMF_EXTRACTIONS)")
            elif not (Path(extractions) / name).is_dir():
                missing.append(f"extraction {name}")
    return missing


def receipt_status(path: Path) -> Check:
    if not path.is_file():
        return Check(f"receipt {path.name}", "fail", f"missing {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Check(f"receipt {path.name}", "fail", f"unreadable: {error}")
    failed = data.get("failed") or []
    checks = data.get("checks") or {}
    bad = [name for name, item in checks.items() if isinstance(item, dict) and not item.get("pass")]
    if failed or bad:
        return Check(f"receipt {path.name}", "fail", f"failed checks: {', '.join(sorted(set(failed) | set(bad)))}")
    summary = str(data.get("summary", ""))
    if "skipped" in summary.lower():
        return Check(f"receipt {path.name}", "skip", summary)
    return Check(f"receipt {path.name}", "pass", summary or "receipt present")


def run_probe(
    spec: ProbeSpec,
    *,
    blender: str,
    extractions: str,
    zip_path: str,
    timeout: int | None = None,
) -> Check:
    script = ROOT / spec.script
    if not script.is_file():
        return Check(spec.name, "fail", f"missing {spec.script}")
    missing = missing_requirements(spec, blender=blender, extractions=extractions, zip_path=zip_path)
    if missing:
        return Check(spec.name, "skip", "missing " + ", ".join(missing))

    receipt = ROOT / spec.receipt
    try:
        receipt.unlink()
    except FileNotFoundError:
        pass
    args = [resolve_arg(value, blender=blender, extractions=extractions, zip_path=zip_path) for value in spec.args]
    if any(not value for value in args):
        return Check(spec.name, "skip", "could not resolve a probe path")
    command = [blender]
    if not spec.gui:
        command.append("--background")
    if spec.factory_startup:
        command.append("--factory-startup")
    command.extend(["--python-exit-code", "1", "--python", str(script), "--", *args])
    environment = os.environ.copy()
    for key, value in spec.env.items():
        path = Path(value)
        environment[key] = str(path if path.is_absolute() else ROOT / path)
    started = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout or spec.timeout,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return Check(spec.name, "fail", f"timed out after {timeout or spec.timeout}s")
    if not receipt.is_file():
        tail = (result.stdout + result.stderr).strip().splitlines()[-5:]
        return Check(
            spec.name,
            "fail",
            f"exit {result.returncode} and {spec.receipt} was not written: " + " | ".join(tail),
        )
    if receipt.stat().st_mtime < started:
        return Check(spec.name, "fail", f"stale receipt {spec.receipt}")
    status = receipt_status(receipt)
    if result.returncode != 0:
        # Blender can exit 1 from an unrelated add-on's unregister handler after
        # this probe already wrote a clean receipt.  The receipt is the probe's
        # evidence; a nonzero exit with a failing or stale receipt is still a
        # failure, but post-run teardown noise must not block the gate.
        if status.status == "pass":
            status.detail = f"{status.detail}; Blender teardown exit {result.returncode}"
            return status
        return Check(spec.name, "fail", f"exit {result.returncode}: {status.detail}")
    return status


def run_lane(
    *,
    blender: str = "",
    extractions: str = "",
    zip_path: str = "",
    mode: str = "default",
    timeout: int | None = None,
) -> list[Check]:
    if mode == "off":
        return [Check("probe lane", "skip", "disabled with --no-probes")]
    specs = [spec for spec in PROBES if mode == "all" or spec.default]
    blender = find_blender(blender)
    extractions = extraction_root(extractions)
    zip_path = zip_path or find_zip()
    if not blender:
        return [
            *(Check(spec.name, "skip", "Blender not configured") for spec in specs),
            Check("probe lane", "skip", "Blender not configured; no probe was run"),
        ]
    checks = [run_probe(spec, blender=blender, extractions=extractions, zip_path=zip_path, timeout=timeout) for spec in specs]
    passed = sum(1 for check in checks if check.status == "pass")
    skipped = sum(1 for check in checks if check.status == "skip")
    failed = [check for check in checks if check.status == "fail"]
    checks.append(
        Check(
            "probe lane",
            "fail" if failed else "pass",
            f"{passed} passed, {skipped} skipped, {len(failed)} failed",
        )
    )
    return checks
