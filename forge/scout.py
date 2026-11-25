"""The Scout port: its sources, its hero scripts, and the Dota-tools animgraph.

Three readings, each from a file that exists, none of them a guessed value:

* the mod workspace says what the port carries (TF2 Scout sources, its own
  ``heroes.vdata`` snapshot, and any animgraph document);
* the live game says what the roster ships now, through
  :func:`forge.live.parse_hero_roster`, so "update to main Deadlock" is a
  measured drift instead of a rebuild;
* the Dota 2 tools tree says which AnimGraph 2 documents exist to author from.

Nothing here parses a KV3 document, writes a vmdl, or rewrites the owner's hero
scripts. The roster is read with the same line scan the live roster already
uses, hero scripts are copied verbatim with their digest recorded, and a graph
is retargeted by replacing two named scalar fields, each of which must occur
exactly once.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import live
from .hashes import blake3_file

GRAPH_SUFFIXES = (".vnmgraph", ".vanmgrph")
ANIM_DIR_MARKERS = ("_anim", "anims", "animation")
DOTA_COMPILER = Path("game/bin/win64/resourcecompiler.exe")
DOTA_ANIMGRAPH_DIR = Path("content/dota_addons/animgraph/animgraphs")

_VARIATION = re.compile(r'(m_variationID\s*=\s*)"[^"]*"')
_SKELETON = re.compile(r'(m_skeleton\s*=\s*(?:resource:)?)"[^"]*"')
_ROOT = re.compile(r"m_nRootNodeIdx\s*=\s*(\d+)")
_PERSISTENT = re.compile(r"m_persistentNodeIndices\s*=\s*\[([^\]]*)\]")
_CLIP = re.compile(r'resource:"([^"]+\.(?:vnmclip|dmx))"')
_SEQUENCE = re.compile(r'm_sequenceName\s*=\s*"([^"]+)"')
_SEQUENCE_NOISE = (
    "_corrective_animation",
    "corrective",
    "@",
)


class ScoutError(ValueError):
    """A named refusal; the code is the first token of the message."""


def _refuse(code: str, detail: str = "") -> None:
    raise ScoutError(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class Sources:
    """What the port carries beside its hero table."""

    stem: str
    qc: str = ""
    mdl: str = ""
    smd: int = 0
    anim_smd: int = 0
    anim_dirs: tuple[str, ...] = ()
    blends: tuple[str, ...] = ()
    vpks: tuple[str, ...] = ()
    graphs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "stem": self.stem,
            "qc": self.qc,
            "mdl": self.mdl,
            "smd": self.smd,
            "anim_smd": self.anim_smd,
            "anim_dirs": list(self.anim_dirs),
            "blends": list(self.blends),
            "vpks": list(self.vpks),
            "graphs": list(self.graphs),
        }


@dataclass(frozen=True)
class HeroTable:
    path: Path
    heroes: tuple[live.Hero, ...]
    bytes: int
    blake3: str

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "heroes": len(self.heroes),
            "bytes": self.bytes,
            "blake3": self.blake3,
        }


@dataclass(frozen=True)
class Drift:
    same: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    moved: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            "same": len(self.same),
            "added": list(self.added),
            "removed": list(self.removed),
            "moved": [dict(row) for row in self.moved],
        }


@dataclass(frozen=True)
class DotaTools:
    root: Path
    compiler: Path
    graphs: tuple[Path, ...] = ()
    models: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "compiler": str(self.compiler),
            "compiler_present": self.compiler.is_file(),
            "graphs": [str(path) for path in self.graphs],
            "models": list(self.models),
        }


@dataclass(frozen=True)
class GraphDoc:
    path: Path
    schema: str
    variation: str
    skeleton: str
    root_index: int
    nodes: int
    clips: tuple[str, ...]
    sequences: tuple[str, ...]
    bytes: int

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "schema": self.schema,
            "variation": self.variation,
            "skeleton": self.skeleton,
            "root_index": self.root_index,
            "nodes": self.nodes,
            "clips": list(self.clips),
            "sequences": len(self.sequences),
            "bytes": self.bytes,
        }


def scan_sources(workspace: Path, stem: str = "scout") -> Sources:
    """What the workspace carries for one port, read from file names only."""
    root = Path(workspace)
    if not root.is_dir():
        _refuse("workspace-missing", str(root))
    lower = stem.lower()
    qc = root / f"{stem}.qc"
    mdl = root / f"{stem}.mdl"
    # One level only. A port's workspace sits on a slow drive, and the animation
    # folders are the port's own; walking every SMD below it timed out on F:.
    smd = len(list(root.glob("*.smd")))
    anim_smd = 0
    anim_dirs: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and any(marker in child.name.lower() for marker in ANIM_DIR_MARKERS):
            anim_dirs.append(child.name)
            anim_smd += len(list(child.glob("*.smd")))
    blends = tuple(sorted(path.name for path in root.glob("*.blend")))
    vpks = tuple(sorted(path.name for path in root.glob("*.vpk")))
    graphs = tuple(
        sorted(
            str(path)
            for suffix in GRAPH_SUFFIXES
            for path in root.glob(f"*{suffix}")
        )
    )
    return Sources(
        stem=stem,
        qc=qc.name if qc.is_file() else "",
        mdl=mdl.name if mdl.is_file() else "",
        smd=smd,
        anim_smd=anim_smd,
        anim_dirs=tuple(anim_dirs),
        blends=blends,
        vpks=vpks,
        graphs=graphs,
    )


def find_hero_table(workspace: Path) -> Path | None:
    """The mod's hero script snapshot, wherever the port keeps it."""
    root = Path(workspace)
    for candidate in (root / "scripts" / "heroes.vdata", root / "heroes.vdata"):
        if candidate.is_file():
            return candidate
    return None


