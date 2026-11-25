"""Install Scout's compiled port into the live Deadlock addon folder, and pack the same set.

What ships is what compiled: the port's own 78-joint skeleton, its four clip documents, its authored
AnimGraph, the mesh model with its materials and textures, the four animation DMX the clip documents name
(a compiled `vnmclip_c` is a reference plus a checksum, not the samples — the DMX has to be there), and
the compiled hero table that names Scout.

  python tools/scout_install.py stage      # every compiled input the install needs, or refuse by name
  python tools/scout_install.py register   # author `hero_scout` in the port's table and compile it
  python tools/scout_install.py install    # register, copy into <game>/citadel_addons/scout_port, pack
  python tools/scout_install.py probe      # read the Popit app's pack and hero steps over loopback HTTP

The hero entry is a clone of `hero_frank` — its abilities, item slots and stats are the parts the engine
resolves by name and none is invented — with its own identity and body
(`models/heroes_wip/scout/scout_body.vmdl`), Scout icon/card/vertical images built by `tools/scout_ui.py`,
and the game's own default shop, team-reveal and postgame maps instead of Frank's. Frank's portrait prefab
and name logos are dropped, as 14 and 23 shipped heroes respectively do. The authored graph
(`models/heroes_wip/scout/scout.vnmgraph`) is still named in `m_sAG2VariationName`, but every released
entry that sets that field names a `hero.vnmgraph+<hero>.vnmgraph` variation; a standalone graph is
therefore recorded as unverified (`ag2-hero-variation-required`), not claimed to load. `register` writes
the table through a backup, compiles it with the CSDK 13 `resourcecompiler` (`-game <csdk>/game/citadel`),
and reads the entry back out of the compiled bytes with Source 2 Viewer before `install` will ship it.

The install is additive: it writes the port's files under the addon folder and never deletes an older
addon (the frank-bound `scout_animgraph` stays on disk, named as superseded by the application). The
receipt records every file with its md5 and the installed size, so the app's `pack` step can read the
install back instead of trusting this run's print.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge.oldmods import read_vpk  # noqa: E402
from tools import scout_ui  # noqa: E402
from tools.scout_clip_bake import write_vpk  # noqa: E402

CSDK = Path("C:/Users/ala/Downloads/Reduced_CSDK_13")
GAME = Path("D:/SteamLibrary/steamapps/common/Deadlock")
ADDON = "scout_port"
CLIP_NAMES = ("scout_attack", "scout_reload", "scout_aimidle", "scout_aimrun")
DMX_NAMES = (
    "attackstand_primary",
    "primary_aimmatrix_idle",
    "primary_aimmatrix_run",
    "primary_reload_loop",
)
RECEIPT = ROOT / "artifacts" / "receipts" / "scout-install.json"
VPK_OUT = ROOT / "artifacts" / "scout-update" / "vpk" / f"{ADDON}_dir.vpk"
S2V = Path("C:/Users/ala/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
TABLE = Path("F:/Documents/heroes.vdata")
TABLE_REL = "scripts/heroes.vdata"
TEMPLATE_HERO = "hero_frank"
HERO = "hero_scout"
HERO_MODEL = "models/heroes_wip/scout/scout_body.vmdl"
HERO_GRAPH = "models/heroes_wip/scout/scout.vnmgraph"
# Entry image fields, each naming a Scout image built by `tools/scout_ui.py`. The minimap and the two
# alternate cards reuse the three textures instead of shipping duplicates.
UI_FIELDS = {
    "m_strIconImageSmall": "scout_sm",
    "m_strMinimapImage": "scout_sm",
    "m_strIconHeroCard": "scout_card",
    "m_strIconHeroCardCritical": "scout_card",
    "m_strIconHeroCardGloat": "scout_card",
    "m_strTopBarVertical": "scout_vertical",
}
# Default UI maps 13 shipped heroes already name; none of them is Frank's.
MAP_FIELDS = {
    "m_strUIShoppingMap": "maps/ui/hero_shop/default_shop.vmap",
    "m_strUITeamRevealMap": "maps/ui/team_reveal_hero/default_team_reveal.vmap",
    "m_strUIPostgamePortraitMap": "maps/ui/hero_postgame_portrait/default_postgame_portrait.vmap",
}
# Frank's portrait prefab and name logos; 14 and 23 shipped heroes carry no such fields.
DROP_FIELDS = ("m_strUIPortraitMap", "m_strLogoImageEnglish", "m_strLogoImageLocalized")


class InstallError(Exception):
    """A refusal that names its code, so the caller can report it instead of a traceback."""


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _block(text: str, hero: str) -> tuple[int, int]:
    """The hero's block in the table text: from its key line to its closing brace."""
    match = re.search(rf"\n\t{hero} = ", text)
    if not match:
        raise InstallError(f"hero-block-missing: {hero}")
    start = match.start() + 1
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise InstallError(f"hero-block-unterminated: {hero}")


