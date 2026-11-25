"""Bake TF2 SMD clips onto a Source 2 skeleton as animation DMX (keyvalues2 text).

The scout port is animation only: its SMDs are authored on a 76-bone TF2 rig (`bip_pelvis`,
`bip_upperArm_L`, `bip_thumb_0_R`, …) and the hero slot it replaces is frank, whose skeleton is
107 joints (`pelvis`, `spine_0..3`, `clavicle_L`, `arm_upper_L`, `leg_lower_R`, `ball_L`, …).
Nothing shares an index, so a clip is bound **by name**; a node with no name in the skeleton is
reported and left holding its rest pose rather than written onto the wrong joint.

Why the output is keyvalues2 text: the toolchain that ships with the games (`dmxconvert.exe`)
converts keyvalues2 to binary DMX, and the DMX reader this repo has (PulseSrcOps'
``datamodel``) is a reader with no writer. Writing the text and converting it with Valve's own
converter is the only path here that does not invent a file format.

Conventions, stated so a later reader can disagree with them precisely:

* SMD bone rotations are Euler angles in radians, applied X then Y then Z (``R = Rz·Ry·Rx``);
  the quaternion is built in that order.
* SMD positions are Source units and the DMX is in metres. Positions are **not** copied: the
  two rigs have different bone lengths, and the clip keeps the slot's own translation channels.
* Rotations are local, as both formats store them, so they are copied joint-local.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

FPS = 30.0

# Which Scout sequence feeds which Dota-branch locomotion slot. Scout has no direction-split
# locomotion and no turn-in-place clips: it has aim matrices. Each slot therefore names the clip
# that carries the nearest real motion, and the count of reuses is reported instead of inventing
# 24 distinct animations.
SLOT_SOURCES = {
    "idle": "PRIMARY_aimmatrix_idle",
    "walkn": "PRIMARY_aimmatrix_run",
    "walke": "PRIMARY_aimmatrix_run",
    "walks": "PRIMARY_aimmatrix_run",
    "walkw": "PRIMARY_aimmatrix_run",
    "walkne": "PRIMARY_aimmatrix_run",
    "walknw": "PRIMARY_aimmatrix_run",
    "walkse": "PRIMARY_aimmatrix_run",
    "walksw": "PRIMARY_aimmatrix_run",
    "crouch_runn": "PRIMARY_aimmatrix_run",
    "crouch_walkn": "PRIMARY_aimmatrix_crouch_idle",
    "crouch_walke": "PRIMARY_aimmatrix_crouch_idle",
    "crouch_walks": "PRIMARY_aimmatrix_crouch_idle",
    "crouch_walkw": "PRIMARY_aimmatrix_crouch_idle",
    "crouch_walkne": "PRIMARY_aimmatrix_crouch_idle",
    "crouch_walknw": "PRIMARY_aimmatrix_crouch_idle",
    "crouch_walkse": "PRIMARY_aimmatrix_crouch_idle",
    "crouch_walksw": "PRIMARY_aimmatrix_crouch_idle",
    "turn_left_45": "PRIMARY_aimmatrix_run",
    "turn_left_90": "PRIMARY_aimmatrix_run",
    "turn_left_180": "PRIMARY_aimmatrix_run",
    "turn_right_45": "PRIMARY_aimmatrix_run",
    "turn_right_90": "PRIMARY_aimmatrix_run",
    "turn_right_180": "PRIMARY_aimmatrix_run",
}

# Which Scout sequence feeds each clip the live aim graph references for Scout. The graph asks for
# standing, run, crouch and slide poses at three aim pitches; Scout ships one sequence per those
# poses, so pitch variants share the source and say so.
AIM_SOURCES = {
    "aim_weapon_idle": "PRIMARY_aimmatrix_idle",
    "aim_weapon_idle_up": "PRIMARY_aimmatrix_idle",
    "aim_weapon_idle_down": "PRIMARY_aimmatrix_idle",
    "aim_weapon_run": "PRIMARY_aimmatrix_run",
    "aim_weapon_run_up": "PRIMARY_aimmatrix_run",
    "aim_weapon_run_down": "PRIMARY_aimmatrix_run",
    "aim_weapon_crouch": "PRIMARY_aimmatrix_crouch_idle",
    "aim_weapon_crouch_up": "PRIMARY_aimmatrix_crouch_idle",
    "aim_weapon_crouch_down": "PRIMARY_aimmatrix_crouch_idle",
    "aim_weapon_slide": "PRIMARY_aimmatrix_crouch_idle",
    "aim_weapon_slide_up": "PRIMARY_aimmatrix_crouch_idle",
    "aim_weapon_slide_down": "PRIMARY_aimmatrix_crouch_idle",
}


class ClipError(Exception):
    """A named refusal: the detail is what a caller has to look at."""


@dataclass(frozen=True)
class SmdNode:
    index: int
    name: str
    parent: int


@dataclass(frozen=True)
class SmdClip:
    path: Path
    nodes: tuple[SmdNode, ...]
    frames: tuple[dict[int, tuple[tuple[float, ...], tuple[float, ...]]], ...]

    @property
    def duration(self) -> float:
        return max(len(self.frames) - 1, 0) / FPS


_QC_SEQUENCE = re.compile(r'^\s*\$sequence\s+"([^"]+)"\s*\{', re.IGNORECASE | re.MULTILINE)
_SMD_PATH = re.compile(r'^\s*"([^"]+\.smd)"', re.IGNORECASE | re.MULTILINE)
_QUOTED = re.compile(r'^\s*"([^"]+)"', re.MULTILINE)
_QC_ANIMATION = re.compile(
    r'^\s*\$animation\s+"([^"]+)"\s+"([^"]+\.smd)"', re.IGNORECASE | re.MULTILINE
)


def parse_smd(path: Path) -> SmdClip:
    """Read one SMD: its node table and every skeleton frame."""
    path = Path(path)
    if not path.is_file():
        raise ClipError(f"smd-missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    nodes: list[SmdNode] = []
    frames: list[dict[int, tuple[tuple[float, ...], tuple[float, ...]]]] = []
    stage = ""
    current: dict[int, tuple[tuple[float, ...], tuple[float, ...]]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line in ("nodes", "skeleton", "triangles") and not line[0].isdigit():
            stage = line
            continue
        if line == "end":
            stage = ""
            continue
        if stage == "nodes":
            match = re.match(r'(-?\d+)\s+"([^"]+)"\s+(-?\d+)', line)
            if match:
                nodes.append(SmdNode(int(match.group(1)), match.group(2), int(match.group(3))))
            continue
        if stage == "skeleton":
            if line.startswith("time "):
                if current:
                    frames.append(current)
                current = {}
                continue
            numbers = line.split()
            if len(numbers) == 7:
                index = int(numbers[0])
                values = [float(value) for value in numbers[1:]]
                current[index] = (tuple(values[:3]), tuple(values[3:]))
    if current:
        frames.append(current)
    if not nodes:
        raise ClipError(f"smd-no-nodes: {path}")
    if not frames:
        raise ClipError(f"smd-no-frames: {path}")
    return SmdClip(path=path, nodes=tuple(nodes), frames=tuple(frames))


def parse_qc_sequences(qc_path: Path) -> dict[str, str]:
    """sequence name -> the SMD it plays, following a sequence composed of other sequences.

    A TF2 aim matrix is not a file: `$sequence "PRIMARY_aimmatrix_idle"` lists other sequences
    (`a_PRIMARY_aimmatrix_idle_straight_up`, …), and each of those finally names an SMD. One hop is
    as common as none, and following it is the difference between "the port has no aim animation"
    and the real SMD.
    """
    qc_path = Path(qc_path)
    if not qc_path.is_file():
        raise ClipError(f"qc-missing: {qc_path}")
    text = qc_path.read_text(encoding="utf-8", errors="replace")
    first_entries: dict[str, str] = {}
    # `$animation` names are the leaves an aim matrix is built from: the matrix sequence lists
    # `a_PRIMARY_aimmatrix_idle_straight_up`, and that name is an `$animation` pointing at an SMD.
    for name, smd in _QC_ANIMATION.findall(text):
        first_entries.setdefault(name, smd.replace("\\", "/"))
    matches = list(_QC_SEQUENCE.finditer(text))
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        block = text[match.end() : end]
        found = _SMD_PATH.search(block)
        if found:
            first_entries.setdefault(match.group(1), found.group(1).replace("\\", "/"))
            continue
        quoted = _QUOTED.search(block)
        if quoted:
            first_entries.setdefault(match.group(1), quoted.group(1))
    resolved: dict[str, str] = {}
    for name in first_entries:
        target = first_entries[name]
        seen = {name}
        while not target.lower().endswith(".smd"):
            if target in seen or target not in first_entries:
                target = ""
                break
            seen.add(target)
            target = first_entries[target]
        if target:
            resolved[name] = target
    return resolved


# --- quaternions (x, y, z, w) -------------------------------------------------------


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def euler_to_quat(rx: float, ry: float, rz: float):
    """SMD Euler radians to a quaternion, in the ``R = Rz·Ry·Rx`` order SMD uses."""
    hx, hy, hz = rx / 2.0, ry / 2.0, rz / 2.0
    qx = (math.sin(hx), 0.0, 0.0, math.cos(hx))
    qy = (0.0, math.sin(hy), 0.0, math.cos(hy))
    qz = (0.0, 0.0, math.sin(hz), math.cos(hz))
    return _qmul(_qmul(qz, qy), qx)


def _format(values) -> str:
    return " ".join(f"{float(value):.6f}" for value in values)


def _find_array(lines: list[str], start: int, key: str) -> tuple[int, int, int]:
    """The array opening after `key`, and its closing line, plus the key line."""
    for index in range(start, len(lines)):
        if lines[index].lstrip().startswith(f'"{key}"'):
            open_at = index
            while open_at < len(lines) and "[" not in lines[open_at]:
                open_at += 1
            depth = 0
            for position in range(open_at, len(lines)):
                depth += lines[position].count("[") - lines[position].count("]")
                if depth == 0:
                    return index, open_at, position
            break
    raise ClipError(f"kv2-array-missing: {key}")


def _rewrite_array(lines: list[str], open_at: int, close_at: int, values: list[str]) -> list[str]:
    """Replace an array's contents.

    keyvalues2 arrays separate their entries with commas and the **last entry has none**: a
    trailing comma makes dmxconvert report `Expecting array attribute value` at the closing
    bracket, which reads like a broken document rather than one extra character.
    """
    pad = lines[open_at][: len(lines[open_at]) - len(lines[open_at].lstrip())] + "\t"
    body = [f"{pad}{value},\n" for value in values]
    if body:
        body[-1] = body[-1].rstrip(",\n") + "\n"
    return lines[: open_at + 1] + body + lines[close_at:]


_CHANNEL_SPLIT = re.compile(r'^\s*"DmeChannel"\s*$')


def _channel_blocks(lines: list[str]) -> list[tuple[int, int]]:
    starts = [index for index, line in enumerate(lines) if _CHANNEL_SPLIT.match(line)]
    blocks = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        blocks.append((start, end))
    return blocks


def bake_kv2(
    template_text: str,
    *,
    samples: dict[str, list[tuple[float, float, float, float]]],
    times: list[float],
    duration: float,
    positions: dict[str, list[tuple[float, float, float]]] | None = None,
    hold: dict[str, str] | None = None,
) -> tuple[str, dict]:
    """Replace a clip's channel samples with `samples` (orientation) and `positions` by joint name.

    ``samples[joint]`` is the joint's local orientation per frame, ``positions[joint]`` its local
    position per frame. A channel whose joint was not baked keeps its first template value for every
    frame, so the clip is uniform in length and the report says which joints hold. A joint whose
    source sequence translates must have positions written; otherwise its translation is lost.
    """
    lines = template_text.splitlines(keepends=True)
    report = {
        "channels": 0,
        "baked": [],
        "held": [],
        "missing_channels": [],
        "position_channels": 0,
        "positions_baked": [],
        "positions_held": [],
    }
    positions = positions or {}
    # keyvalues2 writes every vector and time as a quoted token: `"0.0000",` and
    # `"0 0 0 1",`. Dropping the quotes produces a file dmxconvert cannot read at all.
    time_strings = [f'"{value:.4f}"' for value in times]
    for start, end in reversed(_channel_blocks(lines)):
        block = lines[start:end]
        name = ""
        for line in block:
            found = re.match(r'\s*"name"\s+"string"\s+"([^"]+)"', line)
            if found:
                name = found.group(1)
                break
        if not name.endswith(("_o", "_p")):
            continue
        orientation = name.endswith("_o")
        joint = name[:-2]
        report["channels" if orientation else "position_channels"] += 1
        key, open_at, close_at = _find_array(block, 0, "times")
        block = _rewrite_array(block, open_at, close_at, time_strings)
        key, open_at, close_at = _find_array(block, 0, "values")
        values = samples.get(joint) if orientation else positions.get(joint)
        if values is None:
            # Hold the template's first sample: a joint the port cannot drive stays at rest.
            original = block[open_at + 1].split(",")[0].strip().strip('"')
            block = _rewrite_array(block, open_at, close_at, [f'"{original}"'] * len(times))
            report["held" if orientation else "positions_held"].append(joint)
        else:
            block = _rewrite_array(block, open_at, close_at, [f'"{_format(row)}"' for row in values])
            report["baked" if orientation else "positions_baked"].append(joint)
        lines[start:end] = block
    body = "".join(lines)
    body = re.sub(r'("duration" "time" ")[0-9.]+(")', lambda match: f"{match.group(1)}{duration:.4f}{match.group(2)}", body, count=1)
    report["missing_channels"] = sorted(set(samples) - set(report["baked"]))
    report["missing_positions"] = sorted(set(positions) - set(report["positions_baked"]))
    return body, report


def write_vnmclip(path: Path, *, clip_name: str, skeleton: str, source_dmx: str) -> None:
    """One CNmClipDocument: the DMX the engine samples, and the skeleton it is bound to."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        '<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} '
        'format:generic:version{7412167c-06e9-4698-aff2-e63eb59037e7} -->\n'
        "{\n"
        '\t_class = "CNmClipDocument"\n'
        "\tm_nVersion = 1\n"
        f'\tm_sourceFilename = "{source_dmx}"\n'
        f'\tm_animationSkeletonName = "{skeleton}"\n'
        '\tm_additiveType = "None"\n'
        '\tm_additiveBaseFilename = ""\n'
        '\tm_additiveBaseFrame = "UserSpecifiedFrame"\n'
        "\tm_nAdditiveBaseFrameIdx = 0\n"
        "\tm_bonesToSampleInModelSpace = [  ]\n"
        "\tm_eventTracks = [  ]\n"
        "}\n"
    )
    path.write_text(body, encoding="utf-8")


