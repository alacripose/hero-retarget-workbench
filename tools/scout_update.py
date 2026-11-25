"""Scout port: report, stage, retarget an animgraph, and serve its Popit UI.

Every subcommand reads files that exist and names what it could not read. A
refusal is a code (`hero-table-missing`, `dota-tools-no-compiler`) plus the path
that was searched, never a fill-in value.

The Popit UI is part of the tool, not an extra: `serve` hosts it and `probe`
fails unless the page renders the report the same run produced.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import live, scout  # noqa: E402
from forge.hashes import blake3_file, blake3_hex  # noqa: E402

UI_DIR = Path(__file__).resolve().parent / "scout_ui"
REPORT = ROOT / "artifacts" / "scout-update" / "report.json"
SCHEMA = "dmf.scout-update/1"


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_steam_inf(game_root: Path | None) -> dict:
    """The build markers the client declares, read from its own steam.inf."""
    row: dict[str, Any] = {"root": str(game_root) if game_root else "", "state": "unknown"}
    if not game_root:
        return row
    path = Path(game_root) / "game" / "citadel" / "steam.inf"
    if not path.is_file():
        path = Path(game_root) / "citadel" / "steam.inf"
    row["steam_inf"] = str(path)
    if not path.is_file():
        row["state"] = "steam-inf-missing"
        return row
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        key, _, value = line.partition("=")
        key = key.strip().lower()
        if not value:
            continue
        if key in ("clientversion", "build", "serverbuild"):
            row["build"] = value.strip()
        elif key in ("versiondate", "version_date"):
            row["version_date"] = value.strip()
    row["state"] = "read" if row.get("build") or row.get("version_date") else "unread"
    return row


def build_report(args) -> dict:
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated": _stamp(),
        "workspace": str(Path(args.workspace)) if args.workspace else "",
        "game": _read_steam_inf(Path(args.game) if args.game else None),
        "checks": [],
        "refusals": [],
    }

    def refusal(code: str, detail: str = "") -> None:
        report["refusals"].append({"code": code, "detail": detail})

    def check(name: str, state: str, detail: str = "") -> None:
        report["checks"].append({"name": name, "state": state, "detail": detail})

    mod: dict[str, Any] = {"sources": {}, "hero_table": {}}
    heroes = ()
    if args.workspace:
        try:
            sources = scout.scan_sources(Path(args.workspace), args.stem)
            mod["sources"] = sources.to_dict()
            check("mod-sources", "pass", f"{sources.smd} mesh SMD, {sources.anim_smd} animation SMD")
        except scout.ScoutError as error:
            refusal(*_split(error))
            check("mod-sources", "fail", str(error))
        table_path = scout.find_hero_table(Path(args.workspace))
        if table_path is None:
            refusal("hero-table-missing", f"{args.workspace}: no scripts/heroes.vdata or heroes.vdata")
            check("mod-hero-table", "fail", "no hero script snapshot")
        else:
            try:
                table = scout.read_hero_table(table_path)
                heroes = table.heroes
                mod["hero_table"] = table.to_dict()
                mod["hero_table"]["hero_slugs"] = [hero.slug for hero in table.heroes]
                check("mod-hero-table", "pass", f"{len(table.heroes)} hero entries")
            except scout.ScoutError as error:
                refusal(*_split(error))
                check("mod-hero-table", "fail", str(error))
    else:
        refusal("workspace-not-declared", "pass --workspace or set DMF_SCOUT_WORKSPACE")
        check("mod-sources", "skip", "no workspace")
    report["mod"] = mod

    drift_row: dict[str, Any] = {"state": "unavailable"}
    if args.live_heroes:
        try:
            live_text = Path(args.live_heroes).read_text(encoding="utf-8", errors="replace")
            live_heroes = tuple(live.parse_hero_roster(live_text))
            if not live_heroes:
                scout.ScoutError("live-roster-empty: " + args.live_heroes)
            drift_row = scout.drift(heroes, live_heroes).to_dict()
            drift_row["live"] = len(live_heroes)
            drift_row["live_path"] = str(args.live_heroes)
            drift_row["state"] = "measured"
            check(
                "live-drift",
                "pass" if not (drift_row["added"] or drift_row["removed"] or drift_row["moved"]) else "fail",
                f"{len(drift_row['added'])} new, {len(drift_row['removed'])} gone, {len(drift_row['moved'])} moved",
            )
        except (OSError, scout.ScoutError) as error:
            refusal(*_split(error))
            check("live-drift", "fail", str(error))
    else:
        refusal("live-roster-not-declared", "pass --live-heroes with an extracted scripts/heroes.vdata")
        check("live-drift", "skip", "no live roster")
    report["drift"] = drift_row

    tools_row: dict[str, Any] = {"state": "unavailable"}
    if args.dota_tools:
        try:
            tools = scout.dota_tools(Path(args.dota_tools))
            tools_row = tools.to_dict()
            tools_row["state"] = "ready"
            check("dota-tools", "pass", f"{len(tools.graphs)} graphs, compiler present")
        except scout.ScoutError as error:
            refusal(*_split(error))
            tools_row["state"] = "incomplete"
            check("dota-tools", "fail", str(error))
    else:
        refusal("dota-tools-not-declared", "pass --dota-tools with an extracted Dota 2 tools tree")
        check("dota-tools", "skip", "no Dota tools tree")
    report["dota_tools"] = tools_row

    graph_row: dict[str, Any] = {"state": "unavailable"}
    sequence_row: dict[str, Any] = {"state": "unavailable"}
    graph_rows: list[dict[str, Any]] = []
    if args.graph:
        # Every declared document is summarised; the *last* one is the reading the
        # page shows, so a probe can point the surface at the graph it just authored.
        graph_path = Path(args.graph[-1])
        for declared in args.graph:
            try:
                row = scout.graph_summary(Path(declared)).to_dict()
                row["state"] = "read"
            except scout.ScoutError as error:
                row = {"path": str(declared), "state": "refused", "refusal": str(error)}
            graph_rows.append(row)
        try:
            graph = scout.graph_summary(graph_path)
            graph_row = graph.to_dict()
            graph_row["state"] = "read"
            check(
                "animgraph",
                "pass",
                f"{graph.schema} schema, {graph.nodes} nodes, {len(graph.sequences)} sequences"
                + (f" ({len(graph_rows)} documents)" if len(graph_rows) > 1 else ""),
            )
            if args.workspace and not graph.sequences:
                # A variation document names clips, not sequences: there is no join
                # to measure, and saying "0 of 0" would read as a failure.
                check("sequence-map", "skip", "this document names clips, not sequences")
            elif args.workspace:
                names = scout.sequence_names(graph_path.read_text(encoding="utf-8", errors="replace"))
                # The port's authority on what its model plays is its QC: an SMD on
                # disk is not a sequence until a `$sequence` block names it.
                port = Path(args.workspace)
                binding = scout.bind_sequences(
                    names, scout.port_sequences(port) or scout.source_sequences(port)
                )
                sequence_row = {"state": "measured", **binding}
                sequence_row.pop("rows", None)
                check(
                    "sequence-map",
                    "pass" if binding["bound"] else "fail",
                    f"{binding['bound']}/{binding['graph_sequences']} graph sequences have a source animation",
                )
                if binding["unbound"]:
                    refusal(
                        "animgraph-sequence-unbound",
                        f"{len(binding['unbound'])} of {binding['graph_sequences']}: "
                        + ", ".join(binding["unbound"][:6])
                        + ("…" if len(binding["unbound"]) > 6 else ""),
                    )
            else:
                check("sequence-map", "skip", "no workspace")
        except scout.ScoutError as error:
            refusal(*_split(error))
            check("animgraph", "fail", str(error))
    else:
        refusal("graph-not-declared", "pass --graph with an AnimGraph 2 document")
        check("animgraph", "skip", "no graph document")
    report["animgraph"] = graph_row
    report["animgraphs"] = graph_rows
    variation_row: dict[str, Any] = {"state": "unavailable"}
    if getattr(args, "variation", ""):
        try:
            variation = scout.graph_summary(Path(args.variation))
            variation_row = variation.to_dict()
            variation_row["state"] = "read"
            check("variation", "pass", f"{variation.variation} on {variation.skeleton}")
        except scout.ScoutError as error:
            variation_row["state"] = "refused"
            variation_row["refusal"] = str(error)
            refusal(*_split(error))
            check("variation", "fail", str(error))
    report["variation"] = variation_row
    report["sequences"] = sequence_row
    report["result"] = "pass" if all(row["state"] == "pass" for row in report["checks"]) else "partial"
    return report


def _split(error: Exception) -> tuple[str, str]:
    text = str(error)
    code, _, detail = text.partition(":")
    return code.strip(), detail.strip()


def _write_report(report: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def cmd_report(args) -> int:
    report = build_report(args)
    path = _write_report(report, Path(args.json))
    print(f"report {path}")
    print(f"result {report['result']}")
    for row in report["checks"]:
        print(f"  {row['state']:<5} {row['name']}: {row['detail']}")
    for row in report["refusals"]:
        print(f"  refusal {row['code']}: {row['detail']}")
    return 0 if report["result"] == "pass" else 2


def cmd_extract_dota(args) -> int:
    """Extract only the AnimGraph 2 authoring tree from the shipped zip."""
    import zipfile

    archive = Path(args.zip)
    if not archive.is_file():
        raise scout.ScoutError(f"dota-zip-missing: {archive}")
    out = Path(args.out)
    # `game/bin` carries the tools themselves, including `tools/animgraph_editor.dll`
    # and the `animationsystem.dll` the reduced CSDK has disabled; without them the
    # compiler answers `Tried to FileExists NULL filename` and no graph is built.
    wanted = (
        "content/dota_addons/animgraph/",
        "game/bin/",
        # The compiler resolves `-game` through this file; without it it has no
        # search paths and reports the asset as missing.
        "game/dota/gameinfo",
    )
    written = 0
    selected = 0
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename
            if name.endswith("/") or not any(part in name for part in wanted):
                continue
            selected += 1
            total += info.file_size
            if args.check:
                continue
            # Drop the archive's own top folder so --out is the tools root.
            relative = name.split("/", 1)[1] if "/" in name else name
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as sink:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    sink.write(block)
            written += 1
    if args.check:
        print(f"would extract {selected} of {len(bundle.namelist())} entries; {total} bytes")
        return 0
    print(f"extracted {written} files, {total} bytes to {out}")
    return 0


def cmd_bind(args) -> int:
    """Write the graph-sequence -> source-animation map, gaps included."""
    graph_path = Path(args.graph[0])
    if not graph_path.is_file():
        raise scout.ScoutError(f"graph-missing: {graph_path}")
    names = scout.sequence_names(graph_path.read_text(encoding="utf-8", errors="replace"))
    port = Path(args.workspace)
    declared = scout.port_sequences(port)
    sources = declared or scout.source_sequences(port)
    binding = scout.bind_sequences(names, sources)
    binding["declared_by_qc"] = len(declared)
    payload = {
        "schema": "dmf.scout-sequence-map/1",
        "generated": _stamp(),
        "graph": str(graph_path),
        "graph_blake3": blake3_file(graph_path),
        "workspace": str(Path(args.workspace)),
        **binding,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"sequence map {out}")
    print(f"  {binding['bound']}/{binding['graph_sequences']} bound, {len(binding['unbound'])} unbound")
    for name in binding["unbound"][:10]:
        print(f"  unbound {name}")
    return 0 if binding["bound"] else 2


def cmd_stage(args) -> int:
    """Copy the mod's own scripts and graph beside the live model, verbatim."""
    if not args.hero:
        raise scout.ScoutError("hero-not-declared: pass --hero with the live hero this port replaces")
    workspace = Path(args.workspace)
    table_path = scout.find_hero_table(workspace)
    if table_path is None:
        raise scout.ScoutError(f"hero-table-missing: {workspace}")
    table = scout.read_hero_table(table_path)
    by_slug = {hero.slug: hero for hero in table.heroes}
    if args.hero not in by_slug:
        raise scout.ScoutError(f"mod-hero-absent: {args.hero} is not in {table_path.name}")
    hero = by_slug[args.hero]
    model = hero.model_path
    model_relative = model[:-2] if model.lower().endswith("_c") else model
    present = [workspace / model_relative, workspace / (model_relative + "_c")]
    found = next((path for path in present if path.is_file()), None)
    if found is None:
        raise scout.ScoutError(
            "mod-hero-model-missing: " + ", ".join(str(path) for path in present)
        )
    out = Path(args.out)
    scripts = out / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    staged_table = scripts / "heroes.vdata"
    staged_table.write_bytes(table_path.read_bytes())
    digest_in = blake3_file(table_path)
    digest_out = blake3_file(staged_table)
    if digest_in != digest_out:
        raise scout.ScoutError("hero-table-rewritten: staged bytes differ from the mod's copy")
    graphs: list[dict] = []
    graph_dir = out / "animgraphs"
    for graph in args.graph or ():
        source = Path(graph)
        if not source.is_file():
            raise scout.ScoutError(f"graph-missing: {source}")
        graph_dir.mkdir(parents=True, exist_ok=True)
        target = graph_dir / source.name
        target.write_bytes(source.read_bytes())
        graphs.append(
            {
                "source": str(source),
                "staged": str(target),
                "blake3": blake3_file(target),
                "summary": scout.graph_summary(target).to_dict(),
            }
        )
    manifest = {
        "schema": "dmf.scout-stage/1",
        "generated": _stamp(),
        "workspace": str(workspace),
        "hero": args.hero,
        "model": {
            "declared": model,
            "relative": model_relative,
            "present": str(found),
            "source": found.suffix.lower() == ".vmdl",
        },
        "hero_table": {
            "source": str(table_path),
            "staged": str(staged_table),
            "blake3": digest_out,
            "bytes": staged_table.stat().st_size,
            "heroes": len(table.heroes),
            "verbatim": True,
        },
        "graphs": graphs,
    }
    manifest_path = out / "stage.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"staged {args.hero} -> {out}")
    print(f"  hero table {digest_out[:16]}… verbatim ({len(table.heroes)} heroes)")
    print(f"  model {model_relative} ({'source' if manifest['model']['source'] else 'compiled only'})")
    print(f"  {len(graphs)} graph document(s)")
    print(f"  manifest {manifest_path}")
    return 0


