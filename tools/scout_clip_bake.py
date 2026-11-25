"""Bake Scout's SMD clips onto frank's skeleton, write the clips both graphs name, and compile.

The port's animations are TF2 SMDs on a 76-node `bip_*` rig; the slot is frank, whose skeleton is
107 joints named `pelvis`, `spine_0..3`, `arm_upper_L`, `leg_lower_R`, `ball_L`, `finger_*_2_R`.
Nothing shares an index, so the bake resolves every node **by name** and reports whatever it could
not resolve instead of writing a channel onto the wrong joint.

Four steps, each with its own receipt:

    python tools/scout_clip_bake.py plan   --workspace F:/Documents --out artifacts/.../plan.json
    python tools/scout_clip_bake.py bake   --plan … --template … --out … --clips-out …
    python tools/scout_clip_bake.py compile --plan … --csdk … --graphs …
    python tools/scout_clip_bake.py verify  --plan … --dmx… --csdk …

`plan` reads what the two graphs actually ask for: the Dota-branch `scout_loco.vanmgrph` names 24
sequences, and the live `hero_aim_scout.vnmgraph` carries 18 Scout override references to 12 distinct
`.vnmclip` files. `bake` writes one animation DMX per distinct clip on frank's skeleton plus the
`.vnmclip` document that points at it. `compile` installs them under the content root and runs
`resourcecompiler`. `verify` reads the written files back and refuses an empty or constant clip.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from pathlib import PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import clipbake, scout  # noqa: E402

DEFAULT_TEMPLATE = ROOT / "artifacts" / "scout-update" / "dmx" / "aim_weapon_idle_kv2.xml"
DEFAULT_DMXCONVERT = (
    ROOT / "artifacts" / "dota-tools" / "game" / "bin" / "win64" / "dmxconvert.exe"
)

# Scout's TF2 node names to frank's joints, read off the SMD node table and the skeleton's joint
# list. Fingers are generated below because the two rigs number them the same way.
BONE_MAP = {
    "bip_pelvis": "pelvis",
    "bip_spine_0": "spine_0",
    "bip_spine_1": "spine_1",
    "bip_spine_2": "spine_2",
    "bip_spine_3": "spine_3",
    "bip_neck": "neck_0",
    "bip_head": "head",
    "bip_collar_L": "clavicle_L",
    "bip_collar_R": "clavicle_R",
    "bip_upperArm_L": "arm_upper_L",
    "bip_upperArm_R": "arm_upper_R",
    "bip_lowerArm_L": "arm_lower_L",
    "bip_lowerArm_R": "arm_lower_R",
    "bip_hand_L": "hand_L",
    "bip_hand_R": "hand_R",
    "bip_hip_L": "leg_upper_L",
    "bip_hip_R": "leg_upper_R",
    "bip_knee_L": "leg_lower_L",
    "bip_knee_R": "leg_lower_R",
    "bip_foot_L": "ankle_L",
    "bip_foot_R": "ankle_R",
    "bip_toe_L": "ball_L",
    "bip_toe_R": "ball_R",
    "weapon_bone": "weapon",
}
for _side in ("L", "R"):
    for _finger in ("thumb", "index", "middle", "ring", "pinky"):
        for _segment in (0, 1, 2):
            BONE_MAP[f"bip_{_finger}_{_segment}_{_side}"] = f"finger_{_finger}_{_segment}_{_side}"

SKELETON = "models/heroes_wip/frank/frank.vnmskel"
CLIP_DIR = "models/heroes_wip/frank/clips"
DMX_DIR = "models/heroes_wip/frank/dmx/animation"


def _stamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write(path: Path, payload) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return path


def _tools() -> tuple[Path, Path]:
    dmxconvert = Path(
        shutil.which("dmxconvert")
        or (ROOT / "artifacts" / "dota-tools" / "game" / "bin" / "win64" / "dmxconvert.exe")
    )
    if not dmxconvert.is_file():
        raise clipbake.ClipError(f"dmxconvert-missing: {dmxconvert}")
    return dmxconvert, DEFAULT_TEMPLATE


def _template_joints(template_text: str) -> list[str]:
    return sorted(
        {
            match.group(1)[:-2]
            for match in re.finditer(r'"name"\s+"string"\s+"([^"]+_o)"', template_text)
        }
    )


def _scout_clip_names(aim_graph_text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r'm_variationID = "Scout"[\s\S]{0,400}?m_clip = "([^"]+)"', aim_graph_text):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return names


def cmd_plan(args) -> int:
    workspace = Path(args.workspace)
    loco_graph = Path(args.loco_graph)
    aim_graph = Path(args.aim_graph)
    for path in (loco_graph, aim_graph):
        if not path.is_file():
            raise clipbake.ClipError(f"graph-missing: {path}")
    slots = list(scout.sequence_names(loco_graph.read_text(encoding="utf-8", errors="replace")))
    aim_paths = _scout_clip_names(aim_graph.read_text(encoding="utf-8", errors="replace"))
    sequences: dict[str, str] = {}
    for qc in sorted(workspace.glob("*.qc")):
        for name, smd in clipbake.parse_qc_sequences(qc).items():
            sequences.setdefault(name, smd)
    if not sequences:
        raise clipbake.ClipError(f"qc-sequences-empty: no $sequence under {workspace}")
    smd_index: dict[str, str] = {}
    for folder in ("scout_animations_anims", "scout_anims"):
        for smd in sorted((workspace / folder).glob("*.smd")):
            smd_index.setdefault(smd.stem, f"{folder}/{smd.name}")
    rows, missing = clipbake.plan_rows(
        loco_slots=slots, aim_clips=aim_paths, sequences=sequences, smd_index=smd_index
    )
    plan = {
        "schema": "dmf.scout-clip-plan/1",
        "generated": _stamp(),
        "workspace": str(workspace),
        "loco_graph": str(loco_graph),
        "aim_graph": str(aim_graph),
        "qc_sequences": len(sequences),
        "loco_slots": slots,
        "aim_references": len(aim_paths),
        "aim_clips": [Path(value).stem for value in aim_paths],
        "rows": rows,
        "missing": missing,
        "summary": clipbake.summarise(rows),
    }
    out = _write(Path(args.out), plan)
    print(f"plan {out}")
    print(
        f"  {plan['summary']['references']} references: {len(slots)} loco slots, "
        f"{len(aim_paths)} aim clip paths ({plan['summary']['distinct_clips']} distinct files)"
    )
    print(f"  {plan['summary']['distinct_sources']} Scout sequences feed them: {plan['summary']['source_use']}")
    if missing:
        for row in missing:
            print(f"  MISSING {row['name']}: {row['reason']}")
        raise clipbake.ClipError(f"clip-plan-incomplete: {len(missing)} references have no source")
    return 0


def _bake_one(row: dict, template_text: str, joints: list[str], args) -> dict:
    clip = clipbake.parse_smd(Path(args.workspace) / row["smd"])
    mapped: dict[str, int] = {}
    unknown: list[str] = []
    for node in clip.nodes:
        target = BONE_MAP.get(node.name)
        if target and target in joints:
            mapped[target] = node.index
        elif node.name in joints:
            mapped[node.name] = node.index
        else:
            unknown.append(node.name)
    if len(mapped) < 8:
        raise clipbake.ClipError(
            f"clip-bake-too-few-joints: {row['name']} resolved {len(mapped)} of {len(clip.nodes)} nodes"
        )
    # A one-frame SMD is a static aim pose. Two samples at one frame apart keep it a valid clip
    # with a real duration instead of a zero-length one the player divides by.
    frames = clip.frames if len(clip.frames) > 1 else (clip.frames[0], clip.frames[0])
    samples: dict[str, list[tuple[float, float, float, float]]] = {}
    for joint, index in mapped.items():
        series = []
        for frame in frames:
            _, rotation = frame.get(index, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
            series.append(clipbake.euler_to_quat(*rotation))
        samples[joint] = series
    varying_channels = sum(
        1
        for series in samples.values()
        if len({tuple(round(value, 6) for value in sample) for sample in series}) > 1
    )
    # The threshold is the same one `verify` applies: a handful of channels drifting a fraction of
    # a degree is not motion, it is a pose whose real movement lived on TS2-only bones.
    moving = varying_channels >= 8
    times = [index / clipbake.FPS for index in range(len(frames))]
    duration = max(len(frames) - 1, 1) / clipbake.FPS
    body, report = clipbake.bake_kv2(
        template_text, samples=samples, times=times, duration=duration
    )
    kv2_path = Path(args.out) / f"{row['name']}.kv2.dmx"
    kv2_path.parent.mkdir(parents=True, exist_ok=True)
    kv2_path.write_text(body, encoding="utf-8")
    dmx_path = Path(args.out) / f"{row['name']}.dmx"
    dmxconvert, _ = _tools()
    result = subprocess.run(
        [str(dmxconvert), "-i", str(kv2_path), "-o", str(dmx_path), "-oe", "binary"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=300,
    )
    if result.returncode != 0 or not dmx_path.is_file():
        raise clipbake.ClipError(
            f"dmxconvert-failed: {row['name']} rc={result.returncode} {result.stdout[-200:]}"
        )
    clip_doc = Path(args.clips_out) / f"{row['name']}.vnmclip"
    clipbake.write_vnmclip(
        clip_doc,
        clip_name=row["name"],
        skeleton=SKELETON,
        source_dmx=f"{DMX_DIR}/{row['name']}.dmx",
    )
    return {
        **row,
        "frames": len(frames),
        "static_pose": not moving,
        "static_reason": ""
        if moving
        else ("one-frame-source" if len(clip.frames) == 1 else "motion-on-unmapped-nodes"),
        "varying_channels": varying_channels,
        "duration": round(duration, 4),
        "smd_nodes": len(clip.nodes),
        "joints_resolved": len(mapped),
        "unresolved_nodes": unknown,
        "channels_baked": len(report["baked"]),
        "channels_held": len(report["held"]),
        "dmx": str(dmx_path),
        "dmx_bytes": dmx_path.stat().st_size,
        "vnmclip": str(clip_doc),
    }


def cmd_bake(args) -> int:
    plan = clipbake.load_plan(Path(args.plan))
    template_text = Path(args.template).read_text(encoding="utf-8", errors="replace")
    joints = _template_joints(template_text)
    rows = []
    for row in plan["rows"]:
        rows.append(_bake_one(row, template_text, joints, args))
    receipt = {
        "schema": "dmf.scout-clip-bake/1",
        "generated": _stamp(),
        "plan": str(args.plan),
        "template": str(args.template),
        "skeleton_joints": len(joints),
        "clips": rows,
        "summary": {
            "clips": len(rows),
            "references": plan["summary"]["references"],
            "frames_total": sum(row["frames"] for row in rows),
            "channels_baked_total": sum(row["channels_baked"] for row in rows),
            "dmx_bytes_total": sum(row["dmx_bytes"] for row in rows),
        },
    }
    out = _write(Path(args.report), receipt)
    print(f"RECEIPT {out}")
    for row in rows:
        print(
            f"  {row['name']:<36} {row['frames']:>3}f  {row['joints_resolved']:>3}/{row['smd_nodes']} joints"
            f"  {row['channels_baked']:>3} baked  {row['dmx_bytes']:>8}B"
        )
        if row["unresolved_nodes"]:
            print(f"      unresolved: {', '.join(row['unresolved_nodes'][:8])}")
    print(f"BAKED {receipt['summary']['clips']} clips, {receipt['summary']['dmx_bytes_total']} bytes")
    if args.compile:
        return cmd_compile(
            argparse.Namespace(
                plan=args.plan,
                receipt=out,
                csdk=args.csdk,
                graphs=args.graphs,
                skeleton_source=args.skeleton_source,
            )
        )
    return 0


def _content(csdk: Path) -> Path:
    return csdk / "content" / "citadel_addons" / "scout_animgraph"


def _compile_one(csdk: Path, document: Path, label: str) -> dict:
    """Compile one document the way the repo's own clip handoff does.

    `-i` takes an **absolute** path and the working directory is the content root; a relative
    path makes the compiler report `0 compiled, 0 failed, 0 skipped`, which reads like success.
    The output lands under `<csdk>/game/citadel_addons/<addon>/` with a lower-cased name, not
    beside the source, so the receipt records the path it actually found.
    """
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    result = subprocess.run(
        [
            str(compiler),
            "-nop4",
            "-f",
            "-game",
            str(csdk / "game" / "citadel"),
            "-i",
            str(document.resolve()),
        ],
        cwd=str(csdk / "content"),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=600,
    )
    tail = (result.stdout or "").strip().splitlines()
    return {
        "name": label,
        "returncode": result.returncode,
        "ok_line": next((line.strip() for line in tail if line.strip().startswith(("OK:", "ERROR:"))), ""),
        "error": next((line.strip() for line in tail if "ERROR" in line or "Invalid" in line), ""),
        "stdout_tail": tail[-3:],
    }


def _compiled_path(document: Path, entry_name: str) -> Path:
    """Where the compiler writes a document: `<addon>/game` mirror, lower-cased.

    ``entry_name`` is the full source name including its extension, because the compiler
    keeps it: ``PRIMARY_aimmatrix_idle.vnmclip`` becomes ``primary_aimmatrix_idle.vnmclip_c``.
    """
    content = document
    while content.name.lower() != "content":
        if content.parent == content:
            break
        content = content.parent
    csdk = content.parent
    relative = document.relative_to(content / "citadel_addons" / "scout_animgraph")
    return (
        csdk
        / "game"
        / "citadel_addons"
        / "scout_animgraph"
        / relative.parent
        / (entry_name.lower() + "_c")
    )


def cmd_compile(args) -> int:
    """Install the clips into the addon content root and compile them with resourcecompiler."""
    receipt_path = Path(args.receipt)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    csdk = Path(args.csdk)
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    if not compiler.is_file():
        raise clipbake.ClipError(f"compiler-missing: {compiler}")
    content = _content(csdk)
    for row in receipt["clips"]:
        for source, target in (
            (Path(row["dmx"]), content / DMX_DIR / f"{row['name']}.dmx"),
            (Path(row["vnmclip"]), content / CLIP_DIR / f"{row['name']}.vnmclip"),
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    skeleton_source = Path(args.skeleton_source)
    for source, target in (
        (skeleton_source, content / "models/heroes_wip/frank/frank.vnmskel"),
        (skeleton_source.parent / "dmx/mesh/frank_skel.dmx", content / "models/heroes_wip/frank/dmx/mesh/frank_skel.dmx"),
    ):
        if not source.is_file():
            raise clipbake.ClipError(f"skeleton-source-missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    skeleton = _compile_one(csdk, content / "models/heroes_wip/frank/frank.vnmskel", "frank.vnmskel")
    skeleton_output = _compiled_path(content / "models/heroes_wip/frank/frank.vnmskel", "frank.vnmskel")
    skeleton["compiled"] = str(skeleton_output) if skeleton_output.is_file() else ""
    compiled = []
    for row in receipt["clips"]:
        document = content / CLIP_DIR / f"{row['name']}.vnmclip"
        outcome = _compile_one(csdk, document, row["name"])
        output = _compiled_path(document, document.name)
        outcome["compiled"] = str(output) if output.is_file() else ""
        outcome["bytes"] = output.stat().st_size if output.is_file() else 0
        compiled.append(outcome)
    graphs = []
    for graph in args.graphs or []:
        graph_path = Path(graph)
        target = content / "animgraphs" / graph_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(graph_path, target)
        outcome = _compile_one(csdk, target, graph_path.name)
        base = content / "animgraphs" / graph_path.name
        candidates = [
            _compiled_path(base, base.name),
        ]
        candidates.extend(sorted(_compiled_path(base, base.name).parent.glob(f"{base.name.lower()}+*_c")))
        outputs = [path for path in candidates if path.is_file()]
        outcome["graph"] = str(graph_path)
        outcome["compiled"] = str(outputs[0]) if outputs else ""
        outcome["bytes"] = outputs[0].stat().st_size if outputs else 0
        outcome["variations"] = len(outputs) - 1 if len(outputs) > 1 else 0
        graphs.append(outcome)
    receipt["compile"] = {"skeleton": skeleton, "clips": compiled, "graphs": graphs}
    _write(receipt_path, receipt)
    failed = [row for row in compiled if not row["compiled"]]
    print(f"COMPILED skeleton {1 if skeleton['compiled'] else 0}/1 {skeleton['ok_line']}")
    print(f"COMPILED clips {len(compiled) - len(failed)}/{len(compiled)}")
    for row in failed[:6]:
        print(f"  FAILED {row['name']} {row['ok_line']} {row['error']}")
    for row in graphs:
        print(
            f"  graph {Path(row['graph']).name}: {row['ok_line']} -> {row['bytes']} bytes"
            f" ({row['variations']} variations)"
        )
    if failed or not skeleton["compiled"]:
        raise clipbake.ClipError(f"clip-compile-failed: {len(failed)} clips")
    return 0


def cmd_verify(args) -> int:
    """Read every written clip back and prove it carries real, varying keyframes."""
    receipt_path = Path(args.receipt)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    dmxconvert, _ = _tools()
    rows = []
    bad = []
    for row in receipt["clips"]:
        dmx = (
            Path(row["dmx"])
            if not args.from_content
            else _content(Path(args.csdk)) / DMX_DIR / f"{row['name']}.dmx"
        )
        if not dmx.is_file():
            bad.append({"name": row["name"], "problem": "dmx-missing", "path": str(dmx)})
            continue
        kv2 = Path(args.out) / f"{row['name']}.verify.kv2.dmx"
        kv2.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [str(dmxconvert), "-i", str(dmx), "-o", str(kv2), "-oe", "keyvalues2"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=300,
        )
        if result.returncode != 0 or not kv2.is_file():
            bad.append({"name": row["name"], "problem": "dmxconvert-read-failed", "rc": result.returncode})
            continue
        text = kv2.read_text(encoding="utf-8", errors="replace")
        channels = re.findall(r'"values"\s+"quaternion_array"\s*\n\s*\[([\s\S]*?)\n\s*\]', text)
        animated = 0
        samples = 0
        per_frame = set()
        for body in channels:
            values = [line.strip().strip('",') for line in body.splitlines() if line.strip()]
            samples += len(values)
            per_frame.add(len(values))
            if len({value for value in values}) > 1:
                animated += 1
        rows.append(
            {
                "name": row["name"],
                "frames": row.get("frames"),
                "static_pose": bool(row.get("static_pose")),
                "quaternion_channels": len(channels),
                "animated_channels": animated,
                "samples_per_channel": sorted(per_frame),
                "samples": samples,
                "vnmclip": row["vnmclip"],
            }
        )
        # A static aim pose cannot vary; it still has to carry the pose on every channel.
        minimum_samples = row.get("frames") or 1
        if samples == 0 or min(per_frame) < minimum_samples:
            bad.append(
                {
                    "name": row["name"],
                    "problem": "clip-empty-or-short",
                    "samples_per_channel": sorted(per_frame),
                    "frames": minimum_samples,
                }
            )
        elif not row.get("static_pose") and animated < 8:
            bad.append({"name": row["name"], "problem": "clip-constant", "animated": animated})
    out = _write(
        Path(args.report),
        {
            "schema": "dmf.scout-clip-verify/1",
            "generated": _stamp(),
            "clips": rows,
            "failures": bad,
            "summary": {
                "clips": len(rows),
                "animated_clips": sum(1 for row in rows if row["animated_channels"] >= 8),
                "static_clips": sum(1 for row in rows if row["static_pose"]),
                "animated_channels_total": sum(row["animated_channels"] for row in rows),
                "samples_total": sum(row["samples"] for row in rows),
                "min_animated": min((row["animated_channels"] for row in rows), default=0),
            },
        },
    )
    print(f"VERIFY {out}")
    print(
        f"  {len(rows)} clips, {sum(row['animated_channels'] for row in rows)} animated quaternion channels, "
        f"{sum(row['samples'] for row in rows)} samples"
    )
    for row in bad[:8]:
        print(f"  FAIL {row['name']}: {row['problem']}")
    if bad:
        raise clipbake.ClipError(f"clip-verify-failed: {len(bad)} clips")
    print("RESULT: PASS")
    return 0


VPK_SIGNATURE = 0x55AA1234
VPK_DIR_ARCHIVE = 0x7FFF


def write_vpk(files: dict[str, bytes], destination: Path) -> Path:
    """Write a single-archive VPK (version 2) whose tree the repo reader parses.

    The tree is extension -> directory -> name, every string null-terminated and every
    entry 18 bytes: crc, preload, archive index, offset, length, terminator.
    Offsets are relative to the file-data section.
    """
    groups: dict[str, dict[str, dict[str, bytes]]] = {}
    for path, data in files.items():
        document = PurePosixPath(path)
        extension = document.suffix.lstrip(".")
        directory = document.parent.as_posix() or " "
        groups.setdefault(extension, {}).setdefault(directory, {})[document.stem] = data
    tree = bytearray()
    data_section = bytearray()
    for extension in sorted(groups):
        tree += extension.encode("utf-8") + b"\0"
        for directory in sorted(groups[extension]):
            tree += directory.encode("utf-8") + b"\0"
            for name in sorted(groups[extension][directory]):
                payload = groups[extension][directory][name]
                tree += name.encode("utf-8") + b"\0"
                tree += struct.pack(
                    "<IHHIIH",
                    zlib.crc32(payload) & 0xFFFFFFFF,
                    0,
                    VPK_DIR_ARCHIVE,
                    len(data_section),
                    len(payload),
                    0xFFFF,
                )
                data_section += payload
            # A single empty string ends this directory's name list.
            tree += b"\0"
        # ... and this extension's directory list, with the last one ending the tree.
        tree += b"\0"
    tree += b"\0"
    header = struct.pack("<IIIIIII", VPK_SIGNATURE, 2, len(tree), len(data_section), 0, 0, 0)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(header + bytes(tree) + bytes(data_section))
    return destination


def cmd_pack(args) -> int:
    """Pack the compiled graph, skeleton, clips and their DMX into one addon VPK."""
    addon = Path(args.addon_root)
    content = Path(args.content_root) if args.content_root else addon
    wanted = [
        "animgraphs/hero_aim_scout.vnmgraph_c",
        "animgraphs/hero_aim_scout.vnmgraph+scout.vnmgraph_c",
        "animgraphs/scout_loco.vanmgrph_c",
        "models/heroes_wip/frank/frank.vnmskel_c",
    ]
    # The hero table is optional: the clip pack ships without it, the Scout hero pack needs it.
    if (addon / "scripts/heroes.vdata_c").is_file():
        wanted.append("scripts/heroes.vdata_c")
    wanted += [
        f"{CLIP_DIR}/{path.name}" for path in sorted((addon / CLIP_DIR).glob("*.vnmclip_c"))
    ]
    # The compiled clips reference these DMX by path and do not embed them, so the
    # animation source belongs in the pack even though it is not compiled.
    # Compiled clip names are lower-cased by the compiler; the DMX beside them keeps
    # the bake's own casing, so the match is case-insensitive.
    clip_names = {
        PurePosixPath(relative).stem.lower() for relative in wanted if relative.startswith(CLIP_DIR)
    }
    wanted += [
        f"{DMX_DIR}/{path.name}"
        for path in sorted((content / DMX_DIR).glob("*.dmx"))
        if path.stem.lower() in clip_names
    ]
    missing = [
        relative
        for relative in wanted
        if not (addon / relative).is_file() and not (content / relative).is_file()
    ]
    if missing:
        raise clipbake.ClipError(f"pack-input-missing: {len(missing)} files, first {missing[0]}")
    files = {
        relative: (addon / relative).read_bytes() if (addon / relative).is_file() else (content / relative).read_bytes()
        for relative in wanted
    }
    destination = write_vpk(files, Path(args.out) / f"{args.name}_dir.vpk")
    from forge.oldmods import read_vpk

    tree = read_vpk(destination)
    read_back = {entry.path for entry in tree.entries}
    report = {
        "vpk": str(destination),
        "bytes": destination.stat().st_size,
        "files": len(files),
        "tree_entries": len(tree.entries),
        "version": tree.version,
        "missing_after_read": sorted(set(files) - read_back),
        "extra_after_read": sorted(read_back - set(files)),
        "clips": len([path for path in files if path.startswith(CLIP_DIR)]),
        "dmx": len([path for path in files if path.startswith(DMX_DIR)]),
        "has_scout_variation": "animgraphs/hero_aim_scout.vnmgraph+scout.vnmgraph_c" in read_back,
        "has_skeleton": "models/heroes_wip/frank/frank.vnmskel_c" in read_back,
        "total_payload": sum(len(payload) for payload in files.values()),
    }
    _write(Path(args.report), report)
    print(
        f"PACKED {report['files']} files ({report['total_payload']} bytes) -> {destination} "
        f"{report['bytes']} bytes, tree {report['tree_entries']} entries"
    )
    print(
        f"  scout variation {report['has_scout_variation']}, skeleton {report['has_skeleton']}, "
        f"clips {report['clips']}, dmx {report['dmx']}"
    )
    if report["missing_after_read"] or report["extra_after_read"]:
        raise clipbake.ClipError(f"pack-readback-mismatch: {report['missing_after_read']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="read what the two graphs ask for")
    plan.add_argument("--workspace", required=True)
    plan.add_argument("--loco-graph", required=True)
    plan.add_argument("--aim-graph", required=True)
    plan.add_argument("--out", required=True)
    plan.set_defaults(func=cmd_plan)

    bake = sub.add_parser("bake", help="write one animation DMX and clip document per reference")
    bake.add_argument("--plan", required=True)
    bake.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    bake.add_argument("--workspace", required=True)
    bake.add_argument("--out", required=True, help="directory for the DMX files")
    bake.add_argument("--clips-out", required=True, help="directory for the .vnmclip documents")
    bake.add_argument("--report", required=True)
    bake.add_argument("--compile", action="store_true")
    bake.add_argument("--csdk", default="")
    bake.add_argument("--graphs", nargs="*", default=[])
    bake.add_argument(
        "--skeleton-source",
        default=str(
            ROOT / "artifacts" / "scout-update" / "skel" / "models" / "heroes_wip" / "frank" / "frank.vnmskel"
        ),
        help="the decompiled frank.vnmskel beside dmx/mesh/frank_skel.dmx",
    )
    bake.set_defaults(func=cmd_bake)

    pack = sub.add_parser("pack", help="pack the compiled graph, skeleton and clips into an addon VPK")
    pack.add_argument("--addon-root", required=True, help="<csdk>/game/citadel_addons/scout_animgraph")
    pack.add_argument("--content-root", default="", help="addon content root holding the animation DMX")
    pack.add_argument("--out", required=True, help="directory for the VPK")
    pack.add_argument("--name", default="scout_animgraph")
    pack.add_argument("--report", required=True)
    pack.set_defaults(func=cmd_pack)

    verify = sub.add_parser("verify", help="read the written clips back")
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--out", required=True)
    verify.add_argument("--report", required=True)
    verify.add_argument("--csdk", default="")
    verify.add_argument("--from-content", action="store_true")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    try:
        return args.func(args)
    except clipbake.ClipError as error:
        print(f"REFUSED {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
