"""Build the hero graph variations Deadlock actually loads for a hero model.

The binding is in the model, not the hero table: every shipped hero model carries an
`AnimGraph2List` whose `DefaultAnimGraph2` names `animgraphs/animgraph2/hero/hero.vnmgraph+<hero>.vnmgraph`,
and the compiled model repeats that path as `m_sAG2HeroPawnAnimGraph` with `m_bUseAG2HeroGraph = true`
(decompiled from `models/heroes_wip/inferno/inferno.vmdl_c`). A model without the list loads no hero
graph at all, which is what the first live session showed for `scout_body.vmdl` before this tool existed.

A `+hero.vnmgraph` slice cannot be compiled directly: the compiler refuses a `+` in the input name
("Non-fused-child compiles cannot contain fused delimiter '+'"). The slices are produced from the fused
base (`hero.vnmgraph_c`), so this tool clones the fused base with one existing variation renamed to
`scout`, retargets that variation's skeleton and clips, compiles the fused document, and keeps only the
`+scout.vnmgraph_c` slice the compiler emits. It walks every subgraph the fused hero graph names, so the
whole family the engine can reach is built, not just the root.

  python tools/scout_hero_graph.py build
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSDK = Path("C:/Users/ala/Downloads/Reduced_CSDK_13")
ADDON = "scout_port"
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-hero-graph.json"
WORK = ROOT / "artifacts" / "scout-hero" / "hero-graph"
SOURCE_VARIATION = "abrams"
TARGET_VARIATION = "scout"
SCOUT_SKELETON = "models/heroes_wip/scout/scout.vnmskel"
CLIPS = {
    "aim_run": "models/heroes_wip/scout/clips/scout_aimrun.vnmclip",
    "aim_idle": "models/heroes_wip/scout/clips/scout_aimidle.vnmclip",
    "attack": "models/heroes_wip/scout/clips/scout_attack.vnmclip",
    "reload": "models/heroes_wip/scout/clips/scout_reload.vnmclip",
}
REFERENCE = re.compile(r'animgraphs/animgraph2/hero/(?:(?:abrams|scout)/)?([a-z0-9_]+)\.vnmgraph(?:\+[a-z0-9_]+)?')


class GraphError(Exception):
    """A refusal that names its code, so the caller can report it instead of a traceback."""


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _map_clip(stem: str) -> str:
    lowered = stem.lower()
    if "reload" in lowered:
        return CLIPS["reload"]
    if "attack" in lowered or "fire" in lowered or "shoot" in lowered:
        return CLIPS["attack"]
    if "run" in lowered or "walk" in lowered:
        return CLIPS["aim_run"]
    return CLIPS["aim_idle"]


def retarget(text: str) -> tuple[str, dict]:
    """Rename the abrams variation to scout, retarget its skeleton, and point its clips at Scout's."""
    text = text.replace("models/heroes_wip/abrams/", "models/heroes_wip/scout/")
    text = text.replace("/abrams/abrams_", "/scout/scout_")
    text = text.replace(f"+{SOURCE_VARIATION}.vnmgraph", f"+{TARGET_VARIATION}.vnmgraph")
    text = text.replace(f'm_ID = "{SOURCE_VARIATION}"', f'm_ID = "{TARGET_VARIATION}"')
    text = text.replace(f'm_variationID = "{SOURCE_VARIATION}"', f'm_variationID = "{TARGET_VARIATION}"')
    count = {"clips": 0, "skeleton": text.count("models/heroes_wip/scout/scout.vnmskel")}

    def clip(match: re.Match[str]) -> str:
        count["clips"] += 1
        return _map_clip(Path(match.group(1)).stem)

    text = re.sub(r'"(models/heroes_wip/scout/clips/[^"]+\.vnmclip)"', clip, text)
    return text, count


BONE_MAP = {
    "head": "bip_head",
    "root_motion": "bip_pelvis",
    "weapon": "weapon_bone",
    "weaponPivot": "weapon_bone",
    "weaponHand_L": "weapon_bone_L",
    "weaponHand_R": "weapon_bone",
    "leg_L_IKTARGET": "bip_foot_L",
    "leg_R_IKTARGET": "bip_foot_R",
    "baba_head": "bip_head",
    "baba_hand_R": "bip_hand_R",
    "weapon_hand_L": "weapon_bone_L",
    "weapon_hand_R": "weapon_bone",
    "crossbow": "weapon_bone",
    "offhand": "weapon_bone",
    "magazine": "weapon_bone",
    "umbrella": "weapon_bone",
    "bag_0": "bip_packmiddle",
    "hat_0": "bip_head",
    "jar_root": "bip_pelvis",
}


