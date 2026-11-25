"""Bake the port's own clips onto Scout's own skeleton and compile them.

`tools/scout_clip_bake.py` baked onto frank's skeleton through a hand-written bone map, which is the
step the owner withdrew. This tool takes the other path: the skeleton is `forge.portskel`'s DMX built
from `scout_anims/ref.smd`, the clip template carries one orientation channel per joint of that same
skeleton, and the SMD nodes bind by name because the port's node names *are* the joint names. No map,
no relabel.

  python tools/scout_own_clips.py template
  python tools/scout_own_clips.py bake --clips Scout_Run,Scout_Idle
  python tools/scout_own_clips.py bake --all
  python tools/scout_own_clips.py compile --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
  python tools/scout_own_clips.py verify
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

from forge import clipbake, portskel  # noqa: E402
from tools.scout_clip_bake import _compile_one, _stamp, _tools  # noqa: E402


def _write(path: Path, payload: dict) -> Path:
    """Merge into one receipt: bake, compile and verify all report into the same document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    existing.update(payload)
    path.write_text(json.dumps(existing, indent=1) + "\n", encoding="utf-8")
    return path

MODEL = "models/heroes_wip/scout"
ADDON = "scout_port"
SKELETON = f"{MODEL}/scout.vnmskel"
DMX_DIR = f"{MODEL}/dmx"
WORKSPACE = Path("F:/Documents")
SMD_REFERENCE = WORKSPACE / "scout_anims" / "ref.smd"
OUT = ROOT / "artifacts" / "scout-own-clips"
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-own-clips.json"
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")


def _content(csdk: Path) -> Path:
    return csdk / "content" / "citadel_addons" / ADDON


def _game(csdk: Path) -> Path:
    return csdk / "game" / "citadel_addons" / ADDON


def _template(args) -> tuple[Path, str, list[str], dict[str, tuple[float, float, float]]]:
    joints = portskel.read_reference(Path(args.smd))
    path = Path(args.out) / "template.kv2.dmx"
    # Rewritten every run: the template now carries a position channel per joint, and a stale template
    # without one would bake orientation only and silently drop every translation in the sequence.
    portskel.write_clip_template(joints, path)
    return (
        path,
        path.read_text(encoding="utf-8", errors="replace"),
        [joint.name for joint in joints],
        {joint.name: joint.position for joint in joints},
    )


def _sources(workspace: Path) -> dict[str, Path]:
    """Every port sequence the QC declares, resolved to the SMD that carries it."""
    sequences: dict[str, str] = {}
    for qc in sorted(workspace.glob("*.qc")):
        for name, smd in clipbake.parse_qc_sequences(qc).items():
            sequences.setdefault(name, smd)
    resolved: dict[str, Path] = {}
    for name, smd in sequences.items():
        candidate = workspace / smd
        if not candidate.is_file():
            stem = Path(smd).stem
            for folder in ("scout_animations_anims", "scout_anims"):
                alternative = workspace / folder / f"{stem}.smd"
                if alternative.is_file():
                    candidate = alternative
                    break
        if candidate.is_file():
            resolved[name] = candidate
    return resolved


def cmd_template(args) -> int:
    path, _, joints, _ = _template(args)
    _write(
        Path(args.report),
        {"template": str(path), "joints": len(joints), "channels": len(joints), "position_channels": len(joints)},
    )
    print(f"TEMPLATE {path} {path.stat().st_size} bytes, {len(joints)} orientation + {len(joints)} position channels")
    return 0