def plan_rows(
    *,
    loco_slots: list[str],
    aim_clips: list[str],
    sequences: dict[str, str],
    smd_index: dict[str, str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Every clip either graph asks for, and what will be missing, named per row.

    A locomotion slot in the authored Dota graph already carries the port's own sequence name
    (the graph was retargeted with those names), so its source is itself; a name that the QC
    resolves to an SMD wins, and a bare SMD of the same name is the fallback. The aim clips are
    named after the live hero's files and are mapped to Scout's sequences through AIM_SOURCES.
    """
    index = smd_index or {}
    rows: list[dict] = []
    missing: list[dict] = []
    for slot in loco_slots:
        source = slot
        smd = sequences.get(slot, "") or index.get(slot, "")
        row = {
            "name": slot,
            "graph": "scout_loco.vanmgrph",
            "kind": "sequence",
            "source_sequence": source,
            "smd": smd,
            "reason": "loco-slot" if smd else "no-source-smd",
        }
        (rows if smd else missing).append(row)
    for clip in aim_clips:
        name = Path(clip).stem
        source = AIM_SOURCES.get(name, "")
        smd = sequences.get(source, "") or index.get(source, "")
        row = {
            "name": name,
            "graph": "hero_aim.vnmgraph",
            "kind": "clip",
            "source_sequence": source,
            "smd": smd,
            "reason": "aim-pose" if source else "no-semantic-source",
        }
        (rows if smd else missing).append(row)
    return rows, missing


def summarise(rows: list[dict]) -> dict:
    sources = {}
    for row in rows:
        sources.setdefault(row["source_sequence"], []).append(row["name"])
    return {
        "references": len(rows),
        "distinct_clips": len({row["name"] for row in rows}),
        "distinct_sources": len(sources),
        "source_use": {name: len(rows_) for name, rows_ in sorted(sources.items())},
    }


def load_plan(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