def read_hero_table(path: Path) -> HeroTable:
    """Read the hero table with the roster's own line scan and digest its bytes."""
    path = Path(path)
    if not path.is_file():
        _refuse("hero-table-missing", str(path))
    text = path.read_text(encoding="utf-8", errors="replace")
    heroes = tuple(live.parse_hero_roster(text))
    if not heroes:
        _refuse("hero-table-empty", str(path))
    return HeroTable(
        path=path,
        heroes=heroes,
        bytes=path.stat().st_size,
        blake3=blake3_file(path),
    )


def drift(mod_heroes, live_heroes) -> Drift:
    """What the mod's snapshot no longer matches in the live roster."""
    mod = {hero.slug: hero.model_path for hero in mod_heroes}
    current = {hero.slug: hero.model_path for hero in live_heroes}
    same = tuple(sorted(slug for slug, model in mod.items() if current.get(slug) == model))
    added = tuple(sorted(slug for slug in current if slug not in mod))
    removed = tuple(sorted(slug for slug in mod if slug not in current))
    moved = tuple(
        {"slug": slug, "mod": mod[slug], "live": current[slug]}
        for slug in sorted(mod)
        if slug in current and current[slug] != mod[slug]
    )
    return Drift(same=same, added=added, removed=removed, moved=moved)


def dota_tools(root: Path | str) -> DotaTools:
    """A Dota 2 tools tree, read by the two things a graph build needs."""
    base = Path(root)
    if not base.is_dir():
        _refuse("dota-tools-missing", str(base))
    compiler = base / DOTA_COMPILER
    if not compiler.is_file():
        _refuse("dota-tools-no-compiler", str(compiler))
    graph_dir = base / DOTA_ANIMGRAPH_DIR
    if not graph_dir.is_dir():
        _refuse("dota-tools-no-animgraphs", str(graph_dir))
    graphs = tuple(sorted(graph_dir.glob("*.vanmgrph")))
    if not graphs:
        _refuse("dota-tools-animgraphs-empty", str(graph_dir))
    model_dir = base / "content/dota_addons/animgraph/models"
    models = tuple(
        sorted(str(path.relative_to(base).as_posix()) for path in model_dir.glob("*") if path.is_dir())
    ) if model_dir.is_dir() else ()
    return DotaTools(root=base, compiler=compiler, graphs=graphs, models=models)


