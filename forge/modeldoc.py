"""Read and transplant top-level modeldoc sections without rebuilding a vmdl.

The compiler consumes a modeldoc source file whose root node has top-level child
blocks at a fixed tab indentation. A migration needs to carry a handful of those
blocks (cloth, physics, and optionally a custom render mesh list) from an old
addon into a current game model. This module finds those blocks by their exact
source text so their contents are copied, never interpreted or regenerated.
"""
from __future__ import annotations

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


def section_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


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