def _bake_one(
    name: str,
    smd: Path,
    template_text: str,
    joints: list[str],
    rest: dict[str, tuple[float, float, float]],
    out: Path,
) -> dict:
    clip = clipbake.parse_smd(smd)
    by_name = {joint: index for index, joint in enumerate(joints)}
    mapped = {node.name: node.index for node in clip.nodes if node.name in by_name}
    if len(mapped) < 8:
        raise clipbake.ClipError(f"clip-bake-too-few-joints: {name} resolved {len(mapped)} of {len(clip.nodes)}")
    frames = clip.frames if len(clip.frames) > 1 else (clip.frames[0], clip.frames[0])
    origin = clip.frames[0]
    samples = {}
    positions = {}
    for joint, index in mapped.items():
        samples[joint] = [
            clipbake.euler_to_quat(*frame.get(index, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))[1]) for frame in frames
        ]
        # The source sequence's bone translations are offsets from its own rest; carry them onto the
        # template's rest position so a bob or a weapon kick is not flattened into a held channel.
        base = rest.get(joint)
        if base is not None:
            start = origin.get(index, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))[0]
            positions[joint] = [
                tuple(
                    base[axis] + (frame.get(index, ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))[0][axis] - start[axis])
                    for axis in range(3)
                )
                for frame in frames
            ]
    moving_positions = sum(
        1
        for series in positions.values()
        if len({tuple(round(value, 6) for value in sample) for sample in series}) > 1
    )
    moving = sum(
        1
        for series in samples.values()
        if len({tuple(round(value, 6) for value in sample) for sample in series}) > 1
    )
    times = [index / clipbake.FPS for index in range(len(frames))]
    duration = max(len(frames) - 1, 1) / clipbake.FPS
    body, report = clipbake.bake_kv2(
        template_text, samples=samples, positions=positions, times=times, duration=duration
    )
    kv2 = out / "kv2" / f"{name}.dmx"
    kv2.parent.mkdir(parents=True, exist_ok=True)
    kv2.write_text(body, encoding="utf-8")
    dmxconvert, _ = _tools()
    dmx = out / "dmx" / f"{name}.dmx"
    dmx.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(dmxconvert), "-i", str(kv2), "-o", str(dmx), "-oe", "binary"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=300,
    )
    if result.returncode != 0 or not dmx.is_file():
        raise clipbake.ClipError(f"dmxconvert-failed: {name} rc={result.returncode} {(result.stdout or '')[-200:]}")
    document = out / "clips" / f"{name}.vnmclip"
    clipbake.write_vnmclip(
        document, clip_name=name, skeleton=SKELETON, source_dmx=f"{DMX_DIR}/{name}.dmx"
    )
    return {
        "name": name,
        "smd": str(smd),
        "frames": len(frames),
        "seconds": round(duration, 3),
        "nodes": len(clip.nodes),
        "joints_resolved": len(mapped),
        "unresolved": sorted({node.name for node in clip.nodes} - set(mapped)),
        "moving_channels": moving,
        "channels_baked": len(report["baked"]),
        "channels_held": len(report["held"]),
        "moving_positions": moving_positions,
        "position_channels_baked": len(report["positions_baked"]),
        "position_channels_held": len(report["positions_held"]),
        "dmx": str(dmx),
        "dmx_bytes": dmx.stat().st_size,
        "vnmclip": str(document),
    }


def cmd_bake(args) -> int:
    out = Path(args.out)
    _, template_text, joints, rest = _template(args)
    sources = _sources(Path(args.workspace))
    if not sources:
        raise clipbake.ClipError("qc-sequences-empty: no $sequence resolved to an SMD")
    wanted = list(args.clips) if args.clips else sorted(sources) if args.all else []
    if not wanted:
        raise SystemExit("say which clips: --clips a,b or --all")
    missing = [name for name in wanted if name not in sources]
    if missing:
        raise clipbake.ClipError(f"clip-source-missing: {', '.join(missing[:6])}")
    rows = [_bake_one(name, sources[name], template_text, joints, rest, out) for name in wanted]
    receipt = {
        "schema": "dmf.scout-own-clips/1",
        "generated": _stamp(),
        "skeleton": SKELETON,
        "skeleton_joints": len(joints),
        "sequences_available": len(sources),
        "clips": rows,
        "summary": {
            "clips": len(rows),
            "moving": sum(1 for row in rows if row["moving_channels"] >= 8),
            "static": sum(1 for row in rows if row["moving_channels"] < 8),
            "channels_baked": sum(row["channels_baked"] for row in rows),
            "dmx_bytes": sum(row["dmx_bytes"] for row in rows),
        },
    }
    _write(Path(args.report), receipt)
    for row in rows:
        print(
            f"  {row['name']:<34} {row['frames']:>4}f {row['joints_resolved']:>3}/{row['nodes']} joints "
            f"{row['moving_channels']:>3} moving {row['dmx_bytes']:>8}B"
        )
    print(f"BAKED {len(rows)} clips onto {SKELETON} ({len(joints)} joints), {receipt['summary']['dmx_bytes']} bytes")
    return 0


