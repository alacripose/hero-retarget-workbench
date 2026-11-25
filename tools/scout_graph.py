"""Build, compile and verify Scout's own AnimGraph 2 document.

The graph is authored, not patched: `forge.scoutgraph` writes a standalone `CNmGraphDocument` whose
single variation is `Scout`, whose skeleton is the port's `scout_skel.dmx`-backed `.vnmskel`, and
whose nodes are the four port clips — two as states of `ScoutMotion`, two as named aim poses. No
frank path appears anywhere in the document or in the documents it names.

  python tools/scout_graph.py schema
  python tools/scout_graph.py build
  python tools/scout_graph.py compile --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
  python tools/scout_graph.py verify --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import scoutgraph  # noqa: E402
from tools.scout_clip_bake import _compile_one, _stamp  # noqa: E402

MODEL = "models/heroes_wip/scout"
ADDON = "scout_port"
SKELETON = f"{MODEL}/scout.vnmskel"
GRAPH = f"{MODEL}/scout.vnmgraph"
CLIP_DIR = f"{MODEL}/clips"
# The compiler treats the hierarchy's root variation as the document's default and, for any
# variation that is not `Default`, looks for a `<graph>+<variation>.vnmgraph` override document and
# access-violates when it is absent (measured in artifacts/scout-graph/bisect.py). So the root
# variation is `Default` and it carries Scout's skeleton; the nodes carry Scout's names.
VARIATION = "Default"
GRAPH_OWNER = "Scout"
LIVE = ROOT / "artifacts" / "scout-update" / "live-graphs" / "animgraphs" / "animgraph2" / "hero"
CLIPS = ROOT / "artifacts" / "scout-own-clips" / "clips"
DMX = ROOT / "artifacts" / "scout-own-clips" / "dmx"
OUT = ROOT / "artifacts" / "scout-graph"
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-graph.json"
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
DOTA_TOOLS = ROOT / "artifacts" / "dota-tools"

# Two motion clips (the ones whose bake reported moving channels) and two 2-frame aim poses.
STATES = ("Scout_Attack", "Scout_Reload")
POSES = ("Scout_AimIdle", "Scout_AimRun")
# graph name -> the port sequence baked for it (tools/scout_own_clips.py baked these four)
CLIP_SOURCES = {
    "Scout_Attack": "AttackStand_PRIMARY",
    "Scout_Reload": "PRIMARY_reload_loop",
    "Scout_AimIdle": "PRIMARY_aimmatrix_idle",
    "Scout_AimRun": "PRIMARY_aimmatrix_run",
}
# motion vs pose, from the bake receipt: the aim matrix clips are 2-frame poses, not motion
CLIP_FRAMES = {"Scout_Attack": 21, "Scout_Reload": 20, "Scout_AimIdle": 2, "Scout_AimRun": 2}


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    existing.update(payload)
    path.write_text(json.dumps(existing, indent=1) + "\n", encoding="utf-8")
    return path


def _content(csdk: Path) -> Path:
    return csdk / "content" / "citadel_addons" / ADDON


def _game(csdk: Path) -> Path:
    return csdk / "game" / "citadel_addons" / ADDON


def clip_paths() -> dict[str, str]:
    """The four port clips, by graph name, as the paths the graph will name."""
    return {name: f"{CLIP_DIR}/{name}.vnmclip" for name in STATES + POSES}


def cmd_schema(args) -> int:
    """Dump what the live documents contain, so the authored document copies the tool's own shape."""
    inventory = {}
    for name in ("hero_aim.vnmgraph", "hero.vnmgraph"):
        path = Path(args.live) / name
        if not path.is_file():
            raise SystemExit(f"live-graph-missing: {path}")
        inventory[name] = scoutgraph.schema_inventory(path.read_text(encoding="utf-8", errors="replace"))
    payload = {
        "schema": "dmf.scout-graph-schema/1",
        "generated": _stamp(),
        "source": str(args.live),
        "accepted_classes": inventory,
        "document_keys": list(scoutgraph.DOCUMENT_KEYS),
        "flow_graph_keys": list(scoutgraph.FLOW_GRAPH_KEYS),
        "pose_node_keys": list(scoutgraph.POSE_NODE_KEYS),
        "state_keys": list(scoutgraph.STATE_KEYS),
    }
    _write(Path(args.report), payload)
    for name, found in inventory.items():
        print(f"{name}: {len(found['classes'])} classes, {found['clip_references']} clip refs, {found['skeleton_references']} skeleton refs")
        for cls, count in sorted(found["classes"].items(), key=lambda row: -row[1])[:8]:
            print(f"  {count:>5}  {cls}")
    return 0