def cmd_animgraph(args) -> int:
    """Retarget one AnimGraph 2 document to the port's skeleton and variation."""
    template = Path(args.template)
    if not template.is_file():
        raise scout.ScoutError(f"graph-missing: {template}")
    text = template.read_text(encoding="utf-8", errors="replace")
    before = scout.graph_summary(template)
    body = scout.retarget_graph(text, variation=args.variation, skeleton=args.skeleton, label=args.label)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    after = scout.graph_summary(out)
    receipt = {
        "schema": "dmf.scout-animgraph/1",
        "generated": _stamp(),
        "template": str(template),
        "template_blake3": blake3_file(template),
        "output": str(out),
        "output_blake3": blake3_file(out),
        "before": before.to_dict(),
        "after": after.to_dict(),
        "nodes_preserved": before.nodes == after.nodes,
        "clips_preserved": before.clips == after.clips,
        "compile": {"state": "not-requested"},
    }
    print(f"retargeted {template.name} -> {out}")
    print(f"  variation {before.variation!r} -> {after.variation!r}")
    print(f"  skeleton  {before.skeleton} -> {after.skeleton}")
    print(f"  {after.nodes} nodes and {len(after.clips)} clip references preserved")
    if not receipt["nodes_preserved"] or not receipt["clips_preserved"]:
        raise scout.ScoutError("graph-structure-changed: node or clip count moved during retarget")
    if args.compile:
        if not args.csdk:
            raise scout.ScoutError("compile-refused: pass --csdk with the CSDK13 root")
        csdk = Path(args.csdk)
        content = csdk / "content" / "citadel_addons" / "scout_animgraph" / "animgraphs"
        content.mkdir(parents=True, exist_ok=True)
        installed = content / out.name
        installed.write_bytes(out.read_bytes())
        compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
        gameinfo = csdk / "game" / "citadel" / "gameinfo.gi"
        if not compiler.is_file():
            raise scout.ScoutError(f"compile-refused: resourcecompiler missing at {compiler}")
        if not gameinfo.is_file():
            raise scout.ScoutError(f"compile-refused: gameinfo missing at {gameinfo}")
        result = subprocess.run(
            [
                str(compiler),
                "-nop4",
                "-f",
                "-game",
                str(gameinfo.parent),
                "-i",
                str(installed),
            ],
            cwd=str(content),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=600,
        )
        log = Path(args.log or (ROOT / "logs" / f"scout-animgraph-{out.stem}.log"))
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            "$ " + " ".join(result.args) + "\n\n" + result.stdout + result.stderr,
            encoding="utf-8",
        )
        compiled = installed.with_name(installed.name + "_c")
        receipt["compile"] = {
            "state": "pass" if result.returncode == 0 and compiled.is_file() else "fail",
            "returncode": result.returncode,
            "compiled": str(compiled) if compiled.is_file() else "",
            "bytes": compiled.stat().st_size if compiled.is_file() else 0,
            "log": str(log),
        }
        print(f"  compile {receipt['compile']['state']} rc={result.returncode} -> {compiled}")
    receipt_path = Path(args.receipt or (ROOT / "artifacts" / "receipts" / f"scout-animgraph-{out.stem}.json"))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"  receipt {receipt_path}")
    return 0 if receipt["compile"]["state"] in ("pass", "not-requested") else 2


