"""Measure whether Scout's baked clips carry motion, from both ends: compiled document and source.

For every channel in a compiled clip's decompiled animation DMX this records how many samples it has,
how many distinct values (with a tolerance), and how far the values spread across the clip. The same is
measured on the sequence's source SMD — the animation data the port's model carries — per bone
orientation (angle between Euler poses) and per bone translation.

A clip passes when every orientation channel that moves in the source also moves in the compiled
document, no clip has fewer samples than its source sequence has frames, and no translation the source
carries is lost. The result is written per clip and merged into `artifacts/scout-anim/parsed/<clip>.json`
so the app's clip state keeps reading the parsed files.

Beside the SMD's frame count each result carries the frame count the model itself declares for the same
sequence (`forge.mdlseq`), so 21/20/1/1 is a number read out of `scout_animations.mdl`'s descriptors and
not only out of the decompiled SMD. A clip whose declared frame count disagrees with the SMD, or whose
single-pose declaration disagrees with the measured one, fails.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from forge import clipbake, mdlseq  # noqa: E402
from forge.meshbuild import Element, parse_dmx  # noqa: E402

PARSED = ROOT / "artifacts" / "scout-anim" / "parsed"
OUT = ROOT / "artifacts" / "scout-anim" / "variance"
BAKE_RECEIPT = ROOT / "artifacts" / "receipts" / "scout-own-clips.json"
MDL_BASE = Path("F:/Documents/scout.mdl")
MDL_ANIMS = Path("F:/Documents/scout_animations.mdl")
ORIENTATION_MOVE_DEG = 0.1
TRANSLATION_MOVE = 0.01
ORIENTATION_TOLERANCE = 1e-4
TRANSLATION_TOLERANCE = 1e-4


def _resolve(element: Element, key: str) -> Element | None:
    value = element.attrs.get(key)
    if isinstance(value, Element):
        return value
    if isinstance(value, str):
        return (element.attrs.get("_registry") or {}).get(value)
    return None


def _layer(log: Element) -> tuple[list[float], list[tuple[float, ...]]] | None:
    found = []

    def walk(element: Element) -> None:
        times = element.attrs.get("times")
        values = element.attrs.get("values")
        if isinstance(times, list) and isinstance(values, list):
            found.append((times, values))

    def visit(element: Element) -> None:
        walk(element)
        for value in element.attrs.values():
            if isinstance(value, Element):
                visit(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Element):
                        visit(item)

    visit(log)
    return found[0] if found else None


def read_channels(kv2: Path) -> list[dict]:
    """Every channel in a decompiled clip, with its samples and values."""
    root = parse_dmx(Path(kv2).read_text(encoding="utf-8", errors="replace"))
    channels = []
    for element in (root.attrs.get("_registry") or {}).values():
        if element.klass != "DmeChannel":
            continue
        log = _resolve(element, "log")
        data = _layer(log) if log is not None else None
        if data is None:
            continue
        times, values = data
        name = element.name
        channels.append(
            {
                "name": name,
                "joint": name[:-2] if name.endswith(("_p", "_o")) else name,
                "suffix": name[-2:] if name.endswith(("_p", "_o")) else "",
                "times": times,
                "values": values,
            }
        )
    return channels


def _quat_angle(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return math.degrees(2.0 * math.acos(min(1.0, abs(dot))))


def _unique(values: list[tuple[float, ...]], tolerance: float) -> int:
    seen = set()
    for row in values:
        seen.add(tuple(round(part / tolerance) for part in row))
    return len(seen)


def stats(channel: dict) -> dict:
    values = [tuple(row) for row in channel["values"]]
    kind = "orientation" if channel["suffix"] == "_o" else "position"
    tolerance = ORIENTATION_TOLERANCE if kind == "orientation" else TRANSLATION_TOLERANCE
    if kind == "orientation":
        spread = max((_quat_angle(values[0], row) for row in values), default=0.0)
        threshold = ORIENTATION_MOVE_DEG
        unit = "deg"
    else:
        spread = max((math.dist(values[0], row) for row in values), default=0.0)
        threshold = TRANSLATION_MOVE
        unit = "units"
    return {
        "samples": len(values),
        "distinct": _unique(values, tolerance),
        "spread": round(spread, 6),
        "unit": unit,
        "moving": spread > threshold,
        "tolerance": tolerance,
    }


def _node_motion(frames: list[dict], node: int) -> tuple[float, float]:
    """Largest orientation angle (degrees) and translation distance across a bone's frames."""
    poses = [frame[node] for frame in frames if node in frame]
    if len(poses) < 2:
        return 0.0, 0.0
    quats = [clipbake.euler_to_quat(*pose[1]) for pose in poses]
    angle = max(_quat_angle(quats[0], quat) for quat in quats)
    distance = max(math.dist(poses[0][0], pose[0]) for pose in poses[1:])
    return angle, distance