def cmd_build(args) -> int:
    clips = clip_paths()
    missing = [name for name, source in CLIP_SOURCES.items() if not (CLIPS / f"{source}.vnmclip").is_file()]
    if missing:
        raise SystemExit(f"clip-missing: bake first ({', '.join(missing)})")
    # The baked clips carry the port sequence's name; the graph names them for their branch.
    for name, source in CLIP_SOURCES.items():
        target = Path(args.out) / CLIP_DIR / f"{name}.vnmclip"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CLIPS / f"{source}.vnmclip", target)
    payload = scoutgraph.build_scout_graph(
        variation=VARIATION, skeleton=SKELETON, clips=clips, states=list(STATES)
    )
    document = scoutgraph.write_document(payload, Path(args.out) / GRAPH)
    text = document.read_text(encoding="utf-8")
    if "frank" in text.lower():
        raise SystemExit("frank-reference-in-graph")
    receipt = {
        "schema": "dmf.scout-graph/1",
        "generated": _stamp(),
        "variation": VARIATION,
        "skeleton": SKELETON,
        "graph": GRAPH,
        "document": str(document),
        "document_bytes": document.stat().st_size,
        "states": list(STATES),
        "poses": list(POSES),
        "clips": clips,
        "clip_sources": CLIP_SOURCES,
        "nodes": len(re.findall(r"_class = \"CNmGraphDoc[A-Za-z]+Node\"", text)),
        "clip_references": len(re.findall(r'm_clip = "', text)),
        "frank_references": text.lower().count("frank"),
    }
    _write(Path(args.report), receipt)
    print(
        f"BUILD {document} {receipt['document_bytes']} bytes, {receipt['nodes']} nodes, "
        f"{receipt['clip_references']} clip refs, {receipt['frank_references']} frank refs"
    )
    return 0


def _compiler(csdk: Path) -> Path:
    for path in (csdk / "game" / "bin" / "win64" / "resourcecompiler.exe", csdk / "bin" / "win64" / "resourcecompiler.exe"):
        if path.is_file():
            return path
    raise SystemExit(f"compiler-missing under {csdk}")


def _compile(document: Path, *, compiler: Path, game: Path, content: Path) -> dict:
    result = subprocess.run(
        [str(compiler), "-nop4", "-f", "-game", str(game), "-i", str(document.resolve())],
        cwd=str(content),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
    )
    tail = (result.stdout or "").strip().splitlines()
    ok_line = next((line.strip() for line in tail if line.strip().startswith(("OK:", "ERROR:"))), "")
    errors = [line.strip() for line in tail if "ERROR" in line or "Load error" in line or "Invalid" in line]
    return {
        "name": document.name,
        "returncode": result.returncode,
        "ok_line": ok_line,
        "errors": errors[:6],
        "stdout_tail": tail[-4:],
    }