def _set_field(block: str, field: str, line: str, anchor: str = "m_strModelName") -> str:
    """Replace one entry field in place, or add it after the model line when the template lacks it."""
    pattern = rf"^\t\t{re.escape(field)} = .*$"
    if re.search(pattern, block, re.M):
        return re.sub(pattern, lambda _: line, block, count=1, flags=re.M)
    anchor_line = next((row for row in block.splitlines() if row.startswith(f"\t\t{anchor} = ")), "")
    if not anchor_line:
        raise InstallError(f"hero-template-lacks-anchor: {anchor}")
    return block.replace(anchor_line, anchor_line + "\n" + line, 1)


def _rewrite_ui(block: str) -> str:
    """Point the entry's UI fields at Scout images and the game's default maps; drop Frank's extras."""
    for field, image in UI_FIELDS.items():
        block = _set_field(block, field, f'\t\t{field} = panorama:"file://{{images}}/heroes/{image}.psd"')
    for field, path in MAP_FIELDS.items():
        block = _set_field(block, field, f'\t\t{field} = "{path}"')
    for field in DROP_FIELDS:
        block = re.sub(rf"^\t\t{re.escape(field)} = .*\r?\n", "", block, count=1, flags=re.M)
    return block


def author_hero(table: Path = TABLE) -> dict:
    """Write `hero_scout` into the port's hero table, cloning `hero_frank` and changing only identity.

    Abilities, item slots and stats stay the template's: the engine resolves those by name and inventing
    them would make the entry look resolved while naming nothing real. The body, the graph field and every
    UI field are Scout's. Re-running re-applies the UI fields to the existing block, so an entry authored
    before the Scout images existed is brought forward instead of duplicated.
    """
    text = table.read_text(encoding="utf-8", errors="replace")
    authored = False
    backup = None
    if f"\n\t{HERO} = " in text:
        start, end = _block(text, HERO)
        block = text[start:end]
        hero_id = int(re.search(r"^\t\tm_HeroID = (\d+)", block, re.M).group(1))
    else:
        start, end = _block(text, TEMPLATE_HERO)
        block = text[start:end]
        used = {int(value) for value in re.findall(r"^\t\tm_HeroID = (\d+)", text, re.M)}
        hero_id = next(candidate for candidate in range(89, 250) if candidate not in used)
        block = block.replace(f"\t{TEMPLATE_HERO} = ", f"\t{HERO} = ", 1)
        block = re.sub(r"^\t\tm_HeroID = \d+$", f"\t\tm_HeroID = {hero_id}", block, count=1, flags=re.M)
        block = re.sub(
            r'^(\t\tm_strModelName = resource_name:)"[^"]+"$',
            lambda match: match.group(1) + f'"{HERO_MODEL}"',
            block,
            count=1,
            flags=re.M,
        )
        if HERO_MODEL not in block:
            raise InstallError("hero-template-lacks-model: m_strModelName not replaced")
        graph_line = f'\t\tm_sAG2VariationName = resource_name:"{HERO_GRAPH}"'
        block = _set_field(block, "m_sAG2VariationName", graph_line)
        if HERO_GRAPH not in block:
            raise InstallError("hero-entry-lacks-graph: m_sAG2VariationName not written")
        block = block.replace('"#hero_frank_search"', '"#hero_scout_search"').replace('"#hero_frank_sort"', '"#hero_scout_sort"')
        tags = re.findall(r'^\t\t\t"(#[^"]+)"', block, re.M)
        for index, tag in enumerate(tags, start=1):
            block = block.replace(f'"{tag}"', f'"#Citadel_Scout_HeroTag_{index}"')
        authored = True
    scout = _rewrite_ui(block)
    if not authored and scout == block:
        return {"hero": HERO, "table": str(table), "authored": False, "hero_id": hero_id, "block_bytes": len(scout)}
    if not authored:
        backup = table.with_suffix(".pre-scout")
        if not backup.is_file():
            shutil.copy2(table, backup)
        table.write_text(text[:start] + scout + text[end:], encoding="utf-8")
    else:
        backup = table.with_suffix(".pre-scout")
        if not backup.is_file():
            shutil.copy2(table, backup)
        table.write_text(text[:end] + "\n" + scout.rstrip() + text[end:], encoding="utf-8")
    return {
        "hero": HERO,
        "table": str(table),
        "backup": str(backup),
        "authored": authored,
        "hero_id": hero_id,
        "block_bytes": len(scout),
        "model": HERO_MODEL,
        "graph": HERO_GRAPH,
        "ui": dict(UI_FIELDS),
        "maps": dict(MAP_FIELDS),
        "dropped": list(DROP_FIELDS),
    }