def _md5(path: Path) -> str:
    import hashlib

    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _to_kv2(source: Path, target: Path) -> bool:
    """The same conversion the port uses everywhere: binary DMX to keyvalues2, with dmxconvert."""
    converter = ROOT / "artifacts" / "dota-tools" / "game" / "bin" / "win64" / "dmxconvert.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(converter), "-i", str(source), "-o", str(target), "-oe", "keyvalues2"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    return result.returncode == 0 and target.is_file()


def mdl_anchor(sequence: str) -> dict:
    """The frame count the model's own sequence descriptor declares, beside the SMD's length.

    `scout.mdl` names the sequence but declares no blends for it; the animation descriptors and the
    frame counts are in `scout_animations.mdl`, the companion model Crowbar decompiled into the QC and
    SMDs this port baked. Both files are read so a reader can see which one carries the number.
    """
    if not (MDL_BASE.is_file() and MDL_ANIMS.is_file()):
        return {"available": False, "reason": "model-file-absent", "model": str(MDL_ANIMS)}
    carrier = mdlseq.load(MDL_ANIMS)
    found = carrier.find(sequence)
    if found is None:
        return {"available": False, "reason": "sequence-not-in-descriptors", "model": str(carrier.path)}
    base = mdlseq.load(MDL_BASE)
    base_found = base.find(sequence)
    return {
        "available": True,
        "model": str(carrier.path),
        "model_bytes": carrier.size,
        "model_md5": carrier.md5,
        **mdlseq.describe(found),
        "base_model": {
            "path": str(base.path),
            "descriptor": base_found.descriptor if base_found else None,
            "flags": base_found.flags if base_found else None,
            "numblends": base_found.numblends if base_found else None,
            "declared_frames": base_found.declared_frames if base_found else 0,
            "note": "names the sequence only; the animations companion carries the data",
        },
    }