def _skeleton_names(csdk: Path) -> set[str]:
    """Scout's bone names, read from the compiled skeleton this addon ships."""
    skeleton = csdk / "game" / "citadel_addons" / ADDON / "models" / "heroes_wip" / "scout" / "scout.vnmskel_c"
    if not skeleton.is_file():
        raise GraphError(f"hero-graph-skeleton-missing: {skeleton}")
    document = _decompile(skeleton, WORK / "src" / "scout.vnmskel")
    match = re.search(r'm_highLODBones =\s*\[(.*?)\]', document.read_text(encoding="utf-8", errors="replace"), re.S)
    names = set(re.findall(r'"([^"]+)"', match.group(1))) if match else set()
    if "bip_head" not in names:
        raise GraphError(f"hero-graph-skeleton-empty: {document}")
    names.add("bip_head")
    return names


def retarget_bones(text: str, names: set[str]) -> tuple[str, dict]:
    """Rename abrams bone references to Scout's `bip_` skeleton, or refuse an unmappable one."""
    counts = {"bones": 0, "unmapped": []}

    def bone(match: re.Match[str]) -> str:
        key, name = match.group(1), match.group(2)
        if name in names:
            return match.group(0)
        target = BONE_MAP.get(name) or (f"bip_{name}" if f"bip_{name}" in names else "")
        if not target:
            counts["unmapped"].append(name)
            return match.group(0)
        counts["bones"] += 1
        return f'{key} = "{target}"'

    text = re.sub(r'(m_(?:boneName|chainEndBoneName|rootBoneName)) = "([^"]+)"', bone, text)
    if counts["unmapped"]:
        raise GraphError(f"hero-graph-bone-unmapped: {sorted(set(counts['unmapped']))}")
    return text, counts


def _filter_ids(text: str, key: str, keep: set[str]) -> tuple[str, int]:
    """Drop every entry in a `key = [ … ]` list whose variation ID is not kept.

    A fused document names every hero. Compiling it standalone needs every hero's skeleton, which a
    reduced CSDK does not carry, so the family is trimmed to the default and Scout entries the engine
    will actually ask for; the trim is what makes the document self-consistent against Scout's
    skeleton instead of failing with “No chain end bone set for variation: Default”.
    """
    pattern = re.compile(rf'{key}\s*=\s*\n?\s*\[')
    removed = 0
    position = 0
    while True:
        match = pattern.search(text, position)
        if not match:
            return text, removed
        opening = text.index("[", match.end() - 1)
        depth = 0
        index = opening
        while index < len(text):
            character = text[index]
            if character == "[":
                depth += 1
            elif character == "]":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        inner = text[opening + 1 : index]
        entries: list[str] = []
        start = None
        braces = 0
        for offset, character in enumerate(inner):
            if character == "{":
                if braces == 0:
                    start = offset
                braces += 1
            elif character == "}":
                braces -= 1
                if braces == 0 and start is not None:
                    entries.append(inner[start : offset + 1])
                    start = None
        kept = []
        for entry in entries:
            ids = re.findall(r'm_(?:variationID|ID)\s*=\s*"([^"]*)"', entry)
            if any(value in keep for value in ids):
                kept.append(entry)
            else:
                removed += 1
        replacement = "[\n" + ",\n".join(kept) + "\n\t\t\t\t\t\t\t\t\t]"
        text = text[: opening] + replacement + text[index + 1 :]
        position = opening + len(replacement)


def _decompile(compiled: Path, into: Path) -> Path:
    """Decompile one fused document. S2V treats an `-o` path ending in `.vnmgraph` as the file itself."""
    if into.is_dir():
        shutil.rmtree(into)
    elif into.exists():
        into.unlink()
    subprocess.run(
        [str(S2V), "-i", str(compiled), "-d", "-o", str(into)],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
    )
    dumped = [into] if into.is_file() else sorted(into.rglob("*.vnmgraph")) if into.is_dir() else []
    if not dumped:
        raise GraphError(f"hero-graph-decompile-empty: {compiled}")
    return dumped[0]


def _compile(compiler: Path, content: Path, document: Path) -> tuple[str, list[str]]:
    result = subprocess.run(
        [
            str(compiler),
            "-nop4",
            "-f",
            "-game",
            str(content.parents[2] / "game" / "citadel"),
            "-i",
            str(document.resolve()),
        ],
        cwd=str(content),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=1800,
    )
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    ok_line = next((line for line in lines if line.startswith(("OK:", "ERROR:"))), lines[-1] if lines else "")
    return ok_line, lines