def compile_table(csdk: Path = CSDK) -> dict:
    """Compile the port's hero table with the CSDK 13 compiler, from the addon content root."""
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    content = csdk / "content"
    if not compiler.is_file():
        raise InstallError(f"hero-table-compiler-missing: {compiler}")
    document = content / "citadel_addons" / ADDON / TABLE_REL
    document.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TABLE, document)
    result = subprocess.run(
        [str(compiler), "-nop4", "-f", "-game", str(csdk / "game" / "citadel"), "-i", str(document.resolve())],
        cwd=str(content),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
    )
    tail = (result.stdout or "").strip().splitlines()
    ok_line = next((line.strip() for line in tail if line.strip().startswith(("OK:", "ERROR:"))), "")
    errors = [line.strip() for line in tail if "ERROR" in line or "Invalid" in line or "Load error" in line]
    compiled = csdk / "game" / "citadel_addons" / ADDON / (TABLE_REL + "_c")
    if not ok_line.startswith("OK") or not compiled.is_file():
        raise InstallError(f"hero-table-compile-failed: {ok_line or (errors[:1] or ['no OK line'])[0]}")
    return {
        "source": str(document),
        "compiled": str(compiled),
        "bytes": compiled.stat().st_size,
        "md5": _md5(compiled),
        "ok_line": ok_line,
        "errors": errors[:5],
    }


def read_compiled_entry(compiled: Path) -> dict:
    """Read `hero_scout` back out of the compiled table with Source 2 Viewer, not from the source text."""
    if not S2V.is_file():
        raise InstallError(f"hero-table-decompiler-missing: {S2V}")
    destination = ROOT / "artifacts" / "scout-hero" / "decompiled"
    shutil.rmtree(destination, ignore_errors=True)
    subprocess.run(
        [str(S2V), "-i", str(compiled), "-d", "-o", str(destination)],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=900,
    )
    dumped = sorted(destination.rglob("heroes.vdata")) if destination.is_dir() else []
    if not dumped:
        raise InstallError(f"hero-table-decompile-empty: no heroes.vdata under {destination}")
    text = dumped[0].read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"\n\t{HERO} = ", text)
    if not match:
        raise InstallError(f"hero-entry-absent-after-compile: {HERO} not in {dumped[0]}")
    start, end = _block(text, HERO)
    block = text[start:end]
    graph = re.search(r'^\t\tm_sAG2VariationName = resource_name:"([^"]+)"', block, re.M)
    ui = {
        field: match.group(1)
        for field in UI_FIELDS
        if (match := re.search(rf'^\t\t{field} = panorama:"([^"]+)"', block, re.M))
    }
    maps = {
        field: match.group(1)
        for field in MAP_FIELDS
        if (match := re.search(rf'^\t\t{field} = "([^"]+)"', block, re.M))
    }
    return {
        "decompiled": str(dumped[0]),
        "block_bytes": len(block),
        "model": HERO_MODEL in block,
        "graph": HERO_GRAPH in block,
        "graph_path": graph.group(1) if graph else "",
        "hero_id": int(re.search(r"^\t\tm_HeroID = (\d+)", block, re.M).group(1)),
        "paths": sorted(set(re.findall(r"models/heroes_wip/scout/[^\"\s]+", block))),
        "ui": ui,
        "maps": maps,
        "dropped_present": [field for field in DROP_FIELDS if re.search(rf"^\t\t{re.escape(field)} = ", block, re.M)],
    }


