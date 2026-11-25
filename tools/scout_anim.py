"""Verify Scout's four clips as Deadlock animation documents, and compile the port end to end.

  python tools/scout_anim.py [--csdk C:/Users/ala/Downloads/Reduced_CSDK_13]

The evidence path mirrors the mesh one. A shipped Dota tool-branch animation document is converted to
keyvalues2 with `dmxconvert` to establish the shape (two channels per joint: `_p` position and `_o`
orientation). Then each compiled `vnmclip_c` is decompiled by Source2Viewer, its animation DMX is
converted by `dmxconvert`, and the result is counted here: channels, joint names against the 78-joint
skeleton, frame count and duration. The graph is decompiled the same way for its clip references.

The compile stage runs the port's own graph compiler (skeleton, clips, graph), then the mesh model and
all 15 materials, and records each document's result.
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

OUT = ROOT / "artifacts" / "scout-anim"
PARSED = OUT / "parsed"
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-anim.json"
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
DMXCONVERT = ROOT / "artifacts" / "dota-tools" / "game" / "bin" / "win64" / "dmxconvert.exe"
DOTA_REFERENCE = (
    ROOT / "artifacts" / "dota-tools" / "content" / "dota_addons" / "animgraph"
    / "models" / "biped_standard" / "dmx" / "animation" / "idle.dmx"
)
MODEL = "models/heroes_wip/scout"
ADDON = "scout_port"
SKELETON = ROOT / "artifacts" / "scout-port-skel" / MODEL / "dmx" / "mesh" / "scout_skel.dmx"
MESH_OUT = ROOT / "artifacts" / "scout-mesh" / MODEL
# graph clip name -> (the port sequence baked into it, its frame count)
CLIPS = {
    "Scout_Attack": ("AttackStand_PRIMARY", 21),
    "Scout_Reload": ("PRIMARY_reload_loop", 20),
    "Scout_AimIdle": ("PRIMARY_aimmatrix_idle", 2),
    "Scout_AimRun": ("PRIMARY_aimmatrix_run", 2),
}


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


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def _to_kv2(source: Path, target: Path) -> bool:
    if not DMXCONVERT.is_file() or not source.is_file():
        return False
    _run([str(DMXCONVERT), "-i", str(source), "-o", str(target), "-oe", "keyvalues2"])
    return target.is_file()


def _channel_names(text: str) -> list[str]:
    return re.findall(
        r'"DmeChannel"\s*\{\s*"id" "elementid" "[^"]+"\s*"name" "string" "([^"]+)"', text
    )


def _joint_names(text: str) -> list[str]:
    return re.findall(
        r'"DmeJoint"\s*\{\s*"id" "elementid" "[^"]+"\s*"name" "string" "([^"]+)"', text
    )


def _duration(text: str) -> float:
    frame = re.search(r'"DmeTimeFrame"\s*\{(.*?)\n\t*\}', text, re.S)
    if not frame:
        return 0.0
    found = re.search(r'"duration" "time" "([^"]+)"', frame.group(1))
    return float(found.group(1)) if found else 0.0


def _frames(text: str) -> int:
    """Sample count of the first orientation channel: the clip's own frame count."""
    for match in re.finditer(
        r'"DmeChannel"\s*\{\s*"id" "elementid" "[^"]+"\s*"name" "string" "([^"]+)"', text
    ):
        if not match.group(1).endswith("_o"):
            continue
        block = text[match.start():match.start() + 20000]
        times = re.search(r'"times" "time_array"\s*\n\t*\[(.*?)\n\t*\]', block, re.S)
        if times:
            return len(re.findall(r'"[^"]+"', times.group(1)))
    return 0