def _list_count(text: str, match: re.Match[str]) -> int:
    numbers = [item for item in re.split(r"[,\s]+", match.group(1)) if item.strip()]
    return len(numbers)


def graph_summary(path: Path) -> GraphDoc:
    """Read one AnimGraph 2 document, in either schema the tools ship.

    A Deadlock hero graph is a **variation**: it declares ``m_variationID`` and
    ``m_skeleton`` beside a persistent node index list. The Dota 2 tools graph is
    the older authored document (``format:animgraph19``): a node manager whose
    nodes are ``key =`` blocks, and no variation field at all. Both are read; a
    document that is neither is refused rather than summarised as if it were.
    """
    path = Path(path)
    if not path.is_file():
        _refuse("graph-missing", str(path))
    text = path.read_text(encoding="utf-8", errors="replace")
    variation = _VARIATION.search(text)
    skeleton = _SKELETON.search(text)
    root = _ROOT.search(text)
    if variation is not None:
        schema = "variation"
    elif "format:animgraph19" in text:
        schema = "animgraph19"
    else:
        _refuse("graph-schema-unknown", path.name)
    if schema == "variation" and skeleton is None:
        _refuse("graph-skeleton-field-missing", path.name)
    nodes = 0
    persistent = _PERSISTENT.search(text)
    if persistent is not None:
        nodes = _list_count(text, persistent) + 1
    else:
        nodes = len(re.findall(r"^\t{4}key =", text, re.MULTILINE))
    skeleton_path = re.sub(r'^m_skeleton\s*=\s*(?:resource:)?"', '', skeleton.group(0))[:-1] if skeleton else ""
    # The skeleton is declared as a resource too; it is not a clip.
    clips = sorted({value for value in _CLIP.findall(text) if value != skeleton_path})
    return GraphDoc(
        path=path,
        schema=schema,
        variation=re.sub(r'^m_variationID\s*=\s*"|"$', "", variation.group(0)) if variation else "",
        skeleton=skeleton_path,
        root_index=int(root.group(1)) if root else -1,
        nodes=nodes,
        clips=tuple(clips),
        sequences=sequence_names(text),
        bytes=len(text.encode("utf-8")),
    )


def retarget_graph(text: str, *, variation: str, skeleton: str, label: str = "") -> str:
    """Point one graph at another skeleton and variation, by name only.

    Both fields must occur exactly once. A second occurrence would mean the
    document declares more than one skeleton; replacing the first would be a
    guess. The node layout, control parameters and clips are left untouched.
    """
    variation = str(variation or "").strip()
    skeleton = str(skeleton or "").strip().replace("\\", "/")
    if not variation:
        _refuse("graph-variation-empty")
    if not skeleton:
        _refuse("graph-skeleton-empty")
    if _VARIATION.search(text or "") is None:
        # The Dota tools document has no variation field to point anywhere: it is
        # the older authored schema, not a Deadlock variation. Translating it is
        # an editor job, not a two-field replacement.
        _refuse("graph-schema-not-retargetable", "no m_variationID in this document")
    for field_name, pattern in (("variation", _VARIATION), ("skeleton", _SKELETON)):
        found = pattern.findall(text or "")
        if not found:
            _refuse(f"graph-{field_name}-field-missing")
        if len(found) > 1:
            _refuse(f"graph-{field_name}-field-ambiguous", f"{len(found)} occurrences")
    body = text
    body = _VARIATION.sub(lambda match: f'{match.group(1)}"{variation}"', body, count=1)
    body = _SKELETON.sub(lambda match: f'{match.group(1)}"{skeleton}"', body, count=1)
    if label:
        stamp = f"// retargeted by deadlock-model-forge: {label}\n"
        body = stamp + body
    return body


_VARIATION_ID = re.compile(r'm_variationID\s*=\s*"([^"]+)"')
_CLIP_FIELD = re.compile(r'(m_clip\s*=\s*")[^"]*"')


