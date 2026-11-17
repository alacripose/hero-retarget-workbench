"""AnimGraph 2 clip documents and the compiler handoff.

The game plays ``.vnmclip_c`` clips, not the preview DMX in the model folder.
This module plans the pair (the DMX a clip already points at, and the
``.vnmclip`` document that names it), rewrites only the skeleton source field,
and invokes CSDK13's compiler on those documents.  It never decodes a compiled
resource and it never packs a ``.vnmskel_c``: the model's own skeleton carries
the new tail bones, and only the clip documents are shipped.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

SOURCE_FIELD = re.compile(r'm_sourceFilename\s*=\s*"([^"]+)"')
SOURCE_LINE = re.compile(r'm_sourceFilename\s*=\s*"[^"]*"')


class AnimGraphError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClipDoc:
    """One gameplay clip: its document, the DMX it samples, and its label."""

    label: str
    vnmclip: Path
    source_relative: str
    source: Path
    preview: Path | None


@dataclass(frozen=True)
class CompileOutcome:
    document: Path
    output: Path
    returncode: int
    log: Path
    stdout: str = ""
    stderr: str = ""


def source_filename(text: str) -> str | None:
    match = SOURCE_FIELD.search(text or "")
    return match.group(1).replace("\\", "/").lstrip("/") if match else None


def read_source(document: Path) -> str | None:
    try:
        return source_filename(Path(document).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def documents(hero_root: Path | str, content_root: Path | str) -> list[ClipDoc]:
    """Every gameplay clip under ``<hero_root>/clips`` with a readable source.

    The document's own ``m_sourceFilename`` is authoritative: Shiv's
    ``weapon_stand_idle.vnmclip`` points at ``dmx/animation/primary_idle.dmx``,
    not at the preview clip of the same name.  A document whose source is
    missing is skipped instead of being pointed at a guessed file.
    """
    root = Path(hero_root)
    base = Path(content_root)
    rows: list[ClipDoc] = []
    clip_dir = root / "clips"
    if not clip_dir.is_dir():
        return rows
    for document in sorted(clip_dir.glob("*.vnmclip")):
        if document.name.lower().endswith("_c"):
            continue
        relative = read_source(document)
        if not relative:
            continue
        # Keep the caller's base spelling: resolving here expanded Windows 8.3 temp paths on CI
        # (`RUNNER~1`) into long names, so the returned source no longer equalled the path the
        # caller built.  The existence check is the only place the resolved form matters.
        source = base / relative
        if not (base / relative).is_file():
            continue
        preview = clip_dir / f"{document.stem}.dmx"
        rows.append(
            ClipDoc(
                label=document.stem,
                vnmclip=document,
                source_relative=relative,
                source=source,
                preview=preview if preview.is_file() else None,
            )
        )
    return rows


def _list_end(text: str, start: int) -> int:
    index = text.index("[", start)
    depth = 0
    for position in range(index, len(text)):
        if text[position] == "[":
            depth += 1
        elif text[position] == "]":
            depth -= 1
            if depth == 0:
                return position
    raise ValueError("unterminated-list")


def point_skeleton(text: str, source_relative: str) -> str:
    """Point one ``.vnmskel`` at another skeleton DMX without changing its bones."""
    if not source_relative:
        raise AnimGraphError("skeleton-source-empty")
    if SOURCE_FIELD.search(text or "") is None:
        raise AnimGraphError("vnmskel-source-field-missing")
    return SOURCE_LINE.sub(f'm_sourceFilename = "{source_relative}"', text, count=1)


def prepare_skeleton(text: str, source_relative: str, tail_names: list[str]) -> str:
    """Point one ``.vnmskel`` at a tail-bearing skeleton and widen body masks.

    Only the fields the compiler needs are changed.  The tail is added to both
    the high-LOD set and every mask that already owns ``pelvis``; upper-body
    masks are left alone so a tail does not detach from the lower body during an
    aim or cast layer.
    """
    if not tail_names:
        raise AnimGraphError("tail-names-empty")
    result = SOURCE_LINE.sub(f'm_sourceFilename = "{source_relative}"', text, count=1)
    marker = re.search(r"m_highLODBones\s*=", result)
    if marker is None:
        raise AnimGraphError("vnmskel-high-lod-list-missing")
    end = _list_end(result, marker.end())
    insertion = "".join(f'\n\t\t"{name}",' for name in tail_names) + "\n\t"
    result = result[:end] + insertion + result[end:]

    masks = re.search(r"m_boneMaskSetDefinitions\s*=", result)
    if masks is None:
        raise AnimGraphError("vnmskel-bone-mask-list-missing")
    search_from = masks.end()
    matches = list(re.finditer(r'm_ID = "([^"]+)"', result[search_from:]))
    for match in reversed(matches):
        start = search_from + match.start()
        end = result.find("\n\t\t},", start)
        if end < 0:
            end = len(result)
        block = result[start:end]
        if '"pelvis"' not in block:
            continue
        ids_match = re.search(r"m_boneIDs\s*=", result[start:end])
        weights_match = re.search(r"m_weights\s*=", result[start:end])
        if ids_match is None or weights_match is None:
            continue
        ids_end = _list_end(result, start + ids_match.end())
        weights_end = _list_end(result, start + weights_match.end())
        # Weights sit after the IDs, so insert from the end first and keep the
        # earlier IDs offset valid for the second insertion.
        addition = "".join("\n\t\t\t\t\t1.0," for _ in tail_names)
        result = result[:weights_end] + addition + "\n" + result[weights_end:]
        addition = "".join(f'\n\t\t\t\t\t"{name}",' for name in tail_names)
        result = result[:ids_end] + addition + "\n" + result[ids_end:]
    return result


def compile_documents(
    env,
    content_addon: Path,
    rows: list[ClipDoc],
    *,
    log_dir: Path,
    timeout: int = 300,
) -> list[CompileOutcome]:
    """Run ``resourcecompiler`` on each document, one process per clip."""
    if env.resourcecompiler is None or not Path(env.resourcecompiler).is_file():
        raise AnimGraphError("resourcecompiler-missing: choose the CSDK13 root in Setup")
    if env.csdk_gameinfo is None:
        raise AnimGraphError("csdk-gameinfo-missing: CSDK13 game/citadel/gameinfo.gi was not found")
    content = Path(content_addon)
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    outcomes: list[CompileOutcome] = []
    for row in rows:
        document = Path(row.vnmclip)
        if not document.is_file():
            raise AnimGraphError(f"clip-document-missing: {document}")
        command = [
            str(env.resourcecompiler),
            "-nop4",
            "-f",
            "-game",
            str(Path(env.csdk_gameinfo).parent),
            "-i",
            str(document.resolve()),
        ]
        log = log_dir / f"vnmclip-{row.label}.log"
        result = subprocess.run(
            command,
            cwd=str(content),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        log.write_text(
            "$ " + " ".join(command) + "\n\n" + result.stdout + (("\n" + result.stderr) if result.stderr else ""),
            encoding="utf-8",
        )
        output = document.with_name(document.name + "_c")
        outcomes.append(
            CompileOutcome(
                document=document,
                output=output,
                returncode=result.returncode,
                log=log,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        )
    return outcomes


def compiled_outputs(addon_root: Path, content_addon: Path, rows: list[ClipDoc]) -> list[Path]:
    root = Path(addon_root)
    content = Path(content_addon)
    return [
        root / row.vnmclip.relative_to(content).with_name(row.vnmclip.name + "_c")
        for row in rows
    ]