def measure(clip: str, smd: Path) -> dict:
    parsed = json.loads((PARSED / f"{clip}.json").read_text(encoding="utf-8"))
    # The compiled `vnmclip_c` is a 4 KB document that stores a checksummed reference to its animation
    # DMX, not the samples: changing one value in the DMX moves four bytes of the compiled clip. So the
    # animation document to measure is the one the clip document names, parsed back through dmxconvert.
    source_dmx = ROOT / "artifacts" / "scout-own-clips" / "dmx" / f"{parsed['source_sequence']}.dmx"
    kv2 = OUT / "scratch" / f"{clip}.authored.kv2.dmx"
    converted = _to_kv2(source_dmx, kv2) if source_dmx.is_file() else False
    channels = read_channels(kv2) if converted else []
    document = ROOT / "artifacts" / "scout-anim" / "clips" / f"{clip}.vnmclip"
    reference = ""
    if document.is_file():
        found = re.search(r'm_sourceFilename = "([^"]+)"', document.read_text(encoding="utf-8", errors="replace"))
        reference = found.group(1) if found else ""
    # The compiler resolves the referenced DMX from the addon's content root, so that is where a
    # rebake has to match; the game-root copy is staging for a pack, not what was compiled.
    addon_root = Path("C:/Users/ala/Downloads/Reduced_CSDK_13/content/citadel_addons/scout_port")
    referenced = addon_root / reference if reference else None
    compiled = Path(parsed.get("compiled", ""))
    source = clipbake.parse_smd(smd)
    source_motion = {node.name: _node_motion(source.frames, node.index) for node in source.nodes}
    rows = []
    flat_where_source_moves = []
    moved = 0
    for channel in channels:
        row = {"name": channel["name"], "joint": channel["joint"], **stats(channel)}
        source_angle, source_distance = source_motion.get(channel["joint"], (0.0, 0.0))
        if channel["suffix"] == "_o":
            row["source_spread"] = round(source_angle, 4)
            row["source_moving"] = source_angle > ORIENTATION_MOVE_DEG
            if row["source_moving"] and not row["moving"]:
                flat_where_source_moves.append(channel["joint"])
        else:
            row["source_spread"] = round(source_distance, 6)
            row["source_moving"] = source_distance > TRANSLATION_MOVE
            if row["source_moving"] and not row["moving"]:
                flat_where_source_moves.append(channel["joint"])
        moved += 1 if row["moving"] else 0
        rows.append(row)
    orientation = [row for row in rows if row["name"].endswith("_o")]
    positions = [row for row in rows if row["name"].endswith("_p")]
    moving_source = sorted(joint for joint, (angle, _) in source_motion.items() if angle > ORIENTATION_MOVE_DEG)
    translating_source = sorted(joint for joint, (_, distance) in source_motion.items() if distance > TRANSLATION_MOVE)
    samples = sorted({row["samples"] for row in rows})
    result = {
        "clip": clip,
        "kv2": str(kv2) if converted else "",
        "source_dmx": str(source_dmx),
        "source_dmx_bytes": source_dmx.stat().st_size if source_dmx.is_file() else 0,
        "source_dmx_md5": _md5(source_dmx) if source_dmx.is_file() else "",
        "document": str(document) if document.is_file() else "",
        "document_reference": reference,
        "reference_present": bool(referenced and referenced.is_file()),
        "reference_matches_bake": bool(referenced and referenced.is_file() and source_dmx.is_file() and _md5(referenced) == _md5(source_dmx)),
        "compiled": str(compiled) if compiled.is_file() else "",
        "compiled_bytes": compiled.stat().st_size if compiled.is_file() else 0,
        "compiled_md5": _md5(compiled) if compiled.is_file() else "",
        "source_smd": str(smd),
        "source_frames": len(source.frames),
        "source_nodes": len(source.nodes),
        "compiled_samples": samples[0] if len(samples) == 1 else samples,
        "channels": len(rows),
        "orientation_channels": len(orientation),
        "position_channels": len(positions),
        "moving_channels": moved,
        "moving_orientation_channels": sum(1 for row in orientation if row["moving"]),
        "moving_position_channels": sum(1 for row in positions if row["moving"]),
        "source_moving_joints": moving_source,
        "source_translating_joints": translating_source,
        "flat_where_source_moves": sorted(set(flat_where_source_moves)),
        "missing_source_joints": sorted(set(row["joint"] for row in rows) - set(source_motion)),
        "unmapped_source_joints": sorted(set(source_motion) - set(row["joint"] for row in rows)),
        "single_pose_source": len(source.frames) <= 1,
        "mdl": mdl_anchor(parsed["source_sequence"]),
        "channels_rows": rows,
    }
    result["mdl"]["matches_source_frames"] = result["mdl"].get("declared_frames") == len(source.frames)
    result["mdl"]["single_pose_agrees"] = result["mdl"].get("single_pose") == result["single_pose_source"]
    result["truncated"] = (
        isinstance(result["compiled_samples"], int)
        and result["source_frames"] > 1
        and result["compiled_samples"] < result["source_frames"]
    )
    result["ok"] = (
        converted
        and result["reference_present"]
        and result["reference_matches_bake"]
        and not result["flat_where_source_moves"]
        and not result["truncated"]
        and not result["unmapped_source_joints"]
        and (result["single_pose_source"] or result["moving_orientation_channels"] > 0)
        and (
            not result["mdl"].get("available")
            or (result["mdl"]["matches_source_frames"] and result["mdl"]["single_pose_agrees"])
        )
    )
    return result