def _suffixes(names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in names:
        if name.endswith("_p"):
            counts["_p"] = counts.get("_p", 0) + 1
        elif name.endswith("_o"):
            counts["_o"] = counts.get("_o", 0) + 1
    return counts


def reference_shape() -> dict:
    """The shape a shipped Dota tool-branch animation document has, read through dmxconvert."""
    target = OUT / "reference" / "dota_idle.kv2.dmx"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not _to_kv2(DOTA_REFERENCE, target):
        return {"available": False, "path": str(DOTA_REFERENCE)}
    text = target.read_text(encoding="utf-8", errors="replace")
    names = _channel_names(text)
    return {
        "available": True,
        "path": str(DOTA_REFERENCE),
        "bytes": DOTA_REFERENCE.stat().st_size,
        "kv2_bytes": target.stat().st_size,
        "channels": len(names),
        "joints": len(set(_joint_names(text))),
        "suffixes": _suffixes(names),
        "classes": sorted(set(re.findall(r'"(Dme[A-Za-z]+)"', text)))[:8],
    }


def graph_facts(csdk: Path) -> dict:
    """The compiled graph, decompiled and counted: its clip references and named nodes."""
    compiled = csdk / "game" / "citadel_addons" / ADDON / MODEL / "scout.vnmgraph_c"
    work = OUT / "graph"
    work.mkdir(parents=True, exist_ok=True)
    if not compiled.is_file():
        return {"available": False, "reason": f"compiled-graph-missing: {compiled}"}
    _run([str(S2V), "-i", str(compiled), "-d", "-o", str(work)])
    dumps = sorted(work.glob("*.vnmgraph"))
    if not dumps:
        return {"available": False, "reason": "graph-decompile-empty"}
    text = dumps[0].read_text(encoding="utf-8", errors="replace")
    clips = re.findall(r'm_clip = "([^"]+)"', text)
    return {
        "available": True,
        "compiled": str(compiled),
        "compiled_bytes": compiled.stat().st_size,
        "dump": str(dumps[0]),
        "dump_bytes": dumps[0].stat().st_size,
        "nodes": len(re.findall(r'_class = "CNmGraphDoc[A-Za-z]+Node"', text)),
        "clip_references": clips,
        "states": sorted(set(re.findall(r'm_name = "(state_[A-Za-z0-9_]+)"', text))),
        "aim_states": sorted(set(re.findall(r'm_name = "(aim_state_[A-Za-z0-9_]+)"', text))),
        "skeletons": sorted(set(re.findall(r'm_skeleton = "([^"]+)"', text))),
        "frank_references": text.lower().count("frank"),
    }


def parse_clip(graph_name: str, csdk: Path) -> dict:
    """Decompile one compiled clip, convert its DMX, and count what is in it."""
    source_name, expected_frames = CLIPS[graph_name]
    compiled = (
        csdk / "game" / "citadel_addons" / ADDON / MODEL / "clips" / f"{graph_name.lower()}.vnmclip_c"
    )
    work = PARSED / graph_name
    work.mkdir(parents=True, exist_ok=True)
    if not compiled.is_file():
        return {"name": graph_name, "ok": False, "reason": f"compiled-clip-missing: {compiled}"}
    dump = _run([str(S2V), "-i", str(compiled), "-d", "-o", str(work)])
    documents = sorted(work.glob("*.vnmclip"))
    # The compiled document names the animation DMX it was built from; Source2Viewer resolves that
    # path against the addon, so a missing DMX beside the compiled clip means no dump of the data.
    if documents:
        text = documents[0].read_text(encoding="utf-8", errors="replace")
        named = re.search(r'm_sourceFilename = "([^"]+)"', text)
        if named:
            relative = named.group(1)
            addon_root = csdk / "game" / "citadel_addons" / ADDON
            if not (addon_root / relative).is_file():
                source = ROOT / "artifacts" / "scout-own-clips" / "dmx" / f"{source_name}.dmx"
                if source.is_file():
                    (addon_root / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, addon_root / relative)
                    dump = _run([str(S2V), "-i", str(compiled), "-d", "-o", str(work)])
                    documents = sorted(work.glob("*.vnmclip"))
    # Source2Viewer writes the referenced DMX one level above the output folder, `dmx/<name>.dmx`,
    # so the dump beside the document is not where it lands.
    document_text = documents[0].read_text(encoding="utf-8", errors="replace") if documents else ""
    reference = re.search(r'm_sourceFilename = "([^"]+)"', document_text) if documents else None
    basename = Path(reference.group(1)).name if reference else ""
    dmx_files = [path for path in sorted((PARSED / "dmx").glob("*.dmx")) if not basename or path.name == basename]
    if not documents or not dmx_files:
        return {
            "name": graph_name,
            "ok": False,
            "reason": f"decompile-empty: {(dump.stdout or dump.stderr)[-200:]}",
        }
    dmx = dmx_files[0]
    kv2 = work / f"{graph_name}.compiled.kv2.dmx"
    if not _to_kv2(dmx, kv2):
        return {"name": graph_name, "ok": False, "reason": f"dmxconvert-failed: {dmx}"}
    text = kv2.read_text(encoding="utf-8", errors="replace")
    names = _channel_names(text)
    joints = _joint_names(text)
    source_copy = OUT / "clips" / f"{graph_name}.vnmclip"
    source_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(documents[0], source_copy)
    skeleton_names = [joint.name for joint in meshbuild.read_skeleton(SKELETON)]
    track_joints = sorted({name[:-2] for name in names if name.endswith(("_p", "_o"))})
    frames = _frames(text)
    source_filename = re.search(r'm_sourceFilename = "([^"]+)"', document_text)
    skeleton_reference = re.search(r'm_animationSkeletonName = "([^"]+)"', document_text)
    row = {
        "name": graph_name,
        "source_sequence": source_name,
        "compiled": str(compiled),
        "compiled_bytes": compiled.stat().st_size,
        "document": str(source_copy),
        "document_bytes": source_copy.stat().st_size,
        "source_dmx": str(dmx),
        "source_dmx_bytes": dmx.stat().st_size,
        "kv2": str(kv2),
        "channels": len(names),
        "suffixes": _suffixes(names),
        "joints": len(set(joints)),
        "track_joints": len(track_joints),
        "skeleton_joints": len(skeleton_names),
        "skeleton_matches": track_joints == sorted(skeleton_names),
        "frames": frames,
        "expected_frames": expected_frames,
        "duration": _duration(text),
        "source_filename": source_filename.group(1) if source_filename else "",
        "animation_skeleton": skeleton_reference.group(1) if skeleton_reference else "",
    }
    row["ok"] = (
        row["channels"] == 2 * row["skeleton_joints"]
        and row["track_joints"] == row["skeleton_joints"]
        and row["skeleton_matches"]
        and row["frames"] == expected_frames
        and row["duration"] > 0
    )
    _write(PARSED / f"{graph_name}.json", row)
    return row


def compile_all(csdk: Path) -> dict:
    """The port's own graph compile for skeleton/clips/graph, then the mesh model and materials."""
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    content = csdk / "content"
    if not compiler.is_file():
        return {"available": False}
    graph_run = _run(
        [sys.executable, str(ROOT / "tools" / "scout_graph.py"), "compile", "--csdk", str(csdk)],
        cwd=ROOT,
    )
    graph_receipt = ROOT / "artifacts" / "receipts" / "scout-graph.json"
    graph_rows = []
    if graph_receipt.is_file():
        try:
            graph_rows = json.loads(graph_receipt.read_text(encoding="utf-8")).get("results", [])
        except ValueError:
            graph_rows = []
    rows = [
        {"document": row.get("name", ""), "ok": bool(row.get("compiled")), "compiled_bytes": row.get("compiled_bytes", 0)}
        for row in graph_rows
    ]
    shutil.copytree(MESH_OUT, content / MODEL, dirs_exist_ok=True)
    shutil.copytree(ROOT / "artifacts" / "scout-port-skel" / MODEL, content / MODEL, dirs_exist_ok=True)
    mesh_documents = [content / MODEL / "scout_body.vmdl"]
    mesh_documents += sorted((content / MODEL / "materials").glob("*.vmat"))
    for document in mesh_documents:
        result = _run(
            [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", str(document)],
            cwd=content,
        )
        tail = (result.stdout + result.stderr).strip().splitlines()
        rows.append(
            {
                "document": document.name,
                "ok": any("0 failed" in line for line in tail[-6:]),
                "ok_line": next((line.strip() for line in tail if "compiled" in line and "failed" in line), ""),
            }
        )
    return {
        "available": True,
        "compiler": str(compiler),
        "graph_exit": graph_run.returncode,
        "documents": len(rows),
        "compiled": sum(1 for row in rows if row["ok"]),
        "failed": [row for row in rows if not row["ok"]],
        "mesh_documents": len(mesh_documents),
        "materials": len(list((csdk / "game" / MODEL / "materials").glob("*.vmat_c"))),
        "model_compiled": str(csdk / "game" / MODEL / "scout_body.vmdl_c"),
        "model_bytes": (csdk / "game" / MODEL / "scout_body.vmdl_c").stat().st_size
        if (csdk / "game" / MODEL / "scout_body.vmdl_c").is_file()
        else 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csdk", default="C:/Users/ala/Downloads/Reduced_CSDK_13")
    args = parser.parse_args(argv)
    csdk = Path(args.csdk)
    comp = compile_all(csdk)
    parsed = [parse_clip(name, csdk) for name in CLIPS]
    graph = graph_facts(csdk)
    reference = reference_shape()
    receipt = {
        "schema": "dmf.scout-anim/1",
        "generated": _stamp(),
        "clips": list(CLIPS),
        "parsed": {row["name"]: row for row in parsed},
        "graph": graph,
        "reference": reference,
        "compile": comp,
        "all_ok": all(row.get("ok") for row in parsed)
        and comp.get("available", False)
        and comp.get("compiled") == comp.get("documents")
        and graph.get("available", False)
        and len(graph.get("clip_references", [])) == 4,
    }
    _write(RECEIPT, receipt)
    for row in parsed:
        print(
            f"{row['name']:<14} {row.get('channels', 0):>3} channels "
            f"({row.get('suffixes', {}).get('_p', 0)}_p/{row.get('suffixes', {}).get('_o', 0)}_o) "
            f"{row.get('frames', 0):>2} frames {row.get('duration', 0):.4f}s "
            f"joints {row.get('track_joints', 0)}/{row.get('skeleton_joints', 0)} ok={row.get('ok')}"
        )
    if graph.get("available"):
        print(
            f"graph: {graph['compiled_bytes']} B, {graph['nodes']} nodes, "
            f"{len(graph['clip_references'])} clip refs, {len(graph['states'])} states, "
            f"{len(graph['aim_states'])} aim states"
        )
    if comp.get("available"):
        print(
            f"compile: {comp['compiled']}/{comp['documents']} documents, {len(comp['failed'])} failed, "
            f"model {comp['model_bytes']} B, {comp['materials']} .vmat_c"
        )
    print(f"reference: dota idle {reference.get('channels', 0)} channels {reference.get('suffixes', {})}")
    return 0 if receipt["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