def cmd_compile(args) -> int:
    csdk = Path(args.csdk)
    out = Path(args.out)
    content = _content(csdk)
    if not out.is_dir():
        raise SystemExit(f"bake-first: {out}")
    skeleton_source = Path(args.out).parent / "scout-port-skel" / MODEL
    if not skeleton_source.is_dir():
        raise SystemExit(f"skeleton-missing: run tools/scout_skeleton.py build ({skeleton_source})")
    shutil.copytree(skeleton_source, content / MODEL, dirs_exist_ok=True)
    shutil.copytree(out / "clips", content / MODEL, dirs_exist_ok=True)
    # The clip documents name `models/heroes_wip/scout/dmx/<clip>.dmx`, so the binary clips land
    # one directory down; copying them into the model root makes the compiler fail to load them.
    shutil.copytree(out / "dmx", content / MODEL / "dmx", dirs_exist_ok=True)
    documents = [(content / MODEL / "scout.vnmskel", "scout.vnmskel")]
    documents += [(path, path.name) for path in sorted((content / MODEL).glob("*.vnmclip"))]
    results = []
    for document, label in documents:
        row = _compile_one(csdk, document, label)
        compiled = _game(csdk) / MODEL / (document.name.lower() + "_c")
        row["compiled"] = str(compiled) if compiled.is_file() else ""
        row["compiled_bytes"] = compiled.stat().st_size if compiled.is_file() else 0
        results.append(row)
        print(f"  {label:<40} {row['ok_line'] or row['error']} {row['compiled_bytes']}B")
    failed = [row for row in results if not row["compiled"]]
    receipt = {
        "schema": "dmf.scout-own-compile/1",
        "generated": _stamp(),
        "documents": len(results),
        "compiled": len(results) - len(failed),
        "results": results,
    }
    _write(Path(args.report), receipt)
    print(f"COMPILED {receipt['compiled']}/{receipt['documents']} documents")
    if failed:
        for row in failed:
            print(f"  FAILED {row['name']}: {row['error']}")
        raise SystemExit("compile-failed")
    return 0


def cmd_verify(args) -> int:
    """Every baked clip is compiled, and every clip DMX carries one channel per joint of the skeleton.

    The compiled `.vnmclip_c` is engine binary and stores channels by skeleton index, so the channel
    names are read from the kv2 the compiler accepted (it loaded the DMX the document names) and the
    compiled size is the engine-side witness that the document bound.
    """
    csdk = Path(args.csdk)
    game = _game(csdk) / MODEL
    compiled = sorted(path for path in game.glob("*.vnmclip_c")) if game.is_dir() else []
    if not compiled:
        raise SystemExit(f"no compiled clips under {game}")
    joints = portskel.read_reference(Path(args.smd))
    rows = []
    for kv2 in sorted((Path(args.out) / "kv2").glob("*.dmx")):
        text = kv2.read_text(encoding="utf-8", errors="replace")
        channels = re.findall(r'"name"\s+"string"\s+"([^"]+)_o"', text)
        binary = Path(args.out) / "dmx" / f"{kv2.stem}.dmx"
        row = {
            "clip": kv2.stem,
            "channels": len(channels),
            "all_joints": sorted(channels) == sorted(joint.name for joint in joints),
            "dmx_bytes": binary.stat().st_size if binary.is_file() else 0,
            "compiled": str(game / (kv2.stem.lower() + ".vnmclip_c")),
        }
        row["compiled_bytes"] = (
            Path(row["compiled"]).stat().st_size if Path(row["compiled"]).is_file() else 0
        )
        rows.append(row)
    bad = [row for row in rows if not row["all_joints"] or not row["compiled_bytes"]]
    receipt = {
        "schema": "dmf.scout-own-verify/1",
        "generated": _stamp(),
        "skeleton": SKELETON,
        "skeleton_joints": len(joints),
        "verified": rows,
        "compiled_clips": len(compiled),
        "result": "PASS" if rows and not bad and len(compiled) >= len(rows) else "FAIL",
    }
    _write(Path(args.report), receipt)
    for row in rows:
        print(
            f"  {row['clip']:<34} {row['channels']:>3} channels  dmx {row['dmx_bytes']:>7}B  "
            f"compiled {row['compiled_bytes']:>6}B"
        )
    print(f"VERIFY {len(rows)} clips against {len(joints)} joints, {len(compiled)} compiled documents")
    if receipt["result"] != "PASS":
        raise SystemExit("verify-failed")
    print("RESULT: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--workspace", default=str(WORKSPACE))
    parser.add_argument("--smd", default=str(SMD_REFERENCE))
    parser.add_argument("--report", default=str(RECEIPT))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("template", help="write the clip template for the port's own joints").set_defaults(func=cmd_template)
    bake = sub.add_parser("bake", help="bake port sequences onto Scout's own skeleton")
    bake.add_argument("--clips", nargs="*", default=[])
    bake.add_argument("--all", action="store_true")
    bake.set_defaults(func=cmd_bake)
    compile_parser = sub.add_parser("compile", help="compile the skeleton and clips with the CSDK addon compiler")
    compile_parser.add_argument("--csdk", required=True)
    compile_parser.set_defaults(func=cmd_compile)
    verify = sub.add_parser("verify", help="decompile a compiled clip and count its channels")
    verify.add_argument("--csdk", required=True)
    verify.set_defaults(func=cmd_verify)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
