"""Read and transplant top-level modeldoc sections without rebuilding a vmdl.

The compiler consumes a modeldoc source file whose root node has top-level child
blocks at a fixed tab indentation. A migration needs to carry a handful of those
blocks (cloth, physics, and optionally a custom render mesh list) from an old
addon into a current game model. This module finds those blocks by their exact
source text so their contents are copied, never interpreted or regenerated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256


class ModeldocError(ValueError):
    pass


TOP_LEVEL_OPEN = "\t\t\t{"
ROOT_CLOSE = "\t\t]"
CLASS_PREFIX = "\t\t\t\t_class = \""


@dataclass(frozen=True)
class Section:
    name: str
    start: int
    end: int
    text: str
    end_has_comma: bool


@dataclass(frozen=True)
class MergeResult:
    text: str
    actions: dict[str, dict[str, str]]


def _brace_delta(line: str) -> int:
    """Count braces outside quoted strings."""
    depth = 0
    quoted = False
    escaped = False
    for char in line:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
    return depth


def _section_name(lines: list[str], start: int, end: int) -> str:
    for line in lines[start + 1 : end]:
        if line.startswith(CLASS_PREFIX) and line.endswith('"'):
            return line[len(CLASS_PREFIX) : -1]
    raise ModeldocError(f"section-has-no-class: line {start + 1}")


def sections(text: str) -> dict[str, Section]:
    """Return every top-level child block keyed by its _class value."""
    lines = text.splitlines()
    found: dict[str, Section] = {}
    for start, line in enumerate(lines):
        if line != TOP_LEVEL_OPEN:
            continue
        depth = 0
        end = None
        for index in range(start, len(lines)):
            depth += _brace_delta(lines[index])
            if depth < 0:
                raise ModeldocError(f"section-brace-underflow: line {index + 1}")
            if depth == 0:
                end = index
                break
        if end is None:
            raise ModeldocError(f"section-has-no-close: line {start + 1}")
        name = _section_name(lines, start, end)
        if name in found:
            raise ModeldocError(f"duplicate-section: {name}")
        block = lines[start : end + 1]
        end_has_comma = block[-1].rstrip().endswith(",")
        if end_has_comma:
            block[-1] = block[-1].rstrip()[:-1]
        found[name] = Section(
            name=name,
            start=start,
            end=end,
            text="\n".join(block),
            end_has_comma=end_has_comma,
        )
    if not found:
        raise ModeldocError("modeldoc-has-no-top-level-sections")
    return found


def cloth_physics_sections(text: str) -> list[str]:
    """Return old-model sections that carry cloth or physics nodes.

    The names are discovered from the old model rather than hard-coded for one
    addon. Source 2 modeldocs use ``Softbody`` and ``PhysicsJointList`` today,
    but older mods can carry other cloth/joint class names; the same exact-block
    transplant is valid for any matching top-level section.
    """
    markers = ("softbody", "cloth", "physicsjoint")
    return [
        name
        for name in sections(text)
        if any(marker in name.lower() for marker in markers)
    ]


def section_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Render meshes and body groups
#
# A modeldoc references one DMX per render mesh (``RenderMeshFile`` with a
# ``name`` and a ``filename``), and a ``BodyGroupList`` selects which of those
# meshes are shown together. The game's own hero models already do this (a body
# DMX and a gun DMX, a body and a hip holster), so adding a component does not
# need a second vmdl: it needs one more RenderMeshFile and a body-group choice
# that names it. The functions here edit that source text and nothing else; only
# ``migrate`` writes a vmdl file.
# ---------------------------------------------------------------------------

FIELD = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"(.*)"\s*,?\s*$')
RENDER_MESH_CLASS = "RenderMeshFile"
BODY_GROUP_CLASS = "BodyGroup"
BODY_GROUP_CHOICE_CLASS = "BodyGroupChoice"


class MeshListError(ModeldocError):
    pass


@dataclass(frozen=True)
class RenderMeshFile:
    name: str
    filename: str
    indent: str
    start: int
    end: int


@dataclass(frozen=True)
class BodyGroup:
    name: str
    choices: tuple[str, ...]
    meshes: tuple[str, ...]
    indent: str
    start: int
    end: int


@dataclass(frozen=True)
class MeshMerge:
    text: str
    actions: dict[str, str]
    bodygroup: str = ""
    choice: str = ""


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip("\t"))]


def _class_value(line: str) -> str:
    match = FIELD.match(line)
    if match and match.group(1) == "_class":
        return match.group(2)
    return ""


def _field_value(lines: list[str], start: int, end: int, field: str) -> str:
    for index in range(start, min(end + 1, len(lines))):
        match = FIELD.match(lines[index])
        if match and match.group(1) == field:
            return match.group(2)
    return ""


def _block_end(lines: list[str], start: int) -> int:
    depth = 0
    for index in range(start, len(lines)):
        depth += _brace_delta(lines[index])
        if depth < 0:
            raise ModeldocError(f"block-brace-underflow: line {index + 1}")
        if depth == 0:
            return index
    raise ModeldocError(f"block-has-no-close: line {start + 1}")


def _block_start(lines: list[str], class_index: int) -> int:
    for index in range(class_index - 1, -1, -1):
        stripped = lines[index].strip()
        if stripped.endswith("{"):
            return index
        if stripped:
            break
    raise ModeldocError(f"block-has-no-open: line {class_index + 1}")


def _blocks(lines: list[str], section: Section, klass: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    index = section.start
    while index <= section.end:
        if _class_value(lines[index]) == klass:
            start = _block_start(lines, index)
            end = _block_end(lines, start)
            found.append((start, end))
            index = end + 1
            continue
        index += 1
    return found


def _list_open(lines: list[str], start: int, end: int, field: str) -> int | None:
    for index in range(start, end + 1):
        stripped = lines[index].strip()
        if stripped.startswith(field) and stripped.endswith("["):
            return index
        if stripped.startswith(field):
            for follow in range(index + 1, end + 1):
                if lines[follow].strip() == "[":
                    return follow
    return None


def _list_close(lines: list[str], open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(lines)):
        depth += lines[index].count("[") - lines[index].count("]")
        if depth <= 0:
            return index
    raise ModeldocError(f"list-has-no-close: line {open_index + 1}")


def _insert_in_list(lines: list[str], open_index: int, block: list[str]) -> None:
    close = _list_close(lines, open_index)
    previous = close - 1
    while previous > open_index and not lines[previous].strip():
        previous -= 1
    if previous > open_index and not lines[previous].rstrip().endswith(","):
        lines[previous] = lines[previous].rstrip() + ","
    lines[close:close] = block


def render_mesh_files(text: str) -> list[RenderMeshFile]:
    """Every RenderMeshFile in the RenderMeshList, in source order."""
    section = sections(text).get("RenderMeshList")
    if section is None:
        return []
    lines = text.splitlines()
    found: list[RenderMeshFile] = []
    seen: set[str] = set()
    for start, end in _blocks(lines, section, RENDER_MESH_CLASS):
        name = _field_value(lines, start, end, "name")
        filename = _field_value(lines, start, end, "filename")
        if not name or name in seen:
            continue
        seen.add(name)
        found.append(RenderMeshFile(name=name, filename=filename, indent=_indent(lines[start]), start=start, end=end))
    return found


def body_groups(text: str) -> list[BodyGroup]:
    """Every BodyGroup, with its choice names and the meshes they show."""
    section = sections(text).get("BodyGroupList")
    if section is None:
        return []
    lines = text.splitlines()
    found: list[BodyGroup] = []
    for start, end in _blocks(lines, section, BODY_GROUP_CLASS):
        name = _field_value(lines, start, end, "name")
        choices: list[str] = []
        meshes: list[str] = []
        for choice_start, choice_end in _choice_blocks(lines, start, end):
            choice_name = _field_value(lines, choice_start, choice_end, "name")
            if choice_name:
                choices.append(choice_name)
            meshes.extend(_mesh_names(lines, choice_start, choice_end))
        found.append(
            BodyGroup(
                name=name,
                choices=tuple(choices),
                meshes=tuple(dict.fromkeys(meshes)),
                indent=_indent(lines[start]),
                start=start,
                end=end,
            )
        )
    return found


def _choice_blocks(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    index = start
    while index <= end:
        if _class_value(lines[index]) == BODY_GROUP_CHOICE_CLASS:
            block_start = _block_start(lines, index)
            block_end = _block_end(lines, block_start)
            found.append((block_start, block_end))
            index = block_end + 1
            continue
        index += 1
    return found


def _mesh_names(lines: list[str], start: int, end: int) -> list[str]:
    open_index = _list_open(lines, start, end, "meshes")
    if open_index is None:
        return []
    close = _list_close(lines, open_index)
    names: list[str] = []
    for line in lines[open_index + 1 : close]:
        value = line.strip().strip(",").strip('"')
        if value:
            names.append(value)
    return names


def _render_mesh_block(indent: str, name: str, filename: str) -> list[str]:
    return [
        f"{indent}{{",
        f'{indent}\t_class = "{RENDER_MESH_CLASS}"',
        f'{indent}\tname = "{name}"',
        f'{indent}\tfilename = "{filename}"',
        f"{indent}}},",
    ]


def _choice_block(indent: str, name: str, mesh: str) -> list[str]:
    return [
        f"{indent}{{",
        f'{indent}\t_class = "{BODY_GROUP_CHOICE_CLASS}"',
        f'{indent}\tname = "{name}"',
        f"{indent}\tmeshes = ",
        f"{indent}\t[",
        f'{indent}\t\t"{mesh}",',
        f"{indent}\t]",
        f"{indent}}},",
    ]


def _group_block(indent: str, name: str, mesh: str) -> list[str]:
    choice = _choice_block(indent + "\t\t", f"0_#&{mesh}", mesh)
    return [
        f"{indent}{{",
        f'{indent}\t_class = "{BODY_GROUP_CLASS}"',
        f'{indent}\tname = "{name}"',
        f"{indent}\tchildren = ",
        f"{indent}\t[",
        *[f"{indent}\t{line}" for line in choice],
        f"{indent}\t]",
        f"{indent}}},",
    ]


def add_bodygroup_section(text: str, name: str, mesh: str) -> MeshMerge:
    """Create BodyGroupList with one group and one choice for ``mesh``."""
    lines = text.splitlines()
    close = _root_close(lines)
    section_indent = "\t\t\t"
    if close > 0:
        prior = close - 1
        while prior > 0 and not lines[prior].strip():
            prior -= 1
        if not lines[prior].rstrip().endswith((",", "{")):
            lines[prior] = lines[prior].rstrip() + ","
    block = [
        f"{section_indent}{{",
        f'{section_indent}\t_class = "BodyGroupList"',
        f"{section_indent}\tchildren = ",
        f"{section_indent}\t[",
        *[f"{section_indent}\t{line}" for line in _group_block(section_indent + "\t\t", name, mesh)],
        f"{section_indent}\t]",
        f"{section_indent}}},",
    ]
    lines[close:close] = block
    return MeshMerge(text="\n".join(lines), actions={"BodyGroupList": "created"}, bodygroup=name)


def add_render_mesh_file(
    text: str,
    *,
    name: str,
    filename: str,
    bodygroup: str = "",
    replace: bool = False,
) -> MeshMerge:
    """Add one DMX-backed render mesh, and optionally a body-group choice.

    A duplicate mesh name is refused unless ``replace`` is set, because two
    RenderMeshFile entries with one name make the compiler's body-group lookup
    ambiguous. ``bodygroup`` adds the mesh to that group (creating the group or
    the whole BodyGroupList when it is absent), so a hat or a gun becomes a
    choice the game can switch instead of a second mesh that is always drawn.
    """
    name = (name or "").strip()
    filename = (filename or "").strip().replace("\\", "/")
    bodygroup = (bodygroup or "").strip()
    if not name or any(char in name for char in '"\n\r'):
        raise MeshListError(f"mesh-name-invalid: {name!r}")
    if not filename or any(char in filename for char in '"\n\r'):
        raise MeshListError(f"mesh-filename-invalid: {filename!r}")
    if bodygroup and any(char in bodygroup for char in '"\n\r'):
        raise MeshListError(f"bodygroup-name-invalid: {bodygroup!r}")
    section = sections(text).get("RenderMeshList")
    if section is None:
        raise MeshListError("render-mesh-list-missing")
    lines = text.splitlines()
    existing = next((item for item in render_mesh_files(text) if item.name == name), None)
    actions: dict[str, str] = {}
    if existing is not None:
        if not replace:
            raise MeshListError(f"render-mesh-exists: {name}")
        if existing.filename == filename:
            actions["RenderMeshList"] = "unchanged"
        else:
            for index in range(existing.start, existing.end + 1):
                if FIELD.match(lines[index]) and FIELD.match(lines[index]).group(1) == "filename":
                    lines[index] = f'{existing.indent}\tfilename = "{filename}"'
                    break
            actions["RenderMeshList"] = "replaced"
            text = "\n".join(lines)
    else:
        files = render_mesh_files(text)
        indent = files[0].indent if files else _indent(lines[section.start]) + "\t\t"
        open_index = _list_open(lines, section.start, section.end, "children")
        if open_index is None:
            raise MeshListError("render-mesh-children-list-missing")
        _insert_in_list(lines, open_index, _render_mesh_block(indent, name, filename))
        actions["RenderMeshList"] = "inserted"
        text = "\n".join(lines)

    choice = ""
    if bodygroup:
        result = ensure_bodygroup(text, bodygroup, name)
        text = result.text
        actions["BodyGroupList"] = result.actions.get("BodyGroupList", "")
        choice = result.choice
    return MeshMerge(text=text, actions=actions, bodygroup=bodygroup, choice=choice)


def ensure_bodygroup(text: str, group_name: str, mesh_name: str) -> MeshMerge:
    """Make ``mesh_name`` a choice of ``group_name``, creating what is missing."""
    group_name = (group_name or "").strip()
    mesh_name = (mesh_name or "").strip()
    if not group_name or not mesh_name:
        raise MeshListError("bodygroup-and-mesh-required")
    groups = body_groups(text)
    match = next((group for group in groups if group.name == group_name), None)
    if match is not None and mesh_name in match.meshes:
        return MeshMerge(text=text, actions={"BodyGroupList": "exists"}, bodygroup=group_name)
    if match is None:
        if not groups:
            created = add_bodygroup_section(text, group_name, mesh_name)
            return MeshMerge(
                text=created.text,
                actions={**created.actions, "BodyGroupList": "created"},
                bodygroup=group_name,
                choice=f"0_#&{mesh_name}",
            )
        section = sections(text).get("BodyGroupList")
        if section is None:
            return add_bodygroup_section(text, group_name, mesh_name)
        lines = text.splitlines()
        open_index = _list_open(lines, section.start, section.end, "children")
        if open_index is None:
            raise MeshListError("bodygroup-children-list-missing")
        indent = groups[0].indent
        _insert_in_list(lines, open_index, _group_block(indent, group_name, mesh_name))
        return MeshMerge(
            text="\n".join(lines),
            actions={"BodyGroupList": "group-inserted"},
            bodygroup=group_name,
            choice=f"0_#&{mesh_name}",
        )

    lines = text.splitlines()
    choice_indent = match.indent + "\t\t"
    choices = _choice_blocks(lines, match.start, match.end)
    if choices:
        choice_indent = _indent(lines[choices[0][0]])
    choice_name = f"{len(match.choices)}_#&{mesh_name}"
    open_index = _list_open(lines, match.start, match.end, "children")
    if open_index is None:
        raise MeshListError("bodygroup-children-list-missing")
    _insert_in_list(lines, open_index, _choice_block(choice_indent, choice_name, mesh_name))
    return MeshMerge(
        text="\n".join(lines),
        actions={"BodyGroupList": "choice-inserted"},
        bodygroup=group_name,
        choice=choice_name,
    )


def _root_close(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index] == ROOT_CLOSE:
            return index
    raise ModeldocError("modeldoc-has-no-root-children-close")


def merge(
    new_text: str,
    old_text: str,
    names: tuple[str, ...] | list[str],
) -> MergeResult:
    """Transplant named top-level sections from old into new.

    Existing new sections are replaced with the old block exactly. Missing new
    sections are appended to the root children list. Sections absent from the old
    text are recorded as absent and do not change the new document.
    """
    old_sections = sections(old_text)
    new_sections = sections(new_text)
    result = new_text.splitlines()
    actions: dict[str, dict[str, str]] = {}

    for name in names:
        if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in name):
            raise ModeldocError(f"invalid-section-name: {name!r}")
        old = old_sections.get(name)
        if old is None:
            actions[name] = {"action": "absent", "old_sha256": "", "new_sha256": ""}
            continue
        current = sections("\n".join(result))
        existing = current.get(name)
        existing_sha = section_hash(existing.text) if existing is not None else ""
        replacement = old.text.splitlines()
        if existing is not None:
            if existing.end_has_comma:
                replacement[-1] += ","
            result[existing.start : existing.end + 1] = replacement
            action = "replaced"
        else:
            close = _root_close(result)
            if close == 0 or not result[close - 1].rstrip().endswith((",", "{")):
                if close > 0:
                    result[close - 1] += ","
            block = old.text.splitlines()
            block[-1] += ","
            result[close:close] = block
            action = "inserted"
        actions[name] = {
            "action": action,
            "old_sha256": section_hash(old.text),
            "new_sha256": existing_sha,
        }

    output = "\n".join(result)
    if new_text.endswith("\n") and not output.endswith("\n"):
        output += "\n"
    final = sections(output)
    for name, action in actions.items():
        if action["action"] != "absent" and name not in final:
            raise ModeldocError(f"section-merge-lost: {name}")
        if name in final:
            action["output_sha256"] = section_hash(final[name].text)
    return MergeResult(text=output, actions=actions)
