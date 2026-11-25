"""Build a Deadlock skeleton from the port's own Source 1 rig.

The port ships a reference SMD, not a Deadlock skeleton: `scout_anims/ref.smd` carries `nodes` (name and
parent, in index order) and a `skeleton` block with one local position and one local Euler rotation per
bone. A Deadlock skeleton is a DMX `DmeModel` whose joints hold exactly that: a local transform per
joint, in joint order, with `children` naming the parent-child links.

Nothing here is a retarget. The joint names, the joint order and the rest transforms are the port's own,
so a clip authored for the port binds by name without a bone map. `.vnmskel` is a `CNmSkeletonDocument`
over that DMX, with Scout's bones in the high-LOD list and one body mask per arm-set the port names.

  python -m forge.portskel --smd F:/Documents/scout_anims/ref.smd --out <dir>
"""
from __future__ import annotations

import argparse
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

KV3_HEADER = (
    "<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} "
    "format:generic:version{7412167c-06e9-4698-aff2-e63eb59037e7} -->\n"
)
DMX_HEADER = "<!-- dmx encoding keyvalues2 4 format model 22 -->\n"
AXIS = (3, 1, 0)  # upAxis Z, forwardParity 1, coordSys 0: the values the live skeletons carry


@dataclass(frozen=True)
class Joint:
    name: str
    parent: int
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    children: tuple[int, ...]

    @property
    def quaternion(self) -> tuple[float, float, float, float]:
        return euler_to_quat(*self.rotation)


def euler_to_quat(rx: float, ry: float, rz: float) -> tuple[float, float, float, float]:
    """`R = Rz . Ry . Rx`, the order the port's SMD rotations are authored in."""
    cx, sx = math.cos(rx / 2), math.sin(rx / 2)
    cy, sy = math.cos(ry / 2), math.sin(ry / 2)
    cz, sz = math.cos(rz / 2), math.sin(rz / 2)
    w = cz * cy * cx + sz * sy * sx
    x = cz * cy * sx - sz * sy * cx
    y = cz * sy * cx + sz * cy * sx
    z = sz * cy * cx - cz * sy * sx
    length = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    return (x / length, y / length, z / length, w / length)


def _number(value: float) -> str:
    return f"{value:.7f}".rstrip("0").rstrip(".") or "0"