def cmd_compile(args) -> int:
    csdk = Path(args.csdk)
    out = Path(args.out)
    content = _content(csdk)
    graph = out / GRAPH
    if not graph.is_file():
        raise SystemExit(f"build-first: {graph}")
    # Clips first: the graph names `clips/<name>.vnmclip`, and the compiler resolves them.
    for name in STATES + POSES:
        source = out / CLIP_DIR / f"{name}.vnmclip"
        target = content / CLIP_DIR / f"{name}.vnmclip"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Each clip document names its animation DMX; the compiler reads it from the addon root, looking
    # for the lower-case name. Staging it here is what makes a rebake reach the compiled bytes.
    for source in CLIP_SOURCES.values():
        document = DMX / f"{source}.dmx"
        target = content / MODEL / "dmx" / f"{source.lower()}.dmx"
        if document.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(document, target)
    shutil.copytree(Path(args.out).parent / "scout-port-skel" / MODEL, content / MODEL, dirs_exist_ok=True)
    (content / MODEL).mkdir(parents=True, exist_ok=True)
    shutil.copy2(graph, content / GRAPH)

    compiler = _compiler(csdk)
    results = []
    for name in STATES + POSES:
        document = content / CLIP_DIR / f"{name}.vnmclip"
        row = _compile(document, compiler=compiler, game=csdk / "game" / "citadel", content=csdk / "content")
        compiled = _game(csdk) / CLIP_DIR / (name.lower() + ".vnmclip_c")
        row["compiled"] = str(compiled) if compiled.is_file() else ""
        row["compiled_bytes"] = compiled.stat().st_size if compiled.is_file() else 0
        results.append(row)
        print(f"  {name:<22} {row['ok_line'] or row['errors'][:1]} {row['compiled_bytes']}B")

    row = _compile(content / GRAPH, compiler=compiler, game=csdk / "game" / "citadel", content=csdk / "content")
    compiled = _game(csdk) / MODEL / "scout.vnmgraph_c"
    row["compiled"] = str(compiled) if compiled.is_file() else ""
    row["compiled_bytes"] = compiled.stat().st_size if compiled.is_file() else 0
    results.append(row)
    print(f"  scout.vnmgraph         {row['ok_line'] or row['errors'][:1]} {row['compiled_bytes']}B")

    failed = [row for row in results if not row["compiled"]]
    _write(
        Path(args.report),
        {
            "schema": "dmf.scout-graph-compile/1",
            "generated": _stamp(),
            "compiler": str(compiler),
            "game": str(csdk / "game" / "citadel"),
            # Named apart from `compiled`, which `verify` uses for the compiled graph's path: the
            # receipt is merged, so two meanings on one key lose one of them.
            "document_total": len(results),
            "compiled_documents": len(results) - len(failed),
            "results": results,
        },
    )
    print(f"COMPILED {len(results) - len(failed)}/{len(results)} documents")
    if failed:
        for row in failed:
            print(f"  FAILED {row['name']}: {row['errors'] or row['stdout_tail']}")
        raise SystemExit("graph-compile-failed")
    return 0


def cmd_probe_toolchain(args) -> int:
    """Measure whether the Dota 2 tools branch carries an AnimGraph 2 compiler at all."""
    compiler = _compiler(DOTA_TOOLS)
    game = DOTA_TOOLS / "game" / "dota"
    content = DOTA_TOOLS / "content"
    content.mkdir(parents=True, exist_ok=True)
    document = content / "models" / "heroes_wip" / "scout" / "scout.vnmgraph"
    document.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(args.out) / GRAPH, document)
    row = _compile(document, compiler=compiler, game=game, content=content)
    row["branch"] = "dota-tools"
    row["converter_present"] = (DOTA_TOOLS / "game" / "bin" / "win64" / "dmxconvert.exe").is_file()
    _write(Path(args.report), {"dota_toolchain": row})
    print(f"DOTA BRANCH: {row['ok_line'] or 'no result'} | {row['errors'][:2]}")
    return 0