_OVERRIDES = re.compile(r"m_overrides\s*=\s*$")
_VARIATIONS_ARRAY = re.compile(r"m_variations\s*=\s*$")


def _array_entries(lines: list[str], start: int) -> tuple[list[tuple[int, int]], int]:
    """The `{ … }` entries of the array opening at ``start``, and the array's close line."""
    depth = 0
    close_at = start
    for position in range(start, len(lines)):
        depth += lines[position].count("[") - lines[position].count("]")
        if depth == 0:
            close_at = position
            break
    entries: list[tuple[int, int]] = []
    depth = 0
    entry_start = None
    for offset in range(start, close_at + 1):
        depth += lines[offset].count("{") - lines[offset].count("}")
        if lines[offset].strip() == "{" and entry_start is None:
            entry_start = offset
        elif depth == 0 and entry_start is not None:
            entries.append((entry_start, offset))
            entry_start = None
    return entries, close_at


def _comma(line: str) -> str:
    if line.rstrip().endswith(","):
        return line
    return line.rstrip() + "," + ("\n" if not line.endswith("\n") else "")


def add_variation_overrides(
    text: str,
    *,
    target: str,
    skeleton: str = "",
    clip_from: str = "",
    clip_to: str = "",
    label: str = "",
) -> tuple[str, dict]:
    """Add a hero to a fused AnimGraph 2 document, at every animation-pose node.

    A shipped ``hero_aim.vnmgraph`` is fused: the base pose data is one hero's clips
    and every other hero is an entry in each node's ``m_overrides`` array
    (``m_variationID`` beside ``m_pData.m_clip``). That is why dropping a
    ``hero_aim.vnmgraph+scout.vnmgraph`` file beside it compiles nothing: the
    compiler reads the document, and the document never names the new variation.
    Adding a hero is therefore one cloned override per pose node, not one file.

    Each clone is the node's last override with the id replaced and the clip path
    moved to ``clip_to``. A node with no overrides is counted, not invented: a
    variation that is missing at one node is a hole the compiler will resolve from
    the defaults, and the report says so.
    """
    lines = text.splitlines(keepends=True)
    if _VARIATION_ID.search(text) is None:
        _refuse("variation-id-absent", "this document declares no m_variationID")
    if any(value == target for value in _VARIATION_ID.findall(text)):
        _refuse("variation-already-present", target)
    plan = {"target": target, "clip_dir": clip_to, "nodes": 0, "inserted": 0, "nodes_without_overrides": 0, "clips": []}
    out: list[str] = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        if not _OVERRIDES.match(line.strip()) or index + 1 >= total:
            out.append(line)
            index += 1
            continue
        # The key line itself belongs in the output; without it the array below is
        # a bare `[` and the compiler stops at "Invalid member name '['".
        out.append(line)
        open_at = index + 1
        while open_at < total and lines[open_at].strip() != "[":
            out.append(lines[open_at])
            open_at += 1
        if open_at >= total:
            _refuse("overrides-unreadable", f"m_overrides at line {index + 1} opens no array")
        depth = 0
        close_at = open_at
        for position in range(open_at, total):
            depth += lines[position].count("[") - lines[position].count("]")
            if depth == 0:
                close_at = position
                break
        plan["nodes"] += 1
        body = lines[open_at : close_at + 1]
        entries = []
        depth = 0
        entry_start = None
        for offset, mark in enumerate(body):
            depth += mark.count("{") - mark.count("}")
            if mark.strip() == "{" and entry_start is None:
                entry_start = offset
            elif depth == 0 and entry_start is not None:
                entries.append((entry_start, offset))
                entry_start = None
        if not entries:
            plan["nodes_without_overrides"] += 1
            out.extend(body)
            out.append(lines[close_at])
            index = close_at + 1
            continue
        begin, finish = entries[-1]
        clone = []
        for mark in body[begin : finish + 1]:
            if _VARIATION_ID.search(mark):
                clone.append(_VARIATION_ID.sub(f'm_variationID = "{target}"', mark))
                continue
            clip_match = _CLIP_FIELD.search(mark)
            if clip_match and clip_to:
                original = mark.split('"', 1)[1].rsplit('"', 1)[0]
                name = Path(original.replace("\\", "/")).name
                clone.append(_CLIP_FIELD.sub(f'{clip_match.group(1)}{clip_to.rstrip("/")}/{name}"', mark))
                plan["clips"].append({"from": original, "to": f'{clip_to.rstrip("/")}/{name}'})
                continue
            clone.append(mark)
        if not clone[-1].rstrip().endswith(","):
            clone[-1] = clone[-1].rstrip() + "," + ("\n" if not clone[-1].endswith("\n") else "")
        if not body[finish].rstrip().endswith(","):
            body[finish] = body[finish].rstrip() + "," + ("\n" if not body[finish].endswith("\n") else "")
        out.extend(body[: finish + 1])
        out.extend(clone)
        out.extend(body[finish + 1 :])
        plan["inserted"] += 1
        index = close_at + 1
    # Past the node overrides the document keeps a variation hierarchy: one
    # `{ m_ID, m_parentID, m_skeleton }` entry per hero. Without an entry here the
    # overrides above are data no variation ever selects, and the compiler emits
    # one output per listed variation and none for the new hero.
    plan["hierarchy"] = ""
    hierarchy_at = next(
        (i for i, mark in enumerate(out) if _VARIATIONS_ARRAY.match(mark.strip())), None
    )
    if hierarchy_at is None:
        _refuse("variation-hierarchy-absent", "no m_variations array in this document")
    open_at = hierarchy_at + 1
    while open_at < len(out) and out[open_at].strip() != "[":
        open_at += 1
    entries, close_at = _array_entries(out, open_at)
    if not entries:
        _refuse("variation-hierarchy-empty", "m_variations lists no entry to clone")
    begin, finish = entries[-1]
    clone = []
    for mark in out[begin : finish + 1]:
        if re.match(r"\s*m_ID\s*=", mark):
            clone.append(re.sub(r'm_ID\s*=\s*"[^"]*"', f'm_ID = "{target}"', mark))
            continue
        if skeleton and re.match(r"\s*m_skeleton\s*=", mark):
            clone.append(re.sub(r'm_skeleton\s*=\s*"[^"]*"', f'm_skeleton = "{skeleton}"', mark))
            continue
        clone.append(mark)
    out[finish] = _comma(out[finish])
    clone[-1] = _comma(clone[-1])
    out[finish + 1 : finish + 1] = clone
    plan["hierarchy"] = f"{target} under {skeleton or 'the parent skeleton'}"
    plan["label"] = label
    return "".join(out), plan