def entry_resolution(target: Path, entry: dict) -> list[dict]:
    """Every path the entry names under the port's model folder, resolved to the installed compiled file."""
    rows = []
    for path in entry["paths"]:
        installed = target / (path + "_c")
        rows.append(
            {
                "named": path,
                "compiled": path + "_c",
                "installed": str(installed),
                "present": installed.is_file(),
                "bytes": installed.stat().st_size if installed.is_file() else 0,
                "md5": _md5(installed) if installed.is_file() else "",
            }
        )
    return rows


def ui_resolution(target: Path, entry: dict) -> list[dict]:
    """Each Scout image the entry names, resolved to the panorama resource the install carries."""
    rows = []
    for field, url in entry["ui"].items():
        name = url.rsplit("/", 1)[-1]
        compiled = name.rsplit(".", 1)[0] + "_psd.vtex_c"
        installed = target / "panorama" / "images" / "heroes" / compiled
        rows.append(
            {
                "field": field,
                "named": url,
                "compiled": compiled,
                "installed": str(installed),
                "present": installed.is_file(),
                "bytes": installed.stat().st_size if installed.is_file() else 0,
                "md5": _md5(installed) if installed.is_file() else "",
            }
        )
    return rows


def map_resolution(entry: dict, table: Path = TABLE) -> list[dict]:
    """Each UI map the entry names; the default maps are shipped because 13 released entries name them."""
    text = table.read_text(encoding="utf-8", errors="replace")
    return [
        {"field": field, "named": path, "named_by_released_entries": text.count(f'"{path}"'), "present": text.count(f'"{path}"') > 0}
        for field, path in entry["maps"].items()
    ]


def graph_binding(csdk: Path, entry: dict, table: Path = TABLE) -> dict:
    """How the entry's graph field compares with what the shipped heroes actually name.

    A refactor cannot decide engine acceptance; this records the observed contract and the difference.
    Only entries that set `m_sAG2VariationName` are compared, and every one of those names a
    `hero.vnmgraph+<hero>.vnmgraph` variation. The branch's hero graph folder is counted too.
    """
    text = table.read_text(encoding="utf-8", errors="replace")
    values = re.findall(r'^\t\tm_sAG2VariationName = resource_name:"([^"]+)"', text, re.M)
    others = [value for value in values if value != HERO_GRAPH]
    hero_dir = csdk / "game" / "citadel" / "animgraphs" / "animgraph2" / "hero"
    variations = len(list(hero_dir.glob("hero.vnmgraph+*.vnmgraph_c"))) if hero_dir.is_dir() else 0
    standalone = [path.name for path in hero_dir.glob("*.vnmgraph_c") if "+" not in path.name] if hero_dir.is_dir() else []
    left = sum(1 for value in others if "+" in value)
    return {
        "field": "m_sAG2VariationName",
        "named": entry.get("graph_path", ""),
        "form": "standalone",
        "observed_contract": "animgraphs/animgraph2/hero/hero.vnmgraph+<hero>.vnmgraph",
        "released_entries_with_field": len(others),
        "released_entries_variation_form": left,
        "hero_blocks": len(re.findall(r"^\t\tm_HeroID = ", text, re.M)),
        "variation_files_in_branch": variations,
        "standalone_graphs_in_branch": len(standalone),
        "state": "unverified",
        "refusal": "ag2-hero-variation-required",
        "detail": (
            f"{len(others)} shipped entries set this field, {left} of them name a hero.vnmgraph+<hero> variation; "
            f"{len(re.findall(r'^\t\tm_HeroID = ', text, re.M))} hero blocks exist and the rest leave it unset. "
            f"The branch ships {variations} hero variations; its {len(standalone)} standalone graphs are "
            "auxiliary hero graphs (ability mask, loco sets) that no hero entry names. A standalone graph "
            "has no observed acceptance in this field; loading is not claimed."
        ),
    }


