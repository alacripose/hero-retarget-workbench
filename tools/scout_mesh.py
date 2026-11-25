"""Build Scout's Deadlock mesh, validate it by re-parse, and compile it with the CSDK compiler.

  python tools/scout_mesh.py [--csdk C:/Users/ala/Downloads/Reduced_CSDK_13]

The receipt records measured facts only: counts parsed back out of the written DMX, the counts an
independent Valve tool (`dmxconvert`) gets when it converts that DMX to binary and back, and the bytes
the resource compiler wrote for the model and each material. Nothing is claimed from a build log alone.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge import meshbuild  # noqa: E402

OUT = ROOT / "artifacts" / "scout-mesh"
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-mesh.json"
DMXCONVERT = ROOT / "artifacts" / "dota-tools" / "game" / "bin" / "win64" / "dmxconvert.exe"
SKELETON = ROOT / "artifacts" / "scout-port-skel" / "models" / "heroes_wip" / "scout" / "dmx" / "mesh" / "scout_skel.dmx"
PORT = Path("F:/Documents")


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {}
    if path.is_file():
        try:
            merged = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            merged = {}
    merged.update(data)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


def _array_count(path: Path, name: str) -> int:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r'"' + re.escape(name) + r'" "[a-z0-9_]+_array"\s*\n\t*\[(.*?)\n\t*\]', text, re.S)
    return len(re.findall(r'"[^"]+"', match.group(1))) if match else -1


def roundtrip(dmx: Path) -> dict:
    """What `dmxconvert` reads out of the written DMX, after a binary round trip."""
    if not DMXCONVERT.is_file():
        return {"available": False}
    work = OUT / "check"
    work.mkdir(parents=True, exist_ok=True)
    binary, text = work / "scout_body_binary.dmx", work / "scout_body_roundtrip.dmx"
    for source, target, encoding in ((dmx, binary, "binary"), (binary, text, "keyvalues2")):
        result = subprocess.run(
            [str(DMXCONVERT), "-i", str(source), "-o", str(target), "-oe", encoding],
            capture_output=True,
            text=True,
        )
        if not target.is_file():
            return {"available": True, "ok": False, "output": (result.stdout + result.stderr)[-400:]}
    return {
        "available": True,
        "ok": True,
        "binary_bytes": binary.stat().st_size,
        "positions": _array_count(text, "position$0"),
        "corners": _array_count(text, "position$0Indices"),
        "blend_weights": _array_count(text, "blendweights$0"),
        "faces": len(re.findall(r'"-1"', text.read_text(encoding="utf-8", errors="replace"))),
    }


def compile_all(csdk: Path, produced: Path) -> dict:
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    content = csdk / "content"
    if not compiler.is_file():
        return {"available": False}
    model_root = content / meshbuild.MODEL_ROOT
    shutil.copytree(produced / meshbuild.MODEL_ROOT, model_root, dirs_exist_ok=True)
    (model_root / "dmx" / "mesh").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKELETON, model_root / "dmx" / "mesh" / "scout_skel.dmx")
    rows = []
    for source in [model_root / f"{meshbuild.MESH_NAME}.vmdl"] + sorted((model_root / "materials").glob("*.vmat")):
        result = subprocess.run(
            [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", str(source)],
            cwd=str(content),
            capture_output=True,
            text=True,
        )
        output = (result.stdout + result.stderr).strip().splitlines()
        ok = any("0 failed" in line for line in output[-6:])
        rows.append({"source": str(source.relative_to(content)), "ok": ok, "tail": output[-1] if output else ""})
    compiled_model = csdk / "game" / meshbuild.MODEL_ROOT / f"{meshbuild.MESH_NAME}.vmdl_c"
    materials = csdk / "game" / meshbuild.MODEL_ROOT / "materials"
    return {
        "available": True,
        "compiler": str(compiler),
        "documents": len(rows),
        "compiled": sum(1 for row in rows if row["ok"]),
        "failed": [row for row in rows if not row["ok"]],
        "model_compiled": str(compiled_model) if compiled_model.is_file() else "",
        "model_bytes": compiled_model.stat().st_size if compiled_model.is_file() else 0,
        "material_compiled": len(list(materials.glob("*.vmat_c"))),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csdk", default="C:/Users/ala/Downloads/Reduced_CSDK_13")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    out = Path(args.out)
    textures = sorted(path.name for path in (PORT / "scout").glob("*.vtf"))
    report = meshbuild.build(PORT / "scout.obj", SKELETON, out, textures, textures_dir=PORT / "scout")
    facts = meshbuild.inspect_mesh_dmx(Path(report["mesh_dmx"]))
    independence = roundtrip(Path(report["mesh_dmx"]))
    comp = compile_all(Path(args.csdk), out)
    vmts = sorted((out / meshbuild.MODEL_ROOT / "materials").glob("*.vmt"))
    vmats = sorted((out / meshbuild.MODEL_ROOT / "materials").glob("*.vmat"))
    receipt = {
        "schema": "dmf.scout-mesh/1",
        "generated": _stamp(),
        "source": {
            "obj": str(PORT / "scout.obj"),
            "skeleton": str(SKELETON),
            "textures": len(textures),
            "vertices": report["source_vertices"],
            "faces": report["source_faces"],
            "groups": report["source_groups"],
        },
        "mesh_dmx": report["mesh_dmx"],
        "mesh_dmx_bytes": report["mesh_dmx_bytes"],
        "model_vmdl": report["model_vmdl"],
        "render_mesh_reference": meshbuild.MESH_DMX_REF,
        "parsed": facts,
        "weights_normalized": facts["weight_min"] == 1.0 and facts["weight_max"] == 1.0,
        "vmt_files": len(vmts),
        "vmat_files": len(vmats),
        "png_files": len(list((out / meshbuild.MODEL_ROOT / "materials").glob("*.png"))),
        "independent_parse": independence,
        "compile": comp,
    }
    _write(RECEIPT, receipt)
    print(f"mesh DMX {report['mesh_dmx_bytes']} B: {facts['vertex_count']} verts, {facts['face_count']} faces, "
          f"{facts['joint_count']} joints, weights {facts['weight_min']}–{facts['weight_max']}")
    print(f"materials: {len(vmts)} .vmt, {len(vmats)} .vmat, {receipt['png_files']} .png")
    if independence.get("ok"):
        print(f"dmxconvert: {independence['positions']} positions, {independence['faces']} faces, "
              f"{independence['blend_weights']} weights, binary {independence['binary_bytes']} B")
    if comp.get("available"):
        print(f"compile: {comp['compiled']}/{comp['documents']} documents, model {comp['model_bytes']} B, "
              f"{comp['material_compiled']} .vmat_c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
