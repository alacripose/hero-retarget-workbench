"""File copies that survive paths longer than Windows' legacy 260 limit.

Blender's bundled Python cannot open a destination whose full path crosses
MAX_PATH, even when the registry enables long paths.  The workbench stages old
addons below a project folder, so a material path can become long enough for
``shutil.copyfile`` to report ``[Errno 2]`` for a file that exists.  The extended
prefix is only used on Windows; every other platform receives the plain path.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def native_path(path: str | Path) -> str:
    """Return a path the Windows API can open without the legacy limit."""
    text = os.path.abspath(str(path))
    if os.name != "nt":
        return text
    if text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def ensure_dir(path: str | Path) -> None:
    os.makedirs(native_path(path), exist_ok=True)


def copy_file(source: str | Path, destination: str | Path) -> None:
    """Copy one file, creating its parent and using an extended path on Windows."""
    source_text = native_path(source)
    if not os.path.isfile(source_text):
        raise FileNotFoundError(str(source))
    ensure_dir(Path(destination).parent)
    shutil.copyfile(source_text, native_path(destination))


def walk_files(root: str | Path):
    """Yield ``(absolute path, relative path)`` below ``root``, long paths included."""
    root = Path(root)
    native_root = native_path(root)
    if not os.path.isdir(native_root):
        return
    for current, _folders, files in os.walk(native_root):
        relative_dir = os.path.relpath(current, native_root)
        for name in sorted(files):
            relative = Path(name) if relative_dir == "." else Path(relative_dir) / name
            yield Path(current) / name, relative


def copy_tree(source: str | Path, destination: str | Path, cancel=None) -> int:
    """Copy every file below ``source`` into ``destination``; return the count.

    ``cancel`` is an optional object with a ``cancelled`` property. Checking it
    between files makes a long CSDK stage stop without waiting for the copy to
    finish; the compiler itself is cancelled where its subprocess is attached.
    """
    copied = 0
    for path, relative in walk_files(source):
        if cancel is not None and cancel.cancelled:
            raise RuntimeError("copy-cancelled")
        copy_file(path, Path(destination) / relative)
        copied += 1
    return copied