def _merge_receipt(results: list[dict]) -> None:
    """Put the measured variance beside the parse it belongs to, so one receipt answers both."""
    receipt_path = ROOT / "artifacts" / "receipts" / "scout-anim.json"
    if not receipt_path.is_file():
        return
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["variance"] = {
        "measured": [result["clip"] for result in results],
        "all_ok": all(result["ok"] for result in results),
        "source_model": {
            "path": results[0]["mdl"].get("model", str(MDL_ANIMS)) if results else str(MDL_ANIMS),
            "bytes": results[0]["mdl"].get("model_bytes", 0) if results else 0,
            "md5": results[0]["mdl"].get("model_md5", "") if results else "",
            "base": str(MDL_BASE),
        },
        "clips": {
            result["clip"]: {
                "source_frames": result["source_frames"],
                "mdl_declared_frames": result["mdl"].get("declared_frames"),
                "mdl_activity": result["mdl"].get("activity", ""),
                "mdl_single_pose": result["mdl"].get("single_pose"),
                "mdl_anims": result["mdl"].get("anims", []),
                "compiled_samples": result["compiled_samples"],
                "orientation_channels": result["orientation_channels"],
                "moving_orientation_channels": result["moving_orientation_channels"],
                "moving_position_channels": result["moving_position_channels"],
                "source_moving_joints": result["source_moving_joints"],
                "source_translating_joints": result["source_translating_joints"],
                "single_pose_source": result["single_pose_source"],
                "flat_where_source_moves": result["flat_where_source_moves"],
                "truncated": result["truncated"],
                "source_dmx_md5": result["source_dmx_md5"],
                "compiled_md5": result["compiled_md5"],
                "ok": result["ok"],
            }
            for result in results
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def _bake_sources() -> dict[str, str]:
    receipt = json.loads(BAKE_RECEIPT.read_text(encoding="utf-8"))
    return {row["name"]: row["smd"] for row in receipt.get("clips") or []}


def _merge_parsed(result: dict) -> None:
    row = json.loads((PARSED / f"{result['clip']}.json").read_text(encoding="utf-8"))
    row["variance"] = {
        "path": str(OUT / f"{result['clip']}.json"),
        "source_frames": result["source_frames"],
        "mdl_frames": result["mdl"].get("declared_frames"),
        "mdl_activity": result["mdl"].get("activity", ""),
        "mdl_model": result["mdl"].get("model", ""),
        "mdl_single_pose": result["mdl"].get("single_pose"),
        "source_dmx_bytes": result["source_dmx_bytes"],
        "compiled_samples": result["compiled_samples"],
        "moving_orientation_channels": result["moving_orientation_channels"],
        "moving_position_channels": result["moving_position_channels"],
        "source_moving_joints": len(result["source_moving_joints"]),
        "source_translating_joints": len(result["source_translating_joints"]),
        "flat_where_source_moves": result["flat_where_source_moves"],
        "single_pose_source": result["single_pose_source"],
        "truncated": result["truncated"],
        "ok": result["ok"],
    }
    (PARSED / f"{result['clip']}.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - one pass, four clips
    parser = argparse.ArgumentParser(description="Measure per-channel motion in Scout's baked clips.")
    parser.add_argument("--clip", action="append", help="clip to measure (default: all four)")
    parser.add_argument("--write", action="store_true", help="write the variance files")
    args = parser.parse_args(argv)
    smds = _bake_sources()
    names = args.clip or ["Scout_Attack", "Scout_Reload", "Scout_AimIdle", "Scout_AimRun"]
    results = []
    for name in names:
        parsed = json.loads((PARSED / f"{name}.json").read_text(encoding="utf-8"))
        result = measure(name, Path(smds[parsed["source_sequence"]]))
        results.append(result)
        print(
            f"{name:<14} mdl {result['mdl'].get('declared_frames', '?'):>2} frames / smd {result['source_frames']:>2} frames -> {result['compiled_samples']} samples, "
            f"{result['moving_orientation_channels']}/{result['orientation_channels']} orientation channels move, "
            f"{result['moving_position_channels']}/{result['position_channels']} position channels move, "
            f"flat-where-source-moves {len(result['flat_where_source_moves'])}, ok={result['ok']}"
        )
        if result["flat_where_source_moves"]:
            print(f"  flat joints: {result['flat_where_source_moves'][:8]}")
        if args.write:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            _merge_parsed(result)
    if args.write:
        _merge_receipt(results)
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
