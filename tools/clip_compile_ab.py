"""Compile one clip DMX through the real pipeline and decompile what comes back.

The merged DMX renders correctly on the authoring rig while the compiled clip
decompiled from the shipped pak renders rotated, so the question is whether that
rotation is introduced by this pipeline or by the merged file.  Compiling the
game's own decompiled DMX with the same skeleton, document and compiler answers
it: if the stock clip also comes back rotated, the pipeline does it.

  python tools/clip_compile_ab.py --csdk <csdk> --addon dmf_ab \
      --clip item_run_center --dmx <source.dmx> --out <decompiled dir> [--skeleton <vnmskel_c>]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
S2V = Path("<home>/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
LIVE_PAK = Path("D:/SteamLibrary/steamapps/common/Deadlock/game/citadel/pak01_dir.vpk")
SOURCE = "models/heroes_staging/shiv/dmx/animation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csdk", required=True)
    parser.add_argument("--addon", required=True)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--dmx", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--skeleton", default="")
    options = parser.parse_args()

    csdk = Path(options.csdk)
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    addon = csdk / "content" / "citadel_addons" / options.addon

    # Stage the stock document exactly as shiv_perclip_build does.
    scratch = REPO / "artifacts" / "ab" / options.clip
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    subprocess.run(
        [
            str(S2V),
            "-i",
            str(LIVE_PAK),
            "-f",
            f"models/heroes_staging/shiv/clips/{options.clip}.vnmclip_c",
            "-d",
            "-o",
            str(scratch),
        ],
        check=True,
        capture_output=True,
    )
    document = next(scratch.rglob("*.vnmclip"))
    staged = addon / "models" / "heroes_staging" / "shiv" / "clips" / f"{options.clip}.vnmclip"
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(document, staged)
    staged_dmx = addon / SOURCE / f"{options.clip}.dmx"
    staged_dmx.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(options.dmx, staged_dmx)
    if options.skeleton:
        skel = addon / "models" / "heroes_staging" / "shiv" / "shiv.vnmskel_c"
        skel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(options.skeleton, skel)

    resource = str(staged.relative_to(csdk / "content")).replace("\\", "/")
    proc = subprocess.run(
        [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", resource],
        cwd=str(csdk / "content"),
        capture_output=True,
        text=True,
    )
    print("COMPILE exit", proc.returncode)
    print((proc.stdout or "")[-600:])
    compiled = csdk / "game" / "citadel_addons" / options.addon / "models" / "heroes_staging" / "shiv" / "clips" / f"{options.clip}.vnmclip_c"
    if not compiled.is_file():
        raise SystemExit(f"no compiled output at {compiled}")

    out = REPO / options.out
    if out.exists():
        shutil.rmtree(out)
    subprocess.run([str(S2V), "-i", str(compiled), "-d", "-o", str(out)], check=True, capture_output=True)
    produced = sorted(out.rglob("*.dmx"))
    print("DECOMPILED", produced[0] if produced else "none")
    return 0 if produced else 1


if __name__ == "__main__":
    raise SystemExit(main())
