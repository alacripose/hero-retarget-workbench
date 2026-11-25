"""Build a Deadlock mesh DMX, model document and material definitions from the port's own geometry.

The port ships its mesh as a Source 1 model (`scout.mdl` + `scout.vvd` + `scout.dx90.vtx`), a plain
`scout.obj` with 8,261 vertices and 7,814 faces, and 15 `.vtf` textures. Deadlock wants a mesh DMX whose
`DmeVertexData` carries `position$0`/`normal$0`/`texcoord$0` plus `blendindices$0`/`blendweights$0`
against the skeleton's `jointList`, a `.vmdl` whose `RenderMeshFile` names that DMX, and materials.

Nothing here invents geometry: the OBJ's vertices, polygons, texture coordinates and groups are what get
written. Weights are solved here, because the OBJ carries none: every vertex takes the four skeleton
segments nearest to it, weighted by inverse squared distance and normalized to 1.

The DMX is keyvalues2, the encoding the port's skeleton and clip documents already use, and the encoding
`dmxconvert` reads. `inspect_mesh_dmx` parses the written file back and reports what it holds, so a claim
about the mesh is a claim about the file on disk.
"""
from __future__ import annotations

import argparse
import math
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

KV3_HEADER = (
    "<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} "
    "format:modeldoc28:version{fb63b6ca-f435-4aa0-a2c7-c66ddc651dca} -->\n"
)
DMX_HEADER = "<!-- dmx encoding keyvalues2 4 format model 22 -->\n"
MODEL_ROOT = "models/heroes_wip/scout"
MESH_NAME = "scout_body"
SKELETON_DMX = f"{MODEL_ROOT}/dmx/mesh/scout_skel.dmx"
MESH_DMX = f"{MODEL_ROOT}/dmx/mesh/{MESH_NAME}.dmx"
# ModelDoc resolves RenderMeshFile paths from the `models/` root, not from the content root.
MESH_DMX_REF = MESH_DMX[len("models/"):]
MODEL_VMDL = f"{MODEL_ROOT}/{MESH_NAME}.vmdl"
JOINTS_PER_VERTEX = 4


# --------------------------------------------------------------------------- kv2 reading


@dataclass
class Element:
    klass: str
    id: str = ""
    name: str = ""
    attrs: dict = field(default_factory=dict)


class DmxError(ValueError):
    pass


_INLINE = re.compile(r'^"([^"]*)"\s+"([^"]*)"\s+"(.*)"$')
_NAMED = re.compile(r'^"([^"]*)"\s+"([^"]*)"\s*$')
_CLASS = re.compile(r'^"([^"]+)"$')


