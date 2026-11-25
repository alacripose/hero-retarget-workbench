"""Build, compile and verify Scout's own Deadlock skeleton from the port's reference SMD.

The blocked step in `popit_apps/scout_port` is `skeleton-not-built`: the port ships a Source 1 rig and
the forge had no skeleton for it. This tool closes that step: `forge.portskel` writes the skeleton DMX
and the `.vnmskel` from `scout_anims/ref.smd`, `compile` runs the same CSDK13 compiler the clip work
uses, and `verify` reads the compiled resource back and compares its bone list with the SMD's.

  python tools/scout_skeleton.py build
  python tools/scout_skeleton.py compile --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
  python tools/scout_skeleton.py verify --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import portskel  # noqa: E402

MODEL = "models/heroes_wip/scout"
ADDON = "scout_port"
SOURCE_SMD = Path("F:/Documents/scout_anims/ref.smd")
OUT = ROOT / "artifacts" / "scout-port-skel"
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-skeleton.json"
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")


def _content(csdk: Path) -> Path:
    return csdk / "content" / "citadel_addons" / ADDON


def _game(csdk: Path) -> Path:
    return csdk / "game" / "citadel_addons" / ADDON


def cmd_build(args) -> int:
    joints = portskel.read_reference(Path(args.smd))
    tree = Path(args.out) / MODEL
    dmx = portskel.write_skeleton_dmx(joints, tree / "dmx" / "mesh" / "scout_skel.dmx")
    names = [joint.name for joint in joints]
    vnmskel = portskel.write_vnmskel(
        tree / "scout.vnmskel",
        source=f"{MODEL}/dmx/mesh/scout_skel.dmx",
        root=names[0],
        bones=names,
    )
    receipt = {
        "smd": args.smd,
        "joints": len(joints),
        "root": names[0],
        "dmx": str(dmx),
        "dmx_bytes": dmx.stat().st_size,
        "vnmskel": str(vnmskel),
        "vnmskel_bytes": vnmskel.stat().st_size,
        "bones": names,
    }
    _write(receipt)
    print(f"BUILD {len(joints)} joints, root {names[0]}, {dmx.stat().st_size} B dmx, {vnmskel.stat().st_size} B vnmskel")
    return 0


def _write(receipt: dict) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(RECEIPT.read_text(encoding="utf-8")) if RECEIPT.is_file() else {}
    existing.update(receipt)
    RECEIPT.write_text(json.dumps(existing, indent=1), encoding="utf-8")


def cmd_compile(args) -> int:
    csdk = Path(args.csdk)
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    if not compiler.is_file():
        raise SystemExit(f"compiler-missing: {compiler}")
    source = Path(args.out) / MODEL
    content = _content(csdk) / MODEL
    content.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, content, dirs_exist_ok=True)
    document = content / "scout.vnmskel"
    result = subprocess.run(
        [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", str(document.resolve())],
        cwd=str(csdk / "content"),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=600,
    )
    tail = (result.stdout or "").strip().splitlines()
    ok_line = next((line.strip() for line in tail if line.strip().startswith(("OK:", "ERROR:"))), "")
    compiled = _game(csdk) / MODEL / "scout.vnmskel_c"
    _write(
        {
            "compile": {
                "document": str(document),
                "returncode": result.returncode,
                "ok_line": ok_line,
                "compiled": str(compiled) if compiled.is_file() else "",
                "compiled_bytes": compiled.stat().st_size if compiled.is_file() else 0,
                "stdout_tail": tail[-6:],
            }
        }
    )
    print(f"COMPILE {ok_line} -> {compiled} {compiled.stat().st_size if compiled.is_file() else 0} B")
    if not compiled.is_file():
        raise SystemExit("vnmskel-not-compiled")
    return 0


def cmd_verify(args) -> int:
    csdk = Path(args.csdk)
    compiled = _game(csdk) / MODEL / "scout.vnmskel_c"
    if not compiled.is_file():
        raise SystemExit(f"compiled-missing: {compiled}")
    destination = Path(args.out) / "verify"
    shutil.rmtree(destination, ignore_errors=True)
    result = subprocess.run(
        [str(S2V), "-i", str(compiled), "-d", "-o", str(destination)],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=300,
    )
    decompiled = destination / "scout.vnmskel"
    if not decompiled.is_file():
        found = sorted(destination.rglob("scout.vnmskel"))
        decompiled = found[0] if found else decompiled
    if not decompiled.is_file():
        raise SystemExit(f"decompile-empty: {(result.stdout or result.stderr)[-200:]}")
    text = decompiled.read_text(encoding="utf-8", errors="replace")
    joints = portskel.read_reference(SOURCE_SMD)
    names = [joint.name for joint in joints]
    listed = [line.strip().strip('",') for line in text.splitlines() if line.strip().startswith('"')]
    missing = [name for name in names if f'"{name}"' not in text]
    source = next((line for line in text.splitlines() if "m_sourceFilename" in line), "")
    receipt = {
        "verify": {
            "compiled": str(compiled),
            "compiled_bytes": compiled.stat().st_size,
            "decompiled": str(decompiled),
            "decompiled_bytes": decompiled.stat().st_size,
            "source_field": source.strip(),
            "bones_expected": len(names),
            "bones_missing": missing,
            "strings_listed": len(listed),
            "skeleton_dmx_dumped": str(destination / "dmx" / "mesh" / "scout_skel.dmx"),
            "result": "PASS" if not missing else "FAIL",
        }
    }
    _write(receipt)
    print(f"VERIFY {len(names) - len(missing)}/{len(names)} bones present, {decompiled.stat().st_size} B decompiled")
    print(f"  {source.strip()}")
    if missing:
        print(f"  missing {missing[:8]}")
        raise SystemExit("skeleton-bones-missing")
    print("RESULT: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="write the skeleton DMX and the .vnmskel from the port's SMD")
    build.add_argument("--smd", default=str(SOURCE_SMD))
    build.set_defaults(func=cmd_build)
    compile_parser = sub.add_parser("compile", help="compile the .vnmskel with CSDK13")
    compile_parser.add_argument("--csdk", required=True)
    compile_parser.set_defaults(func=cmd_compile)
    verify = sub.add_parser("verify", help="decompile the compiled skeleton and compare its bones")
    verify.add_argument("--csdk", required=True)
    verify.set_defaults(func=cmd_verify)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