def clip_basenames(clips) -> dict[str, str]:
    """Group a graph's clip references by file name, keeping their paths."""
    rows: dict[str, str] = {}
    for value in clips:
        rows.setdefault(Path(value).stem.lower(), value)
    return rows


def sequence_names(text: str) -> tuple[str, ...]:
    """Every sequence a graph asks its model to play.

    A ``vanmgrph`` does not name files; it names the model's own sequences
    (``walkn``, ``turn_left_90``), so a port carries the animation only when its
    model declares a sequence with that name. Reading the names is the whole
    join key, which is why the bake is a mapping problem first.
    """
    return tuple(sorted({name.strip() for name in _SEQUENCE.findall(text or "") if name.strip()}))


def normalise_sequence(name: str) -> str:
    """A comparable form, without the prefixes the two games add."""
    value = str(name or "").strip().lower()
    for noise in _SEQUENCE_NOISE:
        value = value.replace(noise, "")
    value = value.replace(" ", "_")
    while "__" in value:
        value = value.replace("__", "_")
    return value.strip("_")


def source_sequences(workspace: Path) -> tuple[str, ...]:
    """The port's own animation names, read from its SMD file names."""
    root = Path(workspace)
    if not root.is_dir():
        _refuse("workspace-missing", str(root))
    names = set()
    for child in root.iterdir():
        if child.is_dir() and any(marker in child.name.lower() for marker in ANIM_DIR_MARKERS):
            names.update(path.stem for path in child.glob("*.smd"))
    return tuple(sorted(names))