def _strip(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith("<!--"):
        return None
    return text.rstrip(",")


def parse_dmx(text: str) -> Element:
    """A keyvalues2 DMX document as elements, with element ids resolved after the walk."""
    lines = text.splitlines()
    index = [0]
    registry: dict[str, Element] = {}

    def parse_element(klass: str | None = None) -> Element:
        if klass is None:
            header = _CLASS.match(_strip(lines[index[0]]) or "")
            if header is None:
                raise DmxError(f"dmx-element-header: line {index[0] + 1}")
            klass = header.group(1)
            index[0] += 1
        while index[0] < len(lines) and _strip(lines[index[0]]) is None:
            index[0] += 1
        if index[0] >= len(lines) or _strip(lines[index[0]]) != "{":
            shown = _strip(lines[index[0]]) if index[0] < len(lines) else "<eof>"
            raise DmxError(f"dmx-element-open: line {index[0] + 1}: {shown[:80]}")
        index[0] += 1
        element = Element(klass)
        parse_body(element, "}")
        registry[element.id or element.name] = element
        return element

    def parse_value(kind: str, raw: str):
        if kind in {"int", "int64"}:
            return int(raw)
        if kind in {"float", "time"}:
            return float(raw)
        if kind == "bool":
            return raw not in {"0", "false"}
        if kind == "elementid":
            return raw
        if kind in {"vector2", "vector3", "vector4", "quaternion", "color"}:
            return tuple(float(part) for part in raw.split())
        if kind == "binary":
            return raw
        return raw

    def parse_array(kind: str) -> list:
        index[0] += 1  # the opening bracket
        items: list = []
        while True:
            if index[0] >= len(lines):
                raise DmxError("dmx-array-unterminated")
            text = _strip(lines[index[0]])
            if text is None:
                index[0] += 1
                continue
            if text == "]":
                index[0] += 1
                return items
            named = _NAMED.match(text)
            if named and index[0] + 1 < len(lines) and _strip(lines[index[0] + 1]) == "{":
                index[0] += 1
                items.append(parse_element(named.group(2)))
                continue
            single = _CLASS.match(text)
            if single:
                following = _strip(lines[index[0] + 1]) if index[0] + 1 < len(lines) else None
                if following == "{":
                    items.append(parse_element())
                else:
                    items.append(parse_value(kind.replace("_array", ""), single.group(1)))
                    index[0] += 1
                continue
            if named:
                items.append(parse_value(kind.replace("_array", ""), named.group(2)))
                index[0] += 1
                continue
            inline = _INLINE.match(text)
            if inline:
                items.append(parse_value(kind.replace("_array", ""), inline.group(3)))
                index[0] += 1
                continue
            raise DmxError(f"dmx-array-item: {text[:60]}")

    def parse_body(element: Element, terminator: str) -> None:
        while True:
            if index[0] >= len(lines):
                raise DmxError("dmx-body-unterminated")
            text = _strip(lines[index[0]])
            if text is None:
                index[0] += 1
                continue
            if text == terminator:
                index[0] += 1
                return
            named = _NAMED.match(text)
            if named:
                key, kind = named.group(1), named.group(2)
                if kind.endswith("_array"):
                    index[0] += 1
                    element.attrs[key] = parse_array(kind)
                    continue
                if kind[0].isupper():
                    index[0] += 1
                    element.attrs[key] = parse_element(kind)
                    continue
                index[0] += 1
                element.attrs[key] = ""
                continue
            inline = _INLINE.match(text)
            if inline:
                key, kind, raw = inline.groups()
                if key == "id" and kind == "elementid":
                    element.id = raw
                elif key == "name" and kind == "string":
                    element.name = raw
                element.attrs[key] = parse_value(kind, raw)
                index[0] += 1
                continue
            index[0] += 1

    while index[0] < len(lines):
        text = _strip(lines[index[0]])
        if text and _CLASS.match(text):
            break
        index[0] += 1
    root = parse_element()
    while index[0] < len(lines):  # the document's remaining top-level elements
        text = _strip(lines[index[0]])
        following = _strip(lines[index[0] + 1]) if index[0] + 1 < len(lines) else None
        if text is None or not _CLASS.match(text) or following != "{":
            index[0] += 1
            continue
        parse_element()
    root.attrs["_registry"] = registry
    for element in registry.values():
        element.attrs["_registry"] = registry
    return root


def _walk(element: Element):
    yield element
    for value in element.attrs.values():
        if isinstance(value, Element):
            yield from _walk(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Element):
                    yield from _walk(item)


def _resolve(element: Element, key: str) -> Element | None:
    value = element.attrs.get(key)
    registry = element.attrs.get("_registry", {})
    if isinstance(value, str):
        return registry.get(value)
    if isinstance(value, Element):
        return value
    return None


# --------------------------------------------------------------------------- the port's geometry


@dataclass
class ObjMesh:
    positions: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    texcoords: list[tuple[float, float]]
    faces: list[tuple[str, list[tuple[int, int, int]]]]

    @property
    def groups(self) -> list[str]:
        return sorted({group for group, _ in self.faces})


def read_obj(path: Path) -> ObjMesh:
    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    faces: list[tuple[str, list[tuple[int, int, int]]]] = []
    group, usemtl = "default", "default"
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            positions.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "vn" and len(parts) >= 4:
            normals.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "vt" and len(parts) >= 3:
            texcoords.append((float(parts[1]), float(parts[2])))
        elif parts[0] in {"g", "o"} and len(parts) > 1:
            group = parts[1]
        elif parts[0] == "usemtl" and len(parts) > 1:
            usemtl = parts[1]
            group = usemtl
        elif parts[0] == "f" and len(parts) >= 4:
            corners: list[tuple[int, int, int]] = []
            for token in parts[1:]:
                fields = token.split("/")
                vertex = int(fields[0])
                uv = int(fields[1]) if len(fields) > 1 and fields[1] else 0
                normal = int(fields[2]) if len(fields) > 2 and fields[2] else 0
                corners.append(
                    (
                        vertex - 1 if vertex > 0 else len(positions) + vertex,
                        uv - 1 if uv > 0 else -1,
                        normal - 1 if normal > 0 else -1,
                    )
                )
            faces.append((group, corners))
    if not positions or not faces:
        raise DmxError(f"obj-empty: {path}")
    return ObjMesh(positions, normals, texcoords, faces)


@dataclass(frozen=True)
class SkeletonJoint:
    name: str
    position: tuple[float, float, float]
    orientation: tuple[float, float, float, float]
    children: tuple[int, ...]
    parent: int


def read_skeleton(path: Path) -> list[SkeletonJoint]:
    """`jointList` order, with the parent index derived from the hierarchy."""
    root = parse_dmx(Path(path).read_text(encoding="utf-8", errors="replace"))
    model = _resolve(root, "skeleton") or _resolve(root, "model")
    if model is None:
        raise DmxError(f"skeleton-model-missing: {path}")
    registry = root.attrs.get("_registry", {})
    joint_list = model.attrs.get("jointList", [])
    joint_elements = [
        element if isinstance(element, Element) else registry.get(element)
        for element in joint_list
    ]
    joint_elements = [element for element in joint_elements if isinstance(element, Element)]
    if not joint_elements:
        raise DmxError(f"skeleton-jointlist-empty: {path}")
    index_of = {element.id: position for position, element in enumerate(joint_elements)}
    parents = [-1] * len(joint_elements)
    for position, element in enumerate(joint_elements):
        for child in element.attrs.get("children", []):
            child_id = child.id if isinstance(child, Element) else child
            if child_id in index_of:
                parents[index_of[child_id]] = position
    joints = []
    for position, element in enumerate(joint_elements):
        transform = element.attrs.get("transform")
        if not isinstance(transform, Element):
            raise DmxError(f"skeleton-joint-transform: {element.name}")
        joints.append(
            SkeletonJoint(
                name=element.name,
                position=tuple(transform.attrs.get("position", (0.0, 0.0, 0.0))),
                orientation=tuple(transform.attrs.get("orientation", (0.0, 0.0, 0.0, 1.0))),
                children=tuple(
                    index_of[child.id if isinstance(child, Element) else child]
                    for child in element.attrs.get("children", [])
                    if (child.id if isinstance(child, Element) else child) in index_of
                ),
                parent=parents[position],
            )
        )
    return joints


def _rotate(quaternion, vector):
    x, y, z, w = quaternion
    vx, vy, vz = vector
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def world_positions(joints: list[SkeletonJoint]) -> list[tuple[float, float, float]]:
    world: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(joints)
    done = [False] * len(joints)

    def solve(index: int, depth: int = 0) -> tuple[float, float, float]:
        if done[index]:
            return world[index]
        if depth > len(joints):
            raise DmxError("skeleton-cycle")
        joint = joints[index]
        if joint.parent < 0:
            world[index] = joint.position
        else:
            parent = joints[joint.parent]
            anchor = solve(joint.parent, depth + 1)
            offset = _rotate(parent.orientation, joint.position)
            world[index] = (
                anchor[0] + offset[0],
                anchor[1] + offset[1],
                anchor[2] + offset[2],
            )
        done[index] = True
        return world[index]

    for position in range(len(joints)):
        solve(position)
    return world


def _segments(joints, world) -> list[tuple[int, tuple[float, float, float], tuple[float, float, float]]]:
    segments = []
    for index, joint in enumerate(joints):
        if not joint.children:
            continue
        for child in joint.children:
            segments.append((index, world[index], world[child]))
    if not segments:
        segments = [(index, point, point) for index, point in enumerate(world)]
    return segments


def _distance_to_segment(point, start, end) -> float:
    sx, sy, sz = start
    ex, ey, ez = end
    px, py, pz = point
    dx, dy, dz = ex - sx, ey - sy, ez - sz
    length = dx * dx + dy * dy + dz * dz
    if length <= 1e-12:
        return math.dist(point, start)
    t = ((px - sx) * dx + (py - sy) * dy + (pz - sz) * dz) / length
    t = max(0.0, min(1.0, t))
    return math.dist(point, (sx + t * dx, sy + t * dy, sz + t * dz))


def solve_weights(positions, joints, world):
    """Four nearest bone segments per vertex, inverse-square weighted and normalized."""
    segments = _segments(joints, world)
    weights: list[list[tuple[int, float]]] = []
    for point in positions:
        distances = [
            (_distance_to_segment(point, start, end), joint)
            for joint, start, end in segments
        ]
        distances.sort()
        nearest = distances[:JOINTS_PER_VERTEX]
        raw = [(joint, 1.0 / max(distance, 1e-4) ** 2) for distance, joint in nearest]
        total = sum(weight for _, weight in raw)
        row = [(joint, weight / total) for joint, weight in raw]
        while len(row) < JOINTS_PER_VERTEX:
            row.append((row[0][0], 0.0))
        weights.append(row)
    return weights


# --------------------------------------------------------------------------- writing


def _number(value: float) -> str:
    text = f"{value:.7f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def _vector(values) -> str:
    return " ".join(_number(value) for value in values)


def _element_id() -> str:
    return str(uuid.uuid4())


def _array(name: str, kind: str, items, indent: str) -> str:
    body = ",\n".join(f'{indent}\t"{item}"' for item in items)
    if not body:
        return f'{indent}"{name}" "{kind}" \n{indent}[\n{indent}]\n'
    return f'{indent}"{name}" "{kind}" \n{indent}[\n{body}\n{indent}]\n'


def _element_refs(name: str, ids, indent: str) -> str:
    body = ",\n".join(f'{indent}\t"element" "{ident}"' for ident in ids)
    if not body:
        return f'{indent}"{name}" "element_array" \n{indent}[\n{indent}]\n'
    return f'{indent}"{name}" "element_array" \n{indent}[\n{body}\n{indent}]\n'


def _corner_stream(mesh: ObjMesh):
    """Per-corner indices into the unique arrays; polygon faces keep their corner count."""
    position_indices: list[int] = []
    texcoord_stream: list[tuple[float, float]] = []
    texcoord_indices: list[int] = []
    faces: list[int] = []
    by_group: dict[str, list[int]] = {}
    seen_texcoords: dict[tuple[float, float], int] = {}
    for group, corners in mesh.faces:
        row = by_group.setdefault(group, [])
        for vertex, uv, _normal in corners:
            position_indices.append(vertex)
            key = mesh.texcoords[uv] if 0 <= uv < len(mesh.texcoords) else (0.0, 0.0)
            if key not in seen_texcoords:
                seen_texcoords[key] = len(texcoord_stream)
                texcoord_stream.append(key)
            texcoord_indices.append(seen_texcoords[key])
            row.append(len(faces))
            faces.append(len(faces))
        row.append(-1)
    face_groups = [(group, values) for group, values in by_group.items()]
    return position_indices, texcoord_stream, texcoord_indices, faces, face_groups


def smooth_normals(mesh: ObjMesh) -> list[tuple[float, float, float]]:
    """Area-weighted vertex normals, or the OBJ's own when every corner has one."""
    if mesh.normals:
        normals = [(0.0, 0.0, 0.0)] * len(mesh.positions)
        counts = [0] * len(mesh.positions)
        for _group, corners in mesh.faces:
            for vertex, _uv, normal in corners:
                if 0 <= normal < len(mesh.normals):
                    n = mesh.normals[normal]
                    current = normals[vertex]
                    normals[vertex] = (current[0] + n[0], current[1] + n[1], current[2] + n[2])
                    counts[vertex] += 1
        result = []
        for index, value in enumerate(normals):
            length = math.sqrt(sum(part * part for part in value))
            result.append(
                tuple(part / length for part in value) if length > 1e-9 else (0.0, 0.0, 1.0)
            )
        return result
    normals = [(0.0, 0.0, 0.0)] * len(mesh.positions)
    for _group, corners in mesh.faces:
        for position in range(1, len(corners) - 1):
            a, b, c = corners[0][0], corners[position][0], corners[position + 1][0]
            ax, ay, az = mesh.positions[a]
            bx, by, bz = mesh.positions[b]
            cx, cy, cz = mesh.positions[c]
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx, vy, vz = cx - ax, cy - ay, cz - az
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            for vertex in (a, b, c):
                current = normals[vertex]
                normals[vertex] = (current[0] + nx, current[1] + ny, current[2] + nz)
    result = []
    for value in normals:
        length = math.sqrt(sum(part * part for part in value))
        result.append(tuple(part / length for part in value) if length > 1e-9 else (0.0, 0.0, 1.0))
    return result


def material_name(group: str) -> str:
    """The port's material for one OBJ group, from the names the textures carry.

    The shipped hero models name their materials with the full `models/...` path
    (`models/heroes_wip/abrams/materials/abrams_coat.vmat_c` is what pak01 carries), so the
    element name keeps that prefix. Dropping it made the live client ask for
    `heroes_wip/scout/materials/scout_head.vmat_c`, which no pak carries, and it drew the
    material-less fallback body.
    """
    lowered = group.lower()
    stem = "scout_red"
    if "eye" in lowered or "head" in lowered:
        stem = "scout_head"
    elif "hand" in lowered:
        stem = "scout_hands"
    elif "blue" in lowered:
        stem = "scout_blue"
    return f"{MODEL_ROOT}/materials/{stem}.vmat"


def write_mesh_dmx(
    destination: Path,
    mesh: ObjMesh,
    joints: list[SkeletonJoint],
    weights: list[list[tuple[int, float]]],
) -> Path:
    joint_ids = [_element_id() for _ in joints]
    model_id, model_transform = _element_id(), _element_id()
    roots = [index for index, joint in enumerate(joints) if joint.parent < 0]
    if len(roots) != 1:
        raise DmxError(f"mesh-skeleton-roots: expected one, found {len(roots)}")
    positions = mesh.positions
    normals = smooth_normals(mesh)
    position_indices, texcoords, texcoord_indices, faces, face_groups = _corner_stream(mesh)

    vertex_id, dag_id, mesh_id = _element_id(), _element_id(), _element_id()
    dag_transform = _element_id()
    face_materials: dict[str, str] = {}

    parts: list[str] = [DMX_HEADER, '"DmElement"\n{\n']
    parts.append(f'\t"id" "elementid" "{_element_id()}"\n')
    parts.append('\t"name" "string" "root"\n')
    parts.append(f'\t"model" "element" "{model_id}"\n')
    parts.append(f'\t"skeleton" "element" "{model_id}"\n')
    parts.append('\t"exportTags" "DmeExportTags"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{_element_id()}"\n')
    parts.append('\t\t"name" "string" "exportTags"\n')
    parts.append('\t\t"app" "string" "sfm"\n')
    parts.append('\t\t"source" "string" "Deadlock Model Forge - forge.meshbuild"\n')
    parts.append('\t}\n\n}\n\n')

    parts.append('"DmeModel"\n{\n')
    parts.append(f'\t"id" "elementid" "{model_id}"\n')
    parts.append('\t"name" "string" "scout_body_skeleton"\n')
    parts.append('\t"transform" "DmeTransform"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{model_transform}"\n')
    parts.append('\t\t"position" "vector3" "0 0 0"\n')
    parts.append('\t\t"orientation" "quaternion" "0 0 0 1"\n\t}\n\n')
    parts.append('\t"shape" "element" ""\n\t"visible" "bool" "1"\n')
    parts.append(_element_refs("children", [dag_id, *(joint_ids[index] for index in roots)], "\t"))
    parts.append(_element_refs("jointList", joint_ids, "\t"))
    parts.append('\t"baseStates" "element_array" \n\t[\n\t]\n')
    parts.append('\t"axisSystem" "DmeAxisSystem"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{_element_id()}"\n')
    parts.append('\t\t"upAxis" "int" "3"\n')
    parts.append('\t\t"forwardParity" "int" "1"\n')
    parts.append('\t\t"coordSys" "int" "0"\n\t}\n\n')
    parts.append('}\n\n')

    parts.append('"DmeDag"\n{\n')
    parts.append(f'\t"id" "elementid" "{dag_id}"\n')
    parts.append(f'\t"name" "string" "{MESH_NAME}"\n')
    parts.append('\t"transform" "DmeTransform"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{dag_transform}"\n')
    parts.append('\t\t"position" "vector3" "0 0 0"\n')
    parts.append('\t\t"orientation" "quaternion" "0 0 0 1"\n\t}\n\n')
    parts.append('\t"visible" "bool" "1"\n')
    parts.append('\t"children" "element_array" \n\t[\n\t]\n')
    parts.append('\t"shape" "DmeMesh"\n\t{\n')
    parts.append(f'\t\t"id" "elementid" "{mesh_id}"\n')
    parts.append(f'\t\t"name" "string" "{MESH_NAME}Shape"\n')
    parts.append('\t\t"visible" "bool" "1"\n')
    parts.append('\t\t"bindState" "element" ""\n')
    parts.append(f'\t\t"currentState" "element" "{vertex_id}"\n')
    parts.append(f'\t\t"baseStates" "element_array" \n\t\t[\n\t\t\t"element" "{vertex_id}"\n\t\t]\n')
    parts.append('\t\t"deltaStates" "element_array" \n\t\t[\n\t\t]\n')
    parts.append('\t\t"faceSets" "element_array" \n\t\t[\n')
    blocks = []
    for group, face_values in face_groups:
        material = face_materials.setdefault(group, _element_id())
        body = ",\n".join(f'\t\t\t\t\t"{value}"' for value in face_values)
        blocks.append(
            '\t\t\t"DmeFaceSet"\n\t\t\t{\n'
            f'\t\t\t\t"id" "elementid" "{_element_id()}"\n'
            f'\t\t\t\t"name" "string" "{group.strip() or "default"}SG"\n'
            f'\t\t\t\t"material" "element" "{material}"\n'
            f'\t\t\t\t"faces" "int_array" \n\t\t\t\t[\n{body}\n\t\t\t\t]\n'
            '\t\t\t}'
        )
    parts.append(",\n".join(blocks) + "\n")
    parts.append('\t\t]\n\t}\n\n}\n\n')

    parts.append('"DmeVertexData"\n{\n')
    parts.append(f'\t"id" "elementid" "{vertex_id}"\n')
    parts.append('\t"name" "string" "bind"\n')
    parts.append(_array("vertexFormat", "string_array", [
        "position$0", "normal$0", "texcoord$0", "blendindices$0", "blendweights$0"
    ], "\t"))
    parts.append(f'\t"jointCount" "int" "{JOINTS_PER_VERTEX}"\n')
    parts.append('\t"flipVCoordinates" "bool" "0"\n')
    parts.append(_array("position$0", "vector3_array", [_vector(p) for p in positions], "\t"))
    parts.append(_array("position$0Indices", "int_array", position_indices, "\t"))
    parts.append(_array("normal$0", "vector3_array", [_vector(n) for n in normals], "\t"))
    parts.append(_array("normal$0Indices", "int_array", position_indices, "\t"))
    parts.append(_array("texcoord$0", "vector2_array", [_vector(uv) for uv in texcoords], "\t"))
    parts.append(_array("texcoord$0Indices", "int_array", texcoord_indices, "\t"))
    flat_indices: list[int] = []
    flat_weights: list[float] = []
    for row in weights:
        for joint, weight in row:
            flat_indices.append(joint)
            flat_weights.append(weight)
    parts.append(_array("blendindices$0", "int_array", flat_indices, "\t"))
    parts.append(_array("blendweights$0", "float_array", [_number(w) for w in flat_weights], "\t"))
    parts.append('}\n\n')

    for group, material_id in face_materials.items():
        parts.append('"DmeMaterial"\n{\n')
        parts.append(f'\t"id" "elementid" "{material_id}"\n')
        parts.append(f'\t"name" "string" "{material_name(group).rsplit("/", 1)[-1]}"\n')
        parts.append(f'\t"mtlName" "string" "{material_name(group)}"\n')
        parts.append('}\n\n')

    for index, joint in enumerate(joints):
        parts.append('"DmeJoint"\n{\n')
        parts.append(f'\t"id" "elementid" "{joint_ids[index]}"\n')
        parts.append(f'\t"name" "string" "{joint.name}"\n')
        parts.append('\t"transform" "DmeTransform"\n\t{\n')
        parts.append(f'\t\t"id" "elementid" "{_element_id()}"\n')
        parts.append(f'\t\t"name" "string" "{joint.name}"\n')
        parts.append(f'\t\t"position" "vector3" "{_vector(joint.position)}"\n')
        parts.append(f'\t\t"orientation" "quaternion" "{_vector(joint.orientation)}"\n\t}}\n\n')
        parts.append('\t"shape" "element" ""\n\t"visible" "bool" "1"\n')
        parts.append(_element_refs("children", [joint_ids[c] for c in joint.children], "\t"))
        parts.append('}\n\n')

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(parts), encoding="utf-8", newline="\n")
    return destination