def cmd_variation(args) -> int:
    """Add a variation to a fused AnimGraph 2 document by cloning another hero's."""
    template = Path(args.template)
    if not template.is_file():
        raise scout.ScoutError(f"graph-missing: {template}")
    text = template.read_text(encoding="utf-8", errors="replace")
    before = text.count('m_variationID = "')
    body, plan = scout.add_variation_overrides(
        text,
        target=args.target,
        skeleton=args.skeleton,
        clip_from=args.clip_from,
        clip_to=args.clip_to,
        label=args.label,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    after = body.count(f'm_variationID = "{args.target}"')
    receipt = {
        "schema": "dmf.scout-variation/1",
        "generated": _stamp(),
        "template": str(template),
        "template_blake3": blake3_file(template),
        "output": str(out),
        "output_blake3": blake3_file(out),
        "variations_before": before,
        "variations_after": after,
        "plan": plan,
        "compile": {"state": "not-requested"},
    }
    print(f"added {args.target} to {plan['nodes']} pose nodes in {out}")
    print(f"  {plan['inserted']} overrides, {len(plan['clips'])} clips -> {plan['clip_dir'] or 'unchanged'}")
    print(f"  {plan['nodes_without_overrides']} node(s) had no overrides to clone")
    print(f"  hierarchy {plan.get('hierarchy', '')}")
    if after != plan["inserted"] or not plan["inserted"]:
        raise scout.ScoutError(f"variation-count-moved: {after} ids for {plan['inserted']} inserted overrides")
    if args.compile:
        csdk = Path(args.csdk)
        compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
        game = csdk / "game" / "citadel"
        if not compiler.is_file():
            raise scout.ScoutError(f"compiler-missing: {compiler}")
        content = csdk / "content" / "citadel_addons" / "scout_animgraph" / "animgraphs"
        content.mkdir(parents=True, exist_ok=True)
        installed = content / out.name
        installed.write_bytes(out.read_bytes())
        result = subprocess.run(
            [str(compiler), "-nop4", "-f", "-game", str(game), "-i", f"citadel_addons/scout_animgraph/animgraphs/{out.name}"],
            cwd=str(csdk / "content"),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=900,
        )
        log = Path(args.log or (ROOT / "logs" / f"scout-variation-{out.stem}.log"))
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("$ " + " ".join(result.args) + "\n\n" + result.stdout + result.stderr, encoding="utf-8")
        # The compiler writes beside the source only when the source *is* in the
        # content tree; for an addon path it writes under `game/`. Check both.
        candidates = (
            installed.with_name(installed.name + "_c"),
            csdk / "game" / "citadel_addons" / "scout_animgraph" / "animgraphs" / (installed.name + "_c"),
        )
        compiled = next((path for path in candidates if path.is_file()), None)
        receipt["compile"] = {
            "state": "pass" if result.returncode == 0 and compiled is not None else "fail",
            "returncode": result.returncode,
            "compiled": str(compiled) if compiled is not None else "",
            "bytes": compiled.stat().st_size if compiled is not None else 0,
            "variations_compiled": len(
                [
                    path
                    for path in (compiled.parent if compiled else Path(".")).glob(f"{installed.name}+*_c")
                ]
            ),
            "log": str(log),
        }
        print(
            f"  compile {receipt['compile']['state']} rc={result.returncode} "
            f"({receipt['compile']['variations_compiled']} variations)"
        )
    receipt_path = Path(args.receipt or (ROOT / "artifacts" / "receipts" / f"scout-variation-{args.target}.json"))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"  receipt {receipt_path}")
    return 0 if receipt["compile"]["state"] in ("pass", "not-requested") else 2