def _family(csdk: Path) -> list[dict]:
    """Transform the fused hero graph and every subgraph it names, compile each, keep the +scout slices."""
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    if not compiler.is_file():
        raise GraphError(f"hero-graph-compiler-missing: {compiler}")
    hero_dir = csdk / "game" / "citadel" / "animgraphs" / "animgraph2" / "hero"
    content = csdk / "content" / "citadel_addons" / ADDON
    src_root = WORK / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    skeleton_names = _skeleton_names(csdk)
    rows: list[dict] = []
    queue: list[tuple[str, str]] = [("variation", "hero"), ("variation", "hero_ui")]
    done: set[tuple[str, str]] = set()
    while queue:
        kind, name = queue.pop(0)
        if (kind, name) in done:
            continue
        done.add((kind, name))
        if kind == "variation":
            fused = hero_dir / f"{name}.vnmgraph_c"
            relative = Path(f"{name}.vnmgraph")
            produced = csdk / "game" / "citadel_addons" / ADDON / "animgraphs" / "animgraph2" / "hero" / f"{name}.vnmgraph+{TARGET_VARIATION}.vnmgraph_c"
        else:
            stem = name.removeprefix("scout_")
            fused = hero_dir / SOURCE_VARIATION / f"{SOURCE_VARIATION}_{stem}.vnmgraph_c"
            relative = Path(TARGET_VARIATION) / f"{name}.vnmgraph"
            produced = csdk / "game" / "citadel_addons" / ADDON / "animgraphs" / "animgraph2" / "hero" / relative.with_suffix(".vnmgraph_c")
        if not fused.is_file():
            raise GraphError(f"hero-graph-source-missing: {fused}")
        decompiled = _decompile(fused, src_root / relative.name)
        transformed, counts = retarget(decompiled.read_text(encoding="utf-8", errors="replace"))
        transformed, bone_counts = retarget_bones(transformed, skeleton_names)
        counts.update(bone_counts)
        transformed, overrides_removed = _filter_ids(transformed, "m_overrides", {TARGET_VARIATION})
        transformed, variations_removed = _filter_ids(transformed, "m_variations", {"Default", TARGET_VARIATION})
        transformed = re.sub(r'm_skeleton = "[^"]+"', f'm_skeleton = "{SCOUT_SKELETON}"', transformed)
        counts["variations_pruned"] = overrides_removed + variations_removed
        document = content / "animgraphs" / "animgraph2" / "hero" / relative
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_text(transformed, encoding="utf-8", newline="\n")
        ok_line, lines = _compile(compiler, content, document)
        if not ok_line.startswith("OK") or not produced.is_file():
            error = next((line for line in lines if "ERROR" in line or "Unable" in line), ok_line)
            raise GraphError(f"hero-graph-compile-failed: {name}: {error}")
        rows.append(
            {
                "base": name,
                "source": str(fused),
                "document": str(document),
                "target": str(produced.relative_to(csdk / "game")),
                "bytes": produced.stat().st_size,
                "md5": _md5(produced),
                "counts": counts,
                "ok_line": ok_line,
            }
        )
        for ref in REFERENCE.finditer(transformed):
            reference = ref.group(0)
            base = ref.group(1)
            if f"+{TARGET_VARIATION}.vnmgraph" in reference:
                if ("variation", base) not in done:
                    queue.append(("variation", base))
            elif "/scout/" in reference and ("standalone", base) not in done:
                queue.append(("standalone", base))
    return rows


def build(csdk: Path = CSDK) -> dict:
    rows = _family(csdk)
    report = {
        "schema": "dmf.scout-hero-graph/1",
        "generated": _stamp(),
        "csdk": str(csdk),
        "source_variation": SOURCE_VARIATION,
        "target_variation": TARGET_VARIATION,
        "skeleton": SCOUT_SKELETON,
        "documents": rows,
        "counts": {
            "documents": len(rows),
            "bytes": sum(row["bytes"] for row in rows),
            "retargeted_clips": sum(row["counts"]["clips"] for row in rows),
        },
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def inputs(csdk: Path = CSDK) -> dict[str, Path]:
    """The compiled +scout slices, keyed by their path inside the addon."""
    root = csdk / "game" / "citadel_addons" / ADDON / "animgraphs" / "animgraph2" / "hero"
    return {
        f"animgraphs/animgraph2/hero/{path.name}": path
        for path in sorted(root.glob(f"*+{TARGET_VARIATION}.vnmgraph_c"))
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Scout's hero graph variations.")
    parser.add_argument("--csdk", default=str(CSDK))
    parser.add_argument("command", choices=("build",))
    args = parser.parse_args(argv)
    try:
        report = build(Path(args.csdk))
    except GraphError as error:
        print(f"REFUSED {error}")
        return 2
    print(json.dumps(report["counts"]))
    for row in report["documents"]:
        print(f"  {row['bytes']:>8} B {row['base']} ({row['counts']['clips']} clips)")
    print(f"receipt {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