def read_reference(path: Path) -> list[Joint]:
    """The port's reference SMD as joints in file order, with parent indices intact."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    nodes: list[tuple[str, int]] = []
    local: dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]] = {}
    mode = ""
    for line in lines:
        text = line.strip()
        if text in {"nodes", "skeleton", "triangles", "vertexanimation"}:
            mode = text
            continue
        if text == "end":
            mode = ""
            continue
        if mode == "nodes":
            parts = text.split()
            if len(parts) >= 3:
                nodes.append((parts[1].strip('"'), int(parts[2])))
        elif mode == "skeleton":
            parts = text.split()
            if len(parts) == 7 and parts[0].isdigit():
                values = [float(value) for value in parts[1:]]
                local[int(parts[0])] = (tuple(values[:3]), tuple(values[3:]))
    if not nodes or len(local) != len(nodes):
        raise ValueError(f"smd-incomplete: {len(nodes)} nodes, {len(local)} skeleton lines")
    children: dict[int, list[int]] = {index: [] for index in range(len(nodes))}
    for index, (_, parent) in enumerate(nodes):
        if parent >= 0:
            children[parent].append(index)
    joints = []
    for index, (name, parent) in enumerate(nodes):
        position, rotation = local[index]
        joints.append(Joint(name=name, parent=parent, position=position, rotation=rotation, children=tuple(children[index])))
    return joints


def _element(kind: str) -> str:
    return str(uuid.uuid4())


def write_skeleton_dmx(joints: list[Joint], destination: Path) -> Path:
    """One `DmeModel` skeleton in the shape the live skeletons carry, joints in port order."""
    ids = [_element("DmeJoint") for _ in joints]
    model_id, model_transform = _element("DmeModel"), _element("DmeTransform")
    roots = [index for index, joint in enumerate(joints) if joint.parent < 0]
    if len(roots) != 1:
        raise ValueError(f"skeleton-roots: expected one root, found {len(roots)}")

    def element_list(indices: list[int], indent: str) -> str:
        if not indices:
            return f"{indent}[\n{indent}]\n"
        body = ",\n".join(f'{indent}\t"element" "{ids[index]}"' for index in indices)
        return f"{indent}[\n{body}\n{indent}]\n"

    parts = [DMX_HEADER, '"DmElement"\n{\n']
    parts.append(f'\t"id" "elementid" "{model_id}"\n')
    parts.append('\t"name" "string" "root"\n')
    parts.append('\t"skeleton" "DmeModel"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{_element("DmeModel")}"\n')
    parts.append('\t\t"transform" "DmeTransform"\n\t\t{\n')
    parts.append(f'\t\t\t"id" "elementid" "{model_transform}"\n')
    parts.append('\t\t\t"position" "vector3" "0 0 0"\n')
    parts.append('\t\t\t"orientation" "quaternion" "0 0 0 1"\n\t\t}\n\n')
    parts.append('\t\t"shape" "element" ""\n\t\t"visible" "bool" "1"\n')
    parts.append('\t\t"children" "element_array" \n' + element_list(roots, "\t\t"))
    parts.append('\t\t"jointList" "element_array" \n' + element_list(list(range(len(joints))), "\t\t"))
    parts.append('\t\t"baseStates" "element_array" \n\t\t[\n\t\t]\n')
    parts.append('\t\t"axisSystem" "DmeAxisSystem"\n\t\t{\n')
    parts.append(f'\t\t\t"id" "elementid" "{_element("DmeAxisSystem")}"\n')
    parts.append(f'\t\t\t"upAxis" "int" "{AXIS[0]}"\n')
    parts.append(f'\t\t\t"forwardParity" "int" "{AXIS[1]}"\n')
    parts.append(f'\t\t\t"coordSys" "int" "{AXIS[2]}"\n')
    parts.append('\t\t}\n\n\t}\n\n')
    parts.append('\t"exportTags" "DmeExportTags"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{_element("DmeExportTags")}"\n')
    parts.append('\t\t"name" "string" "exportTags"\n\t\t"app" "string" "sfm"\n')
    parts.append('\t\t"source" "string" "Deadlock Model Forge - forge.portskel"\n\t}\n\n}\n\n')

    for index, joint in enumerate(joints):
        parts.append('"DmeJoint"\n{\n')
        parts.append(f'\t"id" "elementid" "{ids[index]}"\n')
        parts.append(f'\t"name" "string" "{joint.name}"\n')
        parts.append('\t"transform" "DmeTransform"\n\t{\n')
        parts.append(f'\t\t"id" "elementid" "{_element("DmeTransform")}"\n')
        parts.append(f'\t\t"name" "string" "{joint.name}"\n')
        parts.append('\t\t"position" "vector3" "' + " ".join(_number(value) for value in joint.position) + '"\n')
        parts.append('\t\t"orientation" "quaternion" "' + " ".join(_number(value) for value in joint.quaternion) + '"\n\t}\n\n')
        parts.append('\t"shape" "element" ""\n\t"visible" "bool" "1"\n')
        parts.append('\t"children" "element_array" \n' + element_list(list(joint.children), "\t"))
        parts.append("}\n\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(parts), encoding="utf-8")
    return destination


UPPER = re.compile(r"spine|neck|head|collar|arm|hand|finger|thumb", re.I)


def write_vnmskel(destination: Path, *, source: str, root: str, bones: list[str]) -> Path:
    """A `CNmSkeletonDocument` over the built DMX: every bone in LOD 0, plus an upper-body mask."""
    upper = [bone for bone in bones if UPPER.search(bone)]
    masks = [("FullBody", bones), ("UpperBody", upper or bones)]
    lines = [KV3_HEADER, "{\n", '\t_class = "CNmSkeletonDocument"\n', "\tm_nVersion = 0\n"]
    lines.append(f'\tm_sourceFilename = "{source}"\n')
    lines.append(f'\tm_rootBoneName = "{root}"\n')
    lines.append("\tm_flGlobalScale = 1.0\n\tm_bIsAttachableProp = false\n\tm_secondarySkeletons = [  ]\n")
    lines.append("\tm_highLODBones = \n\t[\n")
    lines.append(",\n".join(f'\t\t"{bone}"' for bone in bones))
    lines.append("\n\t]\n\tm_boneMaskSetDefinitions = \n\t[\n")
    for position, (name, members) in enumerate(masks):
        lines.append("\t\t{\n")
        lines.append(f'\t\t\tm_ID = "{name}"\n\t\t\tm_primaryWeightList = \n\t\t\t{{\n')
        lines.append(f'\t\t\t\tm_skeletonName = resource_name:"{source.rsplit("/dmx/", 1)[0]}/scout.vnmskel"\n')
        lines.append("\t\t\t\tm_boneIDs = \n\t\t\t\t[\n")
        lines.append(",\n".join(f'\t\t\t\t\t"{bone}"' for bone in members))
        lines.append("\n\t\t\t\t]\n\t\t\t\tm_weights = \n\t\t\t\t[\n")
        lines.append(",".join("\t\t\t\t\t1.0" for _ in members))
        lines.append("\n\t\t\t\t]\n\t\t\t}\n\t\t\tm_secondaryWeightLists = [  ]\n\t\t}")
        lines.append(",\n" if position + 1 < len(masks) else "\n")
    lines.append("\t]\n}\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(lines), encoding="utf-8")
    return destination


def write_clip_template(joints: list[Joint], destination: Path, *, frames: int = 2, fps: float = 30.0) -> Path:
    """A clip DMX for the port's own joints: an orientation and a position channel per joint, rest held.

    `clipbake.bake_kv2` rewrites the `times` and `values` arrays of every `<joint>_o` and `<joint>_p`
    channel by name, so the template carries each joint's rest rotation and rest local position. A
    sequence with translation on a bone (Scout's pelvis and weapon bone do) needs the position channel
    to exist before the bake can carry that translation.
    """
    ids = [_element("DmeJoint") for _ in joints]
    times = [f'"{index / fps:.4f}"' for index in range(max(frames, 2))]
    roots = [index for index, joint in enumerate(joints) if joint.parent < 0]

    def element_list(indices: list[int], indent: str) -> str:
        if not indices:
            return f"{indent}[\n{indent}]\n"
        body = ",\n".join(f'{indent}\t"element" "{ids[index]}"' for index in indices)
        return f"{indent}[\n{body}\n{indent}]\n"

    def position_channel(index: int, joint: Joint, indent: str) -> list[str]:
        rest = " ".join(_number(value) for value in joint.position)
        rows = [
            f'{indent}"DmeChannel"\n{indent}{{\n',
            f'{indent}\t"id" "elementid" "{_element("DmeChannel")}"\n',
            f'{indent}\t"name" "string" "{joint.name}_p"\n',
            f'{indent}\t"fromElement" "element" ""\n',
            f'{indent}\t"fromAttribute" "string" ""\n',
            f'{indent}\t"fromIndex" "int" "0"\n',
            f'{indent}\t"toElement" "element" "{ids[index]}"\n',
            f'{indent}\t"toAttribute" "string" "position"\n',
            f'{indent}\t"toIndex" "int" "0"\n',
            f'{indent}\t"mode" "int" "3"\n',
            f'{indent}\t"log" "DmeVector3Log"\n{indent}\t{{\n',
            f'{indent}\t\t"id" "elementid" "{_element("DmeVector3Log")}"\n',
            f'{indent}\t\t"name" "string" "vector3 log"\n',
            f'{indent}\t\t"layers" "element_array" \n{indent}\t\t[\n',
            f'{indent}\t\t\t"DmeVector3LogLayer"\n{indent}\t\t\t{{\n',
            f'{indent}\t\t\t\t"id" "elementid" "{_element("DmeVector3LogLayer")}"\n',
            f'{indent}\t\t\t\t"name" "string" "vector3 log"\n',
            f'{indent}\t\t\t\t"times" "time_array" \n{indent}\t\t\t\t[\n',
            ",\n".join(f"{indent}\t\t\t\t\t{value}" for value in times) + "\n",
            f'{indent}\t\t\t\t]\n',
            f'{indent}\t\t\t\t"curvetypes" "int_array" \n{indent}\t\t\t\t[\n{indent}\t\t\t\t]\n',
            f'{indent}\t\t\t\t"values" "vector3_array" \n{indent}\t\t\t\t[\n',
            ",\n".join(f'{indent}\t\t\t\t\t"{rest}"' for _ in times) + "\n",
            f'{indent}\t\t\t\t]\n{indent}\t\t\t}}\n{indent}\t\t]\n',
            f'{indent}\t\t"curveinfo" "element" ""\n',
            f'{indent}\t\t"usedefaultvalue" "bool" "0"\n',
            f'{indent}\t\t"bookmarksX" "time_array" \n{indent}\t\t[\n{indent}\t\t]\n',
            f'{indent}\t\t"bookmarksY" "time_array" \n{indent}\t\t[\n{indent}\t\t]\n',
            f'{indent}\t\t"bookmarksZ" "time_array" \n{indent}\t\t[\n{indent}\t\t]\n',
            f'{indent}\t\t"defaultvalue" "vector3" "0 0 0"\n{indent}\t}}\n',
            f"{indent}}}\n",
        ]
        return rows

    def channel(index: int, joint: Joint, indent: str) -> list[str]:
        rest = " ".join(_number(value) for value in joint.quaternion)
        rows = [
            f'{indent}"DmeChannel"\n{indent}{{\n',
            f'{indent}\t"id" "elementid" "{_element("DmeChannel")}"\n',
            f'{indent}\t"name" "string" "{joint.name}_o"\n',
            f'{indent}\t"fromElement" "element" ""\n',
            f'{indent}\t"fromAttribute" "string" ""\n',
            f'{indent}\t"fromIndex" "int" "0"\n',
            f'{indent}\t"toElement" "element" "{ids[index]}"\n',
            f'{indent}\t"toAttribute" "string" "orientation"\n',
            f'{indent}\t"toIndex" "int" "0"\n',
            f'{indent}\t"mode" "int" "3"\n',
            f'{indent}\t"log" "DmeQuaternionLog"\n{indent}\t{{\n',
            f'{indent}\t\t"id" "elementid" "{_element("DmeQuaternionLog")}"\n',
            f'{indent}\t\t"name" "string" "quaternion log"\n',
            f'{indent}\t\t"layers" "element_array" \n{indent}\t\t[\n',
            f'{indent}\t\t\t"DmeQuaternionLogLayer"\n{indent}\t\t\t{{\n',
            f'{indent}\t\t\t\t"id" "elementid" "{_element("DmeQuaternionLogLayer")}"\n',
            f'{indent}\t\t\t\t"name" "string" "quaternion log"\n',
            f'{indent}\t\t\t\t"times" "time_array" \n{indent}\t\t\t\t[\n',
            ",\n".join(f"{indent}\t\t\t\t\t{value}" for value in times) + "\n",
            f'{indent}\t\t\t\t]\n',
            f'{indent}\t\t\t\t"curvetypes" "int_array" \n{indent}\t\t\t\t[\n{indent}\t\t\t\t]\n',
            f'{indent}\t\t\t\t"values" "quaternion_array" \n{indent}\t\t\t\t[\n',
            ",\n".join(f'{indent}\t\t\t\t\t"{rest}"' for _ in times) + "\n",
            f'{indent}\t\t\t\t]\n{indent}\t\t\t}}\n{indent}\t\t]\n',
            f'{indent}\t\t"curveinfo" "element" ""\n',
            f'{indent}\t\t"usedefaultvalue" "bool" "0"\n',
            f'{indent}\t\t"bookmarksX" "time_array" \n{indent}\t\t[\n{indent}\t\t]\n',
            f'{indent}\t\t"bookmarksY" "time_array" \n{indent}\t\t[\n{indent}\t\t]\n',
            f'{indent}\t\t"bookmarksZ" "time_array" \n{indent}\t\t[\n{indent}\t\t]\n',
            f'{indent}\t\t"defaultvalue" "quaternion" "0 0 0 1"\n{indent}\t}}\n',
            f"{indent}}}\n",
        ]
        return rows

    parts = [DMX_HEADER, '"DmElement"\n{\n']
    parts.append(f'\t"id" "elementid" "{_element("DmElement")}"\n')
    parts.append('\t"name" "string" "root"\n')
    parts.append('\t"skeleton" "DmeModel"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{_element("DmeModel")}"\n')
    parts.append('\t\t"transform" "DmeTransform"\n\t\t{\n')
    parts.append(f'\t\t\t"id" "elementid" "{_element("DmeTransform")}"\n')
    parts.append('\t\t\t"position" "vector3" "0 0 0"\n')
    parts.append('\t\t\t"orientation" "quaternion" "0 0 0 1"\n\t\t}\n\n')
    parts.append('\t\t"shape" "element" ""\n\t\t"visible" "bool" "1"\n')
    parts.append('\t\t"children" "element_array" \n' + element_list(roots, "\t\t"))
    parts.append('\t\t"jointList" "element_array" \n' + element_list(list(range(len(joints))), "\t\t"))
    parts.append('\t\t"baseStates" "element_array" \n\t\t[\n\t\t]\n')
    parts.append('\t\t"axisSystem" "DmeAxisSystem"\n\t\t{\n')
    parts.append(f'\t\t\t"id" "elementid" "{_element("DmeAxisSystem")}"\n')
    parts.append(f'\t\t\t"upAxis" "int" "{AXIS[0]}"\n')
    parts.append(f'\t\t\t"forwardParity" "int" "{AXIS[1]}"\n')
    parts.append(f'\t\t\t"coordSys" "int" "{AXIS[2]}"\n')
    parts.append('\t\t}\n\n\t}\n\n')
    parts.append('\t"animationList" "DmeAnimationList"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{_element("DmeAnimationList")}"\n')
    parts.append('\t\t"animations" "element_array" \n\t\t[\n')
    parts.append('\t\t\t"DmeChannelsClip"\n\t\t\t{\n')
    parts.append(f'\t\t\t\t"id" "elementid" "{_element("DmeChannelsClip")}"\n')
    parts.append('\t\t\t\t"timeFrame" "DmeTimeFrame"\n\t\t\t\t{\n')
    parts.append(f'\t\t\t\t\t"id" "elementid" "{_element("DmeTimeFrame")}"\n')
    parts.append('\t\t\t\t\t"start" "time" "0.0000"\n')
    parts.append(f'\t\t\t\t\t"duration" "time" "{(len(times) - 1) / fps:.4f}"\n')
    parts.append('\t\t\t\t\t"offset" "time" "0.0000"\n\t\t\t\t\t"scale" "float" "1"\n\t\t\t\t}\n\n')
    parts.append('\t\t\t\t"color" "color" "0 0 0 0"\n\t\t\t\t"text" "string" ""\n')
    parts.append('\t\t\t\t"mute" "bool" "0"\n\t\t\t\t"trackGroups" "element_array" \n\t\t\t\t[\n\t\t\t\t]\n')
    parts.append('\t\t\t\t"displayScale" "float" "1"\n\t\t\t\t"channels" "element_array" \n\t\t\t\t[\n')
    blocks = []
    for index, joint in enumerate(joints):
        blocks.append(channel(index, joint, "\t\t\t\t\t"))
        blocks.append(position_channel(index, joint, "\t\t\t\t\t"))
    for position, block in enumerate(blocks):
        if position + 1 < len(blocks):
            # dmxconvert rejects a trailing comma after the last element of an element_array.
            block[-1] = block[-1].rstrip("\n") + ",\n"
        parts.extend(block)
    parts.append('\t\t\t\t]\n\t\t\t}\n\t\t]\n\t}\n\n')
    parts.append('\t"exportTags" "DmeExportTags"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{_element("DmeExportTags")}"\n')
    parts.append('\t\t"name" "string" "exportTags"\n\t\t"app" "string" "sfm"\n')
    parts.append('\t\t"source" "string" "Deadlock Model Forge - forge.portskel"\n\t}\n\n}\n\n')
    for index, joint in enumerate(joints):
        parts.append('"DmeJoint"\n{\n')
        parts.append(f'\t"id" "elementid" "{ids[index]}"\n')
        parts.append(f'\t"name" "string" "{joint.name}"\n')
        parts.append('\t"transform" "DmeTransform"\n\t{\n')
        parts.append(f'\t\t"id" "elementid" "{_element("DmeTransform")}"\n')
        parts.append(f'\t\t"name" "string" "{joint.name}"\n')
        parts.append('\t\t"position" "vector3" "' + " ".join(_number(value) for value in joint.position) + '"\n')
        parts.append('\t\t"orientation" "quaternion" "' + " ".join(_number(value) for value in joint.quaternion) + '"\n\t}\n\n')
        parts.append('\t"shape" "element" ""\n\t"visible" "bool" "1"\n')
        parts.append('\t"children" "element_array" \n' + element_list(list(joint.children), "\t"))
        parts.append("}\n\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(parts), encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smd", default="F:/Documents/scout_anims/ref.smd")
    parser.add_argument("--out", default="artifacts/scout-port-skel")
    parser.add_argument("--model", default="models/heroes_wip/scout")
    args = parser.parse_args()
    joints = read_reference(Path(args.smd))
    out = Path(args.out) / args.model
    dmx = write_skeleton_dmx(joints, out / "dmx/mesh/scout_skel.dmx")
    names = [joint.name for joint in joints]
    vnmskel = write_vnmskel(
        out / "scout.vnmskel",
        source=f"{args.model}/dmx/mesh/scout_skel.dmx",
        root=names[0],
        bones=names,
    )
    print(f"JOINTS {len(joints)} root {names[0]} children {len(joints[0].children)}")
    print(f"DMX {dmx} {dmx.stat().st_size} bytes")
    print(f"VNMSKEL {vnmskel} {vnmskel.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