def inputs(csdk: Path = CSDK) -> dict[str, Path]:
    """The compiled files that make up the addon, keyed by their path inside the addon.

    Compiled output does not land in one place: the skeleton, clips and graph are under
    `game/citadel_addons/<addon>/…`, while the mesh model and its materials compile to `game/models/…`.
    """
    addon_dir = csdk / "game" / "citadel_addons" / ADDON
    addon_root = addon_dir / "models" / "heroes_wip" / "scout"
    game_root = csdk / "game" / "models" / "heroes_wip" / "scout"
    files = {
        "models/heroes_wip/scout/scout.vnmskel_c": addon_root / "scout.vnmskel_c",
        "models/heroes_wip/scout/scout.vnmgraph_c": addon_root / "scout.vnmgraph_c",
        "models/heroes_wip/scout/scout_body.vmdl_c": game_root / "scout_body.vmdl_c",
        TABLE_REL + "_c": addon_dir / (TABLE_REL + "_c"),
    }
    for name in CLIP_NAMES:
        files[f"models/heroes_wip/scout/clips/{name}.vnmclip_c"] = addon_root / "clips" / f"{name}.vnmclip_c"
    for name in DMX_NAMES:
        files[f"models/heroes_wip/scout/dmx/{name}.dmx"] = addon_root / "dmx" / f"{name}.dmx"
    for pattern in ("*.vmat_c", "*.vtex_c"):
        for material in sorted((game_root / "materials").glob(pattern)):
            files[f"models/heroes_wip/scout/materials/{material.name}"] = material
    # The compiler writes a vmat's texture reference without the `models/` prefix (it reads the source
    # texture relative to `<content>/models/`), while the shipped paks carry the same texture under
    # `models/...`. The live client asked for `heroes_wip/scout/materials/<name>_png_<hash>.vtex_c` and
    # fell back to the error texture, so the same compiled vtex is also carried at that name.
    for vtex in sorted((game_root / "materials").glob("*.vtex_c")):
        files[f"heroes_wip/scout/materials/{vtex.name}"] = vtex
    for relative, source in scout_ui.inputs(csdk).items():
        if not source.is_file():
            raise InstallError(f"scout-ui-missing: {relative}; run `python tools/scout_ui.py build`")
        files[relative] = source
    return files


def stage(csdk: Path = CSDK) -> dict:
    """Check every input exists and report the set; refuse with the missing names, not a partial install."""
    files = inputs(csdk)
    missing = [relative for relative, source in files.items() if not source.is_file()]
    if missing:
        raise InstallError(f"addon-input-missing: {len(missing)} files, first {missing[0]}")
    rows = [
        {"path": relative, "bytes": source.stat().st_size, "md5": _md5(source), "source": str(source)}
        for relative, source in sorted(files.items())
    ]
    return {
        "files": rows,
        "counts": {
            "files": len(rows),
            "bytes": sum(row["bytes"] for row in rows),
            "clips": sum(1 for row in rows if row["path"].endswith(".vnmclip_c")),
            "dmx": sum(1 for row in rows if row["path"].endswith(".dmx")),
            "materials": sum(1 for row in rows if "/materials/" in row["path"]),
        },
    }