def write_model(target: Path) -> Path:
    """A modeldoc whose one render mesh is the DMX this module wrote, bound to Scout's hero graph.

    The shipped hero models carry their hero graph here, not in the hero table: `AnimGraph2List`
    names the hero graph and the compiled model repeats it as `m_sAG2HeroPawnAnimGraph` with
    `m_bUseAG2HeroGraph = true` (decompiled from `models/heroes_wip/inferno/inferno.vmdl_c`).
    A model without this list loads no hero graph at all, which is what the first live session
    showed; the form of the graph path here is the binding this addon is testing in the engine.

    For this pass the path names Scout's standalone authored graph, which is compiled and verified
    against the 78-bone skeleton. The engine's answer (loads vs. refuses) is what decides whether
    the standalone or the `hero.vnmgraph+scout.vnmgraph` variation is the accepted form.
    """
    text = KV3_HEADER + """{
	rootNode =
	{
		_class = "RootNode"
		children =
		[
			{
				_class = "RenderMeshList"
				children =
				[
					{
						_class = "RenderMeshFile"
						filename = "%s"
						import_scale = 1.0
						import_filter =
						{
							exclude_by_default = false
							exception_list = [  ]
						}
					},
				]
			},
			{
				_class = "AnimGraph2List"
				children =
				[
					{
						_class = "DefaultAnimGraph2"
						filename = "models/heroes_wip/scout/scout.vnmgraph"
					},
					{
						_class = "AnimGraph2"
						name = "ui"
						filename = "models/heroes_wip/scout/scout.vnmgraph"
					},
				]
			},
			{
				_class = "GenericGameData"
				name = ""
				game_class = "CCitadelHeroModelGameData_t"
				game_keys =
				{
					m_sAG2UIAnimGraph = resource_name:"models/heroes_wip/scout/scout.vnmgraph"
					m_sAG2HeroPawnAnimGraph = resource_name:"models/heroes_wip/scout/scout.vnmgraph"
					m_bUseAG2HeroGraph = true
					m_bUseAG2UIGraph = true
				}
			},
		]
	}
}
""" % MESH_DMX_REF
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def _placeholder_png(path: Path) -> Path:
    """An 8x8 mid-grey PNG, for a texture the port names but did not ship as pixels."""
    import struct
    import zlib

    width = height = 8
    raw = b"".join(b"\x00" + bytes([128, 128, 128]) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return path


def write_materials(directory: Path, textures: list[str], texture_dir: Path | None = None) -> list[Path]:
    """One `.vmt` and one `.vmat` per texture, plus the `.png` the `.vmat` samples."""
    written = []
    directory.mkdir(parents=True, exist_ok=True)
    for texture in textures:
        stem = Path(texture).stem
        png = directory / f"{stem}.png"
        source = None
        if texture_dir is not None:
            for candidate in (f"{stem}_00_00_00.png", f"{stem}.png"):
                if (Path(texture_dir) / candidate).is_file():
                    source = Path(texture_dir) / candidate
                    break
        if source is not None:
            png.write_bytes(source.read_bytes())
        elif not png.is_file():
            _placeholder_png(png)
        written.append(png)
        vmt = directory / f"{stem}.vmt"
        vmt.write_text(
            "// Deadlock Model Forge - legacy material for the port's Source 1 texture\n"
            '"VertexLitGeneric"\n{\n'
            f'\t"$basetexture" "{MODEL_ROOT}/materials/{stem}"\n'
            '\t"$model" "1"\n'
            '\t"$surfaceprop" "flesh"\n}\n',
            encoding="utf-8",
            newline="\n",
        )
        vmat = directory / f"{stem}.vmat"
        vmat.write_text(
            "// Deadlock Model Forge - Deadlock material for the port's texture\n"
            "Layer0\n{\n\tshader \"pbr.vfx\"\n\n"
            f"\tTextureColor1 \"{MODEL_ROOT}/materials/{stem}.png\"\n"
            "\tg_vColorTint1 \"[1.000000 1.000000 1.000000 0.000000]\"\n"
            "\tg_flNormalAndRoughnessScrollQuantize1 \"0.000\"\n}\n",
            encoding="utf-8",
            newline="\n",
        )
        written.extend([vmt, vmat])
    return written


# --------------------------------------------------------------------------- reading the result back


def inspect_mesh_dmx(path: Path) -> dict:
    """What the written file actually contains, parsed from the file itself."""
    root = parse_dmx(Path(path).read_text(encoding="utf-8", errors="replace"))
    model = _resolve(root, "skeleton")
    if model is None:
        raise DmxError(f"meshdmx-skeleton-missing: {path}")
    registry = root.attrs.get("_registry", {})
    joint_elements = [
        e if isinstance(e, Element) else registry.get(e) for e in model.attrs.get("jointList", [])
    ]
    joint_elements = [e for e in joint_elements if isinstance(e, Element)]
    children = [
        e if isinstance(e, Element) else registry.get(e) for e in model.attrs.get("children", [])
    ]
    dag = next((e for e in children if isinstance(e, Element) and e.klass == "DmeDag"), None)
    mesh = dag.attrs.get("shape") if dag is not None else None
    if not isinstance(mesh, Element) or mesh.klass != "DmeMesh":
        raise DmxError(f"meshdmx-dme-mesh-missing: {path}")
    vertex = mesh.attrs.get("currentState")
    if isinstance(vertex, str):
        vertex = registry.get(vertex)
    if not isinstance(vertex, Element):
        raise DmxError(f"meshdmx-vertexdata-missing: {path}")
    positions = vertex.attrs.get("position$0", [])
    faces = []
    materials = []
    for face_set in mesh.attrs.get("faceSets", []):
        if isinstance(face_set, Element):
            faces.append(sum(1 for value in face_set.attrs.get("faces", []) if value == -1))
            material = face_set.attrs.get("material")
            if isinstance(material, str):
                material = registry.get(material)
            if isinstance(material, Element):
                materials.append(material.attrs.get("mtlName", material.name))
    flat_indices = vertex.attrs.get("blendindices$0", [])
    flat_weights = vertex.attrs.get("blendweights$0", [])
    joint_count = int(vertex.attrs.get("jointCount", 0) or 0)
    sums = []
    for start in range(0, len(flat_weights), joint_count or 1):
        chunk = flat_weights[start:start + (joint_count or 1)]
        sums.append(sum(chunk))
    return {
        "vertex_count": len(positions),
        "face_count": sum(faces),
        "face_sets": len(faces),
        "materials": materials,
        "joints": [joint.name for joint in joint_elements],
        "joint_count": len(joint_elements),
        "streams": list(vertex.attrs.get("vertexFormat", [])),
        "joints_per_vertex": joint_count,
        "blend_index_max": max(flat_indices) if flat_indices else -1,
        "weight_rows": len(sums),
        "weight_min": round(min(sums), 6) if sums else 0.0,
        "weight_max": round(max(sums), 6) if sums else 0.0,
        "positions_bbox": None,
    }


def build(
    obj_path: Path,
    skeleton_path: Path,
    out: Path,
    textures: list[str],
    materials_dir: Path | None = None,
    textures_dir: Path | None = None,
) -> dict:
    mesh = read_obj(obj_path)
    joints = read_skeleton(skeleton_path)
    world = world_positions(joints)
    weights = solve_weights(mesh.positions, joints, world)
    dmx = write_mesh_dmx(Path(out) / MESH_DMX, mesh, joints, weights)
    vmdl = write_model(Path(out) / MODEL_VMDL)
    materials = write_materials(
        materials_dir or (Path(out) / MODEL_ROOT / "materials"),
        textures,
        Path(textures_dir) if textures_dir else None,
    )
    facts = inspect_mesh_dmx(dmx)
    return {
        "mesh_dmx": str(dmx),
        "mesh_dmx_bytes": dmx.stat().st_size,
        "model_vmdl": str(vmdl),
        "materials": [str(path) for path in materials],
        "source_vertices": len(mesh.positions),
        "source_faces": len(mesh.faces),
        "source_groups": mesh.groups,
        "skeleton_joints": len(joints),
        "skeleton_height": round(max(point[2] for point in world) - min(point[2] for point in world), 3),
        **facts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Scout's Deadlock mesh, model and materials.")
    parser.add_argument("--obj", default="F:/Documents/scout.obj")
    parser.add_argument(
        "--skeleton",
        default="artifacts/scout-port-skel/models/heroes_wip/scout/dmx/mesh/scout_skel.dmx",
    )
    parser.add_argument("--out", default="artifacts/scout-mesh")
    parser.add_argument("--textures", default="F:/Documents/scout")
    args = parser.parse_args(argv)
    textures = sorted(path.name for path in Path(args.textures).glob("*.vtf"))
    report = build(Path(args.obj), Path(args.skeleton), Path(args.out), textures, textures_dir=Path(args.textures))
    for key in (
        "mesh_dmx_bytes", "vertex_count", "face_count", "face_sets", "joint_count",
        "weight_min", "weight_max", "blend_index_max",
    ):
        print(f"{key}: {report[key]}")
    print(f"materials: {len(report['materials'])} files, {len(report['materials']) // 2} textures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