def cmd_update(args) -> int:
    """Bring the port's hero table up to the live build, keeping a backup."""
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        raise scout.ScoutError(f"workspace-missing: {workspace}")
    port_table = scout.find_hero_table(workspace)
    if port_table is None:
        raise scout.ScoutError(f"hero-table-missing: no heroes.vdata under {workspace}")
    target = workspace / args.stem_hero_table if args.stem_hero_table else port_table
    live_path = Path(args.live_heroes)
    if not live_path.is_file():
        raise scout.ScoutError(f"live-roster-not-declared: {live_path}")
    port_rows = {hero.slug: hero for hero in scout.read_hero_table(port_table).heroes}
    live_rows = {hero.slug: hero for hero in scout.read_hero_table(live_path).heroes}
    port_only = sorted(set(port_rows) - set(live_rows))
    if port_only and not args.drop_port_only:
        raise scout.ScoutError(
            "port-only-heroes: "
            f"{len(port_only)} entries the live build does not carry would be dropped: "
            f"{', '.join(port_only[:6])} (pass --drop-port-only to proceed; a backup is kept)"
        )
    if not args.write:
        print(f"would update {port_table}")
        print(f"  {len(live_rows)} live entries, {len(port_rows)} in the port, {len(port_only)} port-only")
        print("  pass --write to replace the port's table (a backup is kept)")
        return 0
    backup = target.with_suffix(target.suffix + ".pre-update")
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
    body = live_path.read_text(encoding="utf-8", errors="replace")
    target.write_text(body, encoding="utf-8")
    written = {hero.slug: hero for hero in scout.read_hero_table(target).heroes}
    receipt = {
        "schema": "dmf.scout-update-table/1",
        "generated": _stamp(),
        "table": str(target),
        "backup": str(backup),
        "backup_blake3": blake3_file(backup),
        "before_blake3": blake3_file(backup),
        "after_blake3": blake3_file(target),
        "source": str(live_path),
        "source_blake3": blake3_file(live_path),
        "heroes_before": len(port_rows),
        "heroes_after": len(written),
        "matches_live": sorted(written) == sorted(live_rows),
        "added": sorted(set(live_rows) - set(port_rows)),
        "dropped": port_only,
        "moved": [
            {"slug": slug, "mod": port_rows[slug].model_path, "live": live_rows[slug].model_path}
            for slug in sorted(set(port_rows) & set(live_rows))
            if port_rows[slug].model_path != live_rows[slug].model_path
        ],
    }
    out = Path(args.receipt or (ROOT / "artifacts" / "receipts" / "scout-update-hero-table.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"updated {target}")
    print(f"  {receipt['heroes_before']} -> {receipt['heroes_after']} entries, matches live: {receipt['matches_live']}")
    print(f"  backup {backup}")
    print(f"  receipt {out}")
    if not receipt["matches_live"]:
        raise scout.ScoutError("hero-table-mismatch: the written table does not read back as the live roster")
    return 0


def cmd_graph(args) -> int:
    """Author a custom animgraph19 on the port's own sequences, from the Dota template."""
    template = Path(args.template)
    if not template.is_file():
        raise scout.ScoutError(f"graph-missing: {template}")
    if args.sequences_from:
        sequences = tuple(
            line.strip()
            for line in Path(args.sequences_from).read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        )
    elif args.workspace:
        sequences = scout.port_sequences(Path(args.workspace))
    else:
        raise scout.ScoutError("sequences-source-missing: pass --workspace or --sequences-from")
    if not sequences:
        raise scout.ScoutError("sequences-empty: the port declares no $sequence")
    text = template.read_text(encoding="utf-8", errors="replace")
    before = scout.graph_summary(template)
    body, plan = scout.retarget_sequences(
        text, model=args.model, sequences=sequences, label=args.label
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    after = scout.graph_summary(out)
    receipt = {
        "schema": "dmf.scout-graph/1",
        "generated": _stamp(),
        "template": str(template),
        "template_blake3": blake3_file(template),
        "output": str(out),
        "output_blake3": blake3_file(out),
        "before": before.to_dict(),
        "after": after.to_dict(),
        "plan": plan,
        "sequences_available": len(sequences),
        "nodes_preserved": before.nodes == after.nodes,
        "compile": {"state": "not-requested"},
    }
    print(f"authored {out}")
    print(f"  {plan['renamed']} sequence slots, {plan['occurrences']} occurrences, from {len(sequences)} port sequences")
    print(f"  model {plan['model']}")
    if not receipt["nodes_preserved"]:
        raise scout.ScoutError("graph-structure-changed: node count moved while renaming sequences")
    if args.compile:
        dota = Path(args.dota_tools or ROOT / "artifacts" / "dota-tools")
        compiler = dota / "game" / "bin" / "win64" / "resourcecompiler.exe"
        game = Path(args.game) / "game" / "citadel" if args.game else dota / "game" / "dota"
        if not compiler.is_file():
            raise scout.ScoutError(f"dota-tools-no-compiler: {compiler}")
        if not (game / "gameinfo.gi").is_file():
            raise scout.ScoutError(f"compile-refused: no gameinfo at {game}")
        result = subprocess.run(
            [str(compiler), "-nop4", "-f", "-game", str(game), "-i", out.name],
            cwd=str(out.parent),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=600,
        )
        log = Path(args.log or (ROOT / "logs" / f"scout-graph-{out.stem}.log"))
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            "$ " + " ".join(result.args) + "\n\n" + result.stdout + result.stderr,
            encoding="utf-8",
        )
        compiled = out.with_name(out.name + "_c")
        receipt["compile"] = {
            "state": "pass" if result.returncode == 0 and compiled.is_file() else "fail",
            "returncode": result.returncode,
            "compiled": str(compiled) if compiled.is_file() else "",
            "bytes": compiled.stat().st_size if compiled.is_file() else 0,
            "log": str(log),
        }
        print(f"  compile {receipt['compile']['state']} rc={result.returncode} -> {compiled}")
    receipt_path = Path(args.receipt or (ROOT / "artifacts" / "receipts" / f"scout-graph-{out.stem}.json"))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"  receipt {receipt_path}")
    return 0 if receipt["compile"]["state"] in ("pass", "not-requested") else 2


class _Handler(SimpleHTTPRequestHandler):
    report_path: Path = REPORT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_GET(self):  # noqa: N802 - http.server's own spelling
        if self.path.split("?")[0] == "/report.json":
            path = Path(self.report_path)
            if not path.is_file():
                self.send_error(404, "report.json is missing; run `report` first")
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, fmt, *args):  # keep the probe's stdout clean
        return