def install(csdk: Path = CSDK, game: Path = GAME) -> dict:
    """Register Scout, copy the staged set into the addon folder, pack it, and read both back."""
    target = game / "game" / "citadel_addons" / ADDON
    if not (game / "game").is_dir():
        raise InstallError(f"install-target-missing: {game / 'game'}")
    ui = scout_ui.build(csdk)
    hero = author_hero()
    table = compile_table(csdk)
    entry = read_compiled_entry(Path(table["compiled"]))
    prepared = stage(csdk)
    payload = {row["path"]: Path(row["source"]).read_bytes() for row in prepared["files"]}
    installed = []
    for relative, data in sorted(payload.items()):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        installed.append(
            {
                "path": relative,
                "installed": str(destination),
                "bytes": destination.stat().st_size,
                "md5": _md5(destination),
                "matches_staged": _md5(destination) == hashlib.md5(data).hexdigest(),
            }
        )
    mismatched = [row["path"] for row in installed if not row["matches_staged"]]
    if mismatched:
        raise InstallError(f"install-readback-mismatch: {len(mismatched)} files, first {mismatched[0]}")
    vpk = write_vpk(payload, VPK_OUT)
    tree = read_vpk(vpk)
    read_back = {entry.path for entry in tree.entries}
    expected = set(payload)
    resolution = entry_resolution(target, entry)
    ui_rows = ui_resolution(target, entry)
    map_rows = map_resolution(entry)
    binding = graph_binding(csdk, entry)
    installed_table = target / (TABLE_REL + "_c")
    compiled_graph = csdk / "game" / "citadel_addons" / ADDON / "models" / "heroes_wip" / "scout" / "scout.vnmgraph_c"
    hero_report = {
        **hero,
        "table_compile": table,
        "entry": entry,
        "paths": resolution,
        "resolved_all": all(row["present"] for row in resolution) and bool(resolution),
        "ui": ui_rows,
        "ui_resolved_all": all(row["present"] for row in ui_rows) and bool(ui_rows),
        "maps": map_rows,
        "maps_resolved_all": all(row["present"] for row in map_rows) and bool(map_rows),
        "graph_binding": binding,
        "table_installed": str(installed_table),
        "table_installed_md5": _md5(installed_table) if installed_table.is_file() else "",
        "graph_installed_md5": _md5(target / "models/heroes_wip/scout/scout.vnmgraph_c")
        if (target / "models/heroes_wip/scout/scout.vnmgraph_c").is_file()
        else "",
        "graph_compiled_md5": _md5(compiled_graph) if compiled_graph.is_file() else "",
    }
    hero_report["graph_matches_compiled"] = bool(
        hero_report["graph_installed_md5"]
        and hero_report["graph_installed_md5"] == hero_report["graph_compiled_md5"]
    )
    report = {
        "schema": "dmf.scout-install/1",
        "generated": _stamp(),
        "csdk": str(csdk),
        "game": str(game),
        "target": str(target),
        "addon": ADDON,
        "files": installed,
        "counts": prepared["counts"],
        "vpk": {
            "path": str(vpk),
            "bytes": vpk.stat().st_size,
            "version": tree.version,
            "entries": len(tree.entries),
            "missing_after_read": sorted(expected - read_back),
            "extra_after_read": sorted(read_back - expected),
        },
        "hero": hero_report,
        "ui": {"receipt": str(scout_ui.RECEIPT), "counts": ui["counts"]},
        "missing_after_install": sorted(row["path"] for row in installed if not Path(row["installed"]).is_file()),
    }
    report["ok"] = (
        not report["missing_after_install"]
        and not report["vpk"]["missing_after_read"]
        and report["counts"]["files"] == len(installed)
        and hero_report["resolved_all"]
        and hero_report["ui_resolved_all"]
        and hero_report["maps_resolved_all"]
        and hero_report["table_installed_md5"] == table["md5"]
    )
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def probe() -> dict:
    """Read the install back through the Popit app, the surface the owner would look at."""
    app = ROOT / "popit_apps" / "scout_port"
    sys.path.insert(0, str(app))
    import server  # noqa: E402  (the app's own reader)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=15) as response:
            page = response.read().decode("utf-8", errors="replace")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
    steps = {step["id"]: step for step in body.get("steps") or []}
    pack = steps.get("pack") or {}
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8")) if RECEIPT.is_file() else {}
    checks = [
        {"name": "page-served", "ok": 'data-popit="scout-port"' in page, "detail": "data-popit"},
        {"name": "pack-step-pass", "ok": pack.get("state") == "pass", "detail": str(pack.get("detail", "")[:120])},
        {
            "name": "pack-counts",
            "ok": (pack.get("counts") or {}).get("files") == (receipt.get("counts") or {}).get("files")
            and bool((pack.get("counts") or {}).get("files")),
            "detail": json.dumps(pack.get("counts") or {}),
        },
        {
            "name": "vpk-read-back",
            "ok": bool(receipt.get("vpk", {}).get("entries")) and not receipt.get("vpk", {}).get("missing_after_read"),
            "detail": json.dumps(receipt.get("vpk") or {}),
        },
        {
            "name": "hero-step-pass",
            "ok": (steps.get("hero") or {}).get("state") == "pass",
            "detail": str((steps.get("hero") or {}).get("detail", ""))[:140],
        },
        {
            "name": "hero-paths-resolve",
            "ok": bool((receipt.get("hero") or {}).get("resolved_all"))
            and (receipt.get("hero") or {}).get("graph_matches_compiled") is True,
            "detail": json.dumps(
                {
                    "hero": (receipt.get("hero") or {}).get("hero"),
                    "paths": [row.get("compiled") for row in (receipt.get("hero") or {}).get("paths") or []],
                    "graph_matches_compiled": (receipt.get("hero") or {}).get("graph_matches_compiled"),
                }
            ),
        },
        {
            "name": "hero-ui-resolve",
            "ok": bool((receipt.get("hero") or {}).get("ui_resolved_all"))
            and bool((receipt.get("hero") or {}).get("maps_resolved_all")),
            "detail": json.dumps(
                {
                    "images": [row.get("compiled") for row in (receipt.get("hero") or {}).get("ui") or []],
                    "maps": [row.get("named") for row in (receipt.get("hero") or {}).get("maps") or []],
                    "binding": ((receipt.get("hero") or {}).get("graph_binding") or {}).get("refusal"),
                }
            ),
        },
    ]
    out = {
        "schema": "dmf.scout-install-probe/1",
        "generated": _stamp(),
        "url": f"http://127.0.0.1:{port}/",
        "receipt": str(RECEIPT),
        "checks": checks,
    }
    path = ROOT / "artifacts" / "receipts" / "scout-install-probe.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    failed = [check for check in checks if not check["ok"]]
    for check in checks:
        print(f"  [{'PASS' if check['ok'] else 'FAIL'}] {check['name']}: {check['detail']}")
    print(f"receipt {path}")
    print(f"RESULT: {'PASS' if not failed else 'REFUSED'}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Scout's compiled port into the live addon folder.")
    parser.add_argument("--csdk", default=str(CSDK))
    parser.add_argument("--game", default=str(GAME))
    parser.add_argument("command", choices=("stage", "register", "install", "probe"))
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            prepared = stage(Path(args.csdk))
            print(json.dumps(prepared["counts"]))
            for row in prepared["files"]:
                print(f"  {row['bytes']:>8} {row['path']}")
            return 0
        if args.command == "register":
            hero = author_hero()
            table = compile_table(Path(args.csdk))
            entry = read_compiled_entry(Path(table["compiled"]))
            print(json.dumps({"hero": hero, "table": table, "entry": entry}, indent=2))
            return 0 if entry["model"] and entry["graph"] else 2
        if args.command == "install":
            report = install(Path(args.csdk), Path(args.game))
            print(f"installed {report['counts']['files']} files ({report['counts']['bytes']} bytes) -> {report['target']}")
            print(f"vpk {report['vpk']['path']} {report['vpk']['bytes']} bytes, {report['vpk']['entries']} entries")
            print(f"receipt {RECEIPT}")
            return 0 if report["ok"] else 2
        probe()
        return 0
    except InstallError as error:
        print(f"REFUSED {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