_QC_SEQUENCE = re.compile(r'^\s*\$sequence\s+"([^"]+)"', re.IGNORECASE | re.MULTILINE)
_MODEL_NAME = re.compile(r'(m_modelName\s*=\s*)"[^"]*"')
_SEQUENCE_VALUE = re.compile(r'(m_sequenceName\s*=\s*)"[^"]*"')


def port_sequences(workspace: Path) -> tuple[str, ...]:
    """The sequences the port's own QC files declare, in declaration order.

    This is the port's authority on what its model can play: an animation SMD on
    disk is not a sequence until a ``$sequence`` block names it. Only the QC files
    at the workspace root are read, so a slow drive costs one directory listing.
    """
    root = Path(workspace)
    if not root.is_dir():
        _refuse("workspace-missing", str(root))
    names: list[str] = []
    seen: set[str] = set()
    for qc in sorted(root.glob("*.qc")):
        for name in _QC_SEQUENCE.findall(qc.read_text(encoding="utf-8", errors="replace")):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return tuple(names)


def retarget_sequences(text: str, *, model: str = "", sequences=(), label: str = "") -> tuple[str, dict]:
    """Point a Dota animgraph19 graph at a model and at the port's own sequences.

    A ``vanmgrph`` names its clips by sequence name, so a graph bound to a port
    has to carry that port's names. The graph's sequence **slots** are filled in
    sorted order from ``sequences`` and the pairing is returned as proposed: which
    slot should hold which clip is an authoring decision, and this records the
    choice instead of hiding it. Extra graph occurrences reuse the slot's name,
    so a document that asks for ``turn_right_180`` in six places stays consistent.
    """
    if "format:animgraph19" not in (text or ""):
        _refuse("graph-schema-not-animgraph19", "no animgraph19 header")
    names = list(sequences)
    occurrences = [match.group(0) for match in _SEQUENCE_VALUE.finditer(text)]
    slots = []
    for raw in occurrences:
        name = raw.split('"', 1)[1].rsplit('"', 1)[0]
        if name not in slots:
            slots.append(name)
    if not occurrences:
        _refuse("animgraph-sequences-absent", "no m_sequenceName in this document")
    if len(names) < len(slots):
        _refuse(
            "animgraph-sequences-short",
            f"graph has {len(slots)} sequence slots, the port declares {len(names)}",
        )
    mapping = {old: names[index] for index, old in enumerate(slots)}
    body = _SEQUENCE_VALUE.sub(
        lambda match: f'{match.group(1)}"{mapping[match.group(0).split(chr(34), 1)[1].rsplit(chr(34), 1)[0]]}"',
        text,
    )
    model_state = "not-requested"
    if model:
        found = _MODEL_NAME.findall(body)
        if len(found) != 1:
            _refuse("animgraph-model-field-ambiguous", f"{len(found)} m_modelName fields")
        body = _MODEL_NAME.sub(lambda match: f'{match.group(1)}"{model}"', body, count=1)
        model_state = model
    report = {
        "slots": len(slots),
        "renamed": len(slots),
        "occurrences": len(occurrences),
        "mapping": {old: mapping[old] for old in slots},
        "proposed": True,
        "model": model_state,
        "label": label,
    }
    return body, report


def bind_sequences(graph_names, source_names) -> dict:
    """Join graph sequence names to the port's animations, and name the gaps."""
    source = {normalise_sequence(name): name for name in source_names}
    rows = []
    unbound = []
    for name in graph_names:
        match = source.get(normalise_sequence(name))
        if match is None:
            unbound.append(name)
        rows.append({"graph": name, "source": match or "", "bound": match is not None})
    return {
        "graph_sequences": len(graph_names),
        "source_sequences": len(source_names),
        "bound": len(graph_names) - len(unbound),
        "unbound": unbound,
        "rows": rows,
    }