def cmd_serve(args) -> int:
    if not UI_DIR.is_dir():
        raise scout.ScoutError(f"popit-ui-missing: {UI_DIR}")
    _Handler.report_path = Path(args.report)
    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    port = server.server_address[1]
    print(f"Popit UI: http://{args.host}:{port}/")
    print(f"  report: {_Handler.report_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_probe(args) -> int:
    """Run the tool, then read its Popit UI over HTTP — the probe's own gate."""
    report = build_report(args)
    report_path = _write_report(report, Path(args.json))
    _Handler.report_path = report_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    page = ""
    served = {}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=15) as response:
            page = response.read().decode("utf-8", errors="replace")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/report.json", timeout=15) as response:
            served = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()

    required = (
        'data-popit="scout-update"',
        'id="port-state"',
        'id="drift-table"',
        'id="graph-clips"',
        'id="sequence-coverage"',
    )
    ui_checks = [
        {"name": f"popit:{needle}", "state": "pass" if needle in page else "fail", "detail": needle}
        for needle in required
    ]
    ui_checks.append(
        {
            "name": "popit:report-served",
            "state": "pass" if served.get("schema") == SCHEMA else "fail",
            "detail": str(served.get("schema", "")),
        }
    )
    ui_checks.append(
        {
            "name": "popit:checks-carried",
            "state": "pass" if served.get("checks") and all(row.get("state") for row in served["checks"]) else "fail",
            "detail": f"{len(served.get('checks', []))} rows",
        }
    )
    receipt = {
        "schema": "dmf.scout-probe/1",
        "generated": _stamp(),
        "report": str(report_path),
        "report_blake3": blake3_file(report_path),
        "url": f"http://127.0.0.1:{port}/",
        "page_bytes": len(page.encode("utf-8")),
        "page_blake3": blake3_hex(page.encode("utf-8")),
        "report_result": served.get("result", ""),
        "ui_checks": ui_checks,
        "refusals": served.get("refusals", []),
    }
    out = Path(args.receipt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    failed = [row for row in ui_checks if row["state"] != "pass"]
    print(f"report {report_path} ({served.get('result', '')})")
    print(f"popit {len(ui_checks) - len(failed)}/{len(ui_checks)} checks")
    for row in failed:
        print(f"  FAIL {row['name']}: {row['detail']}")
    print(f"receipt {out}")
    print("RESULT: PASS" if not failed else "RESULT: REFUSED")
    return 0 if not failed else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default="", help="the port's workspace (its heroes.vdata and sources)")
    common.add_argument("--stem", default="scout", help="the port's source stem (scout.qc, scout.mdl)")
    common.add_argument("--game", default="", help="the live Deadlock install root")
    common.add_argument("--live-heroes", default="", help="an extracted scripts/heroes.vdata from the live build")
    common.add_argument("--dota-tools", default="", help="an extracted Dota 2 tools tree")
    common.add_argument("--graph", action="append", default=[], help="an AnimGraph 2 document (repeatable)")
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", parents=[common], help="read the port, the live roster and the graph")
    report.add_argument("--json", default=str(REPORT))
    report.add_argument(
        "--variation", default="", help="a hero variation document to show as the bake target"
    )
    report.set_defaults(func=cmd_report)

    extract = sub.add_parser("extract-dota", help="extract the Dota tools animgraph tree from the shipped zip")
    extract.add_argument("--zip", required=True)
    extract.add_argument("--out", required=True)
    extract.add_argument("--check", action="store_true")
    extract.set_defaults(func=cmd_extract_dota)

    bind = sub.add_parser("bind", parents=[common], help="map a graph's sequence names onto the port's animations")
    bind.add_argument("--out", default=str(ROOT / "artifacts" / "scout-update" / "sequence-map.json"))
    bind.set_defaults(func=cmd_bind)

    stage = sub.add_parser("stage", parents=[common], help="copy the port's hero scripts and graphs verbatim")
    stage.add_argument("--hero", default="", help="the live hero this port replaces")
    stage.add_argument("--out", required=True)
    stage.set_defaults(func=cmd_stage)

    graph = sub.add_parser("animgraph", help="retarget one AnimGraph 2 document to a skeleton")
    graph.add_argument("--template", required=True)
    graph.add_argument("--skeleton", required=True, help="the port's skeleton DMX or vnmskel path")
    graph.add_argument("--variation", required=True)
    graph.add_argument("--label", default="", help="a one-line note written above the document")
    graph.add_argument("--out", required=True)
    graph.add_argument("--compile", action="store_true")
    graph.add_argument("--csdk", default="")
    graph.add_argument("--log", default="")
    graph.add_argument("--receipt", default="")
    graph.set_defaults(func=cmd_animgraph)

    variation = sub.add_parser(
        "variation", help="add a variation to a fused AnimGraph 2 document by cloning a hero's"
    )
    variation.add_argument("--template", required=True, help="the fused document (hero_aim.vnmgraph)")
    variation.add_argument("--to", dest="target", required=True)
    variation.add_argument("--skeleton", default="", help="the variation's skeleton resource")
    variation.add_argument("--clip-from", default="")
    variation.add_argument("--clip-to", default="")
    variation.add_argument("--label", default="")
    variation.add_argument("--out", required=True)
    variation.add_argument("--compile", action="store_true")
    variation.add_argument("--csdk", default="")
    variation.add_argument("--log", default="")
    variation.add_argument("--receipt", default="")
    variation.set_defaults(func=cmd_variation)

    update = sub.add_parser(
        "update", parents=[common], help="update the port's hero table to the live build (keeps a backup)"
    )
    update.add_argument("--write", action="store_true", help="replace the table; without it the plan is printed")
    update.add_argument("--stem-hero-table", default="", help="the table's file name in the workspace")
    update.add_argument("--drop-port-only", action="store_true", help="drop entries the live build lacks")
    update.add_argument("--receipt", default="")
    update.set_defaults(func=cmd_update)

    authored = sub.add_parser(
        "graph", help="author a custom animgraph19 on the port's own sequences"
    )
    authored.add_argument("--template", required=True, help="an animgraph19 template from the Dota tools")
    authored.add_argument("--out", required=True)
    authored.add_argument("--workspace", default="", help="the port workspace to read $sequence names from")
    authored.add_argument("--sequences-from", default="", help="a file of sequence names, one per line")
    authored.add_argument("--model", default="", help="the model resource the graph binds to")
    authored.add_argument("--label", default="")
    authored.add_argument("--compile", action="store_true")
    authored.add_argument("--dota-tools", default="")
    authored.add_argument("--game", default="", help="the live Deadlock install root")
    authored.add_argument("--log", default="")
    authored.add_argument("--receipt", default="")
    authored.set_defaults(func=cmd_graph)

    serve = sub.add_parser("serve", help="host the tool's Popit UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8791)
    serve.add_argument("--report", default=str(REPORT))
    serve.set_defaults(func=cmd_serve)

    probe = sub.add_parser("probe", parents=[common], help="run the tool and gate its Popit UI")
    probe.add_argument("--json", default=str(REPORT))
    probe.add_argument(
        "--variation", default="", help="a hero variation document to show as the bake target"
    )
    probe.add_argument("--receipt", default=str(ROOT / "artifacts" / "receipts" / "scout-update-popit.json"))
    probe.set_defaults(func=cmd_probe)

    args = parser.parse_args(argv)
    if getattr(args, "graph", None) is None:
        args.graph = []
    try:
        return args.func(args)
    except scout.ScoutError as error:
        code, _, detail = str(error).partition(":")
        print(f"REFUSED {code.strip()}: {detail.strip()}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
