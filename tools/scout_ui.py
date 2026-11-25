"""Build Scout's own UI images into the panorama resources the hero entry names.

The CSDK 13 compiler has no direct image compiler: handing it a `.png` refuses with "Failed to find
compiler". It does compile a texture referenced from a one-texture `.vmat`, exactly as the port's 15
material textures are built, so that is how these are built too.

The hero entry names images the way the shipped heroes do — `file://{images}/heroes/scout_sm.psd` —
and the live paks resolve that name to `panorama/images/heroes/scout_sm_psd.vtex_c`. The compiled
texture is therefore copied to that exact panorama name, and the copy is decompiled with Source 2
Viewer before `tools/scout_install.py install` will ship it.

  python tools/scout_ui.py build
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CSDK = Path("C:/Users/ala/Downloads/Reduced_CSDK_13")
ADDON = "scout_port"
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
SOURCE_DIR = ROOT / "artifacts" / "scout-hero" / "ui"
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-ui.json"

# The entry's image names and the authored PNG each one is built from. The minimap, critical and gloat
# fields reuse these three names rather than shipping duplicate textures.
IMAGES = {
    "scout_sm": "sm",
    "scout_card": "card",
    "scout_vertical": "vertical",
}


class UIError(Exception):
    """A refusal that names its code, so the caller can report it instead of a traceback."""


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _texture_root(csdk: Path) -> Path:
    return csdk / "content" / "citadel_addons" / ADDON / "heroes_wip" / "scout" / "ui"


def _material_root(csdk: Path) -> Path:
    return csdk / "content" / "citadel_addons" / ADDON / "models" / "heroes_wip" / "scout" / "materials" / "ui"


def _compiled_root(csdk: Path) -> Path:
    return csdk / "game" / "citadel_addons" / ADDON / "heroes_wip" / "scout" / "ui"


def _panorama_root(csdk: Path) -> Path:
    return csdk / "game" / "citadel_addons" / ADDON / "panorama" / "images" / "heroes"


def build(csdk: Path = CSDK) -> dict:
    """Compile each authored image and place it under the panorama name the hero entry uses."""
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    if not compiler.is_file():
        raise UIError(f"ui-compiler-missing: {compiler}")
    missing = [name for name, stem in IMAGES.items() if not (SOURCE_DIR / f"{stem}.png").is_file()]
    if missing:
        raise UIError(f"ui-source-missing: {len(missing)} authored PNGs, first {missing[0]}.png")
    texture_root = _texture_root(csdk)
    material_root = _material_root(csdk)
    compiled_root = _compiled_root(csdk)
    panorama_root = _panorama_root(csdk)
    for directory in (texture_root, material_root, panorama_root):
        directory.mkdir(parents=True, exist_ok=True)
    verify_root = ROOT / "artifacts" / "scout-hero" / "ui-verify"
    shutil.rmtree(verify_root, ignore_errors=True)
    rows = []
    for name, stem in IMAGES.items():
        source = SOURCE_DIR / f"{stem}.png"
        png = texture_root / f"{name}.png"
        shutil.copy2(source, png)
        material = material_root / f"{name}_ui.vmat"
        material.write_text(
            "// Deadlock Model Forge - Scout UI image for the hero entry\n"
            "Layer0\n"
            "{\n"
            '\tshader "pbr.vfx"\n'
            "\n"
            f'\tTextureColor1 "heroes_wip/scout/ui/{name}.png"\n'
            "}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", str(material.resolve())],
            cwd=str(csdk / "content"),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=900,
        )
        output = (result.stdout or "").strip().splitlines()
        ok_line = next((line.strip() for line in output if line.strip().startswith(("OK:", "ERROR:"))), "")
        produced = sorted(compiled_root.glob(f"{name}_png_*.vtex_c"))
        if not ok_line.startswith("OK") or not produced:
            raise UIError(f"ui-compile-failed: {name}: {ok_line or 'no OK line'}")
        compiled = max(produced, key=lambda path: path.stat().st_mtime)
        panorama = panorama_root / f"{name}_psd.vtex_c"
        shutil.copy2(compiled, panorama)
        destination = verify_root / name
        subprocess.run(
            [str(S2V), "-i", str(panorama), "-d", "-o", str(destination)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=900,
        )
        dumped = sorted(destination.rglob("*")) if destination.is_dir() else []
        dumped = [path for path in dumped if path.is_file()]
        if not dumped:
            raise UIError(f"ui-readback-empty: {name}: Source 2 Viewer wrote nothing for {panorama.name}")
        rows.append(
            {
                "name": name,
                "source": str(source),
                "source_bytes": source.stat().st_size,
                "png_bytes": png.stat().st_size,
                "compiled": str(compiled),
                "compiled_bytes": compiled.stat().st_size,
                "panorama": f"panorama/images/heroes/{name}_psd.vtex_c",
                "panorama_path": str(panorama),
                "panorama_bytes": panorama.stat().st_size,
                "panorama_md5": _md5(panorama),
                "readback": str(dumped[0]),
                "readback_bytes": dumped[0].stat().st_size,
            }
        )
    report = {
        "schema": "dmf.scout-ui/1",
        "generated": _stamp(),
        "csdk": str(csdk),
        "compiler": str(compiler),
        "images": rows,
        "counts": {"images": len(rows), "bytes": sum(row["panorama_bytes"] for row in rows)},
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def inputs(csdk: Path = CSDK) -> dict[str, Path]:
    """The panorama files the addon install has to carry, keyed by their path inside the addon."""
    root = _panorama_root(csdk)
    return {f"panorama/images/heroes/{name}_psd.vtex_c": root / f"{name}_psd.vtex_c" for name in IMAGES}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Scout's UI images into panorama vtex resources.")
    parser.add_argument("--csdk", default=str(CSDK))
    parser.add_argument("command", choices=("build",))
    args = parser.parse_args(argv)
    try:
        report = build(Path(args.csdk))
    except UIError as error:
        print(f"REFUSED {error}")
        return 2
    print(json.dumps(report["counts"]))
    for row in report["images"]:
        print(
            f"  {row['name']}: {row['panorama_bytes']:>8} B -> {row['panorama']} "
            f"(compiled {row['compiled_bytes']} B, read back {row['readback_bytes']} B)"
        )
    print(f"receipt {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