def cmd_verify(args) -> int:
    """Read the compiled graph, not the source: clips, skeleton and the skeleton's joint count."""
    csdk = Path(args.csdk)
    compiled = _game(csdk) / MODEL / "scout.vnmgraph_c"
    if not compiled.is_file():
        raise SystemExit(f"compiled-graph-missing: {compiled}")
    raw = compiled.read_bytes()
    binary_text = raw.decode("latin-1", errors="replace")
    destination = Path(args.out) / "verify"
    shutil.rmtree(destination, ignore_errors=True)
    decompiled = ""
    if S2V.is_file():
        subprocess.run(
            [str(S2V), "-i", str(compiled), "-d", "-o", str(destination)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=600,
        )
        dumped = sorted(destination.rglob("scout.vnmgraph")) if destination.is_dir() else []
        decompiled = str(dumped[0]) if dumped else ""
    if not decompiled:
        raise SystemExit(f"decompile-empty: no scout.vnmgraph under {destination}")
    # The compiled form stores resources by hash; the graph it decodes back to is what a re-parse can
    # read, and it is the compiled document's own content, not the authored source.
    text = Path(decompiled).read_text(encoding="utf-8", errors="replace")
    lower = text.lower()
    clips = clip_paths()
    found_clips = {name: path.lower() in lower for name, path in clips.items()}
    skeleton_named = "models/heroes_wip/scout/scout.vnmskel" in lower or "models/heroes_wip/scout/dmx/mesh/scout_skel.dmx" in lower
    frank = "frank" in lower or "frank" in binary_text.lower()
    states = sorted(set(re.findall(r'm_name = "(state_[A-Za-z0-9_]+)"', text)))
    aim_states = sorted(set(re.findall(r'm_name = "(aim_state_[A-Za-z0-9_]+)"', text)))
    aims = sorted(set(re.findall(r'm_name = "(aim_Scout_[A-Za-z0-9_]+)"', text)))
    joints = __import__("forge.portskel", fromlist=["read_reference"]).read_reference(
        Path("F:/Documents/scout_anims/ref.smd")
    )
    skeleton_c = _game(csdk) / MODEL / "scout.vnmskel_c"
    skeleton_bytes = skeleton_c.stat().st_size if skeleton_c.is_file() else 0
    bones = 0
    if skeleton_c.is_file():
        skeleton_dump = Path(args.out) / "verify-skeleton"
        shutil.rmtree(skeleton_dump, ignore_errors=True)
        subprocess.run(
            [str(S2V), "-i", str(skeleton_c), "-d", "-o", str(skeleton_dump)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=600,
        )
        found = sorted(skeleton_dump.rglob("scout.vnmskel")) if skeleton_dump.is_dir() else []
        if found:
            skeleton_text = found[0].read_text(encoding="utf-8", errors="replace")
            high = skeleton_text.split("m_highLODBones")[1].split("]")[0]
            bones = len(re.findall(r'"[^"]+"', high))
    channel_counts = {}
    for name in list(clips):
        kv2 = ROOT / "artifacts" / "scout-own-clips" / "kv2" / f"{CLIP_SOURCES[name]}.dmx"
        if kv2.is_file():
            channel_counts[name] = len(re.findall(r'_o"', kv2.read_text(encoding="utf-8", errors="replace")))
    result = (
        "PASS"
        if all(found_clips.values())
        and skeleton_named
        and not frank
        and len(states) == len(STATES)
        and len(aim_states) == len(POSES)
        and len(aims) >= len(POSES)
        and bones == len(joints)
        else "FAIL"
    )
    receipt = {
        "schema": "dmf.scout-graph-verify/1",
        "generated": _stamp(),
        "compiled": str(compiled),
        "compiled_bytes": compiled.stat().st_size,
        "decompiled": decompiled,
        "decompiled_bytes": Path(decompiled).stat().st_size,
        "skeleton_compiled": str(skeleton_c) if skeleton_c.is_file() else "",
        "skeleton_compiled_bytes": skeleton_bytes,
        "skeleton_joints": len(joints),
        "skeleton_bones_in_compiled": bones,
        "clip_channels": channel_counts,
        "clips": found_clips,
        "clip_names": list(clips),
        "states_in_compiled": states,
        "aim_states_in_compiled": aim_states,
        "aim_poses_in_compiled": aims,
        "clip_frames": CLIP_FRAMES,
        "skeleton_named": skeleton_named,
        "frank_references": frank,
        "result": result,
    }
    _write(Path(args.report), receipt)
    print(f"VERIFY {compiled.name} {receipt['compiled_bytes']}B -> {decompiled} {receipt['decompiled_bytes']}B")
    for name, found in found_clips.items():
        print(f"  clip {name:<16} {'in compiled graph' if found else 'MISSING'} ({channel_counts.get(name, 0)} channels)")
    print(f"  motion states {states}")
    print(f"  aim states {aim_states} with pose nodes {aims}")
    print(
        f"  skeleton named: {skeleton_named} | joints {len(joints)} | bones in compiled skeleton {bones} "
        f"| frank refs: {receipt['frank_references']}"
    )
    print(f"RESULT: {result}")
    if result != "PASS":
        raise SystemExit("graph-verify-failed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--report", default=str(RECEIPT))
    parser.add_argument("--live", default=str(LIVE))
    sub = parser.add_subparsers(dest="command", required=True)
    schema = sub.add_parser("schema", help="dump the classes and keys the live documents carry")
    schema.set_defaults(func=cmd_schema)
    build = sub.add_parser("build", help="author the Scout graph document")
    build.set_defaults(func=cmd_build)
    compile_parser = sub.add_parser("compile", help="compile the clips and the graph with CSDK13")
    compile_parser.add_argument("--csdk", required=True)
    compile_parser.set_defaults(func=cmd_compile)
    probe = sub.add_parser("probe-toolchain", help="measure the Dota 2 tools branch against the same document")
    probe.set_defaults(func=cmd_probe_toolchain)
    verify = sub.add_parser("verify", help="read the compiled graph for its clips and skeleton")
    verify.add_argument("--csdk", required=True)
    verify.set_defaults(func=cmd_verify)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
