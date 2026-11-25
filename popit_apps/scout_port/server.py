"""Scout Port — a Popit-shell application for the Deadlock Model Forge's Scout port.

The pattern is the shell's own (`popit-shell/server.py`, whose docstring names the session archive as
the model): one loopback ThreadingHTTPServer over a folder, no framework, one JSON API, a view that
reads it. This application is the port's dashboard: it reads the port on `F:/Documents` and the forge's
own receipts, and it says what is built and what is refused.

It never claims a step it cannot read from a file. The port is the TF2 Scout model with its own
skeleton and its own animations — nothing here is bound to a Deadlock dev hero's rig.

  python popit_apps/scout_port/server.py            # http://127.0.0.1:8795/
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP = Path(__file__).resolve().parent
ROOT = APP.parents[1]
sys.path.insert(0, str(ROOT))

from forge import scout  # noqa: E402

UI = APP / "ui"
PORT = int(os.environ.get("SCOUT_PORT_APP_PORT", "8795"))
WORKSPACE = Path(os.environ.get("SCOUT_PORT_WORKSPACE", "F:/Documents"))
ARTIFACTS = ROOT / "artifacts"
PACK_RECEIPT = ARTIFACTS / "receipts" / "scout-install.json"
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def _count(directory: Path, pattern: str) -> int:
    return len(list(directory.glob(pattern))) if directory.is_dir() else 0


def _first(roots: list[Path], pattern: str) -> str:
    for root in roots:
        if not root.is_dir():
            continue
        found = sorted(root.rglob(pattern))
        if found:
            return str(found[0])
    return ""


def skeleton_state() -> dict:
    """Scout's own animation skeleton, from the forge's artifacts.

    The port ships a Source 1 model and SMDs; a Deadlock hero needs a `.vnmskel` built from *that*
    rig. Until one exists the clip bake has no target and says so by name.
    """
    found = sorted(ARTIFACTS.rglob("scout*.vnmskel")) + sorted(ARTIFACTS.rglob("scout*.vnmskel_c"))
    # A verify dump is a decompiled copy, not the built skeleton; the built one is what this step reads.
    authored = [path for path in found if "verify" not in str(path).lower()]
    found = authored or found
    if found:
        return {"state": "present", "path": str(found[0]), "bytes": found[0].stat().st_size}
    return {
        "state": "missing",
        "path": "",
        "refusal": "skeleton-not-built",
        "detail": "no scout.vnmskel under artifacts/; the port's own rig has not been converted",
    }


ANIM = ARTIFACTS / "scout-anim" / "parsed"
ANIM_CLIPS = ("Scout_Attack", "Scout_Reload", "Scout_AimIdle", "Scout_AimRun")


def clips_state(root: Path | None = None) -> dict:
    """The four clips as each compiled document parses, not as the bake reported them.

    `tools/scout_anim.py` decompiles every compiled `vnmclip_c`, converts its animation DMX and writes
    the counts it measured to `artifacts/scout-anim/parsed/<clip>.json`. This reads those measurements;
    a clip without one is missing, whatever the bake said.
    """
    base = Path(root or ANIM)
    rows: dict[str, dict] = {}
    for name in ANIM_CLIPS:
        path = base / f"{name}.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("ok") and data.get("channels", 0) and data.get("track_joints", 0):
            rows[name] = data
    missing = [name for name in ANIM_CLIPS if name not in rows]
    channels = sorted({int(data["channels"]) for data in rows.values()})
    joints = sorted({int(data["track_joints"]) for data in rows.values()})
    frames = [int(data.get("frames") or 0) for name in ANIM_CLIPS if name in rows for data in (rows[name],)]
    counts = {
        "clips": len(rows),
        "channels": channels[0] if len(channels) == 1 else 0,
        "joints": joints[0] if len(joints) == 1 else 0,
        "frames": "/".join(str(value) for value in frames),
    }
    if not rows:
        return {
            "state": "ready",
            "refusal": "clips-not-converted",
            "detail": "no parsed clip documents under artifacts/scout-anim/parsed",
            "counts": counts,
        }
    if missing:
        return {
            "state": "partial",
            "refusal": "clips-partial",
            "detail": f"{len(rows)}/4 clips parsed, missing {', '.join(missing)}",
            "counts": counts,
        }
    return {
        "state": "pass",
        "refusal": "",
        "detail": (
            f"{len(rows)}/4 clips parsed, {counts['channels']} channel tracks "
            f"({counts['channels'] // 2} joints x position+orientation), frames {counts['frames']}"
        ),
        "counts": counts,
    }


MESH_FILES = ("scout.mdl", "scout.vvd", "scout.dx90.vtx", "scout.obj", "scout.phy", "scout.qc")
MESH_OUT = "scout-mesh"
MESH_DMX_REF = "models/heroes_wip/scout/dmx/mesh/scout_body.dmx"
MODEL_VMDL_REF = "models/heroes_wip/scout/scout_body.vmdl"
MATERIALS_DIR = "models/heroes_wip/scout/materials"
MATERIAL_TOTAL = 15


def _port_geometry(root: Path) -> dict:
    files = {name: (root / name).stat().st_size for name in MESH_FILES if (root / name).is_file()}
    textures = _count(root / "scout", "*.vtf")
    vertices = faces = 0
    obj = root / "scout.obj"
    if obj.is_file():
        for line in obj.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("v "):
                vertices += 1
            elif line.startswith("f "):
                faces += 1
    return {"files": files, "textures": textures, "vertices": vertices, "faces": faces}


def mesh_state(workspace: Path | None = None, root: Path | None = None) -> dict:
    """The converted mesh, read back from the files the conversion wrote.

    The step is `converted` only when all three deliverables exist and the mesh DMX parses back to real
    geometry weighted to the skeleton: the DMX itself, a model definition whose `RenderMeshFile` names
    it, and 15 `.vmt` plus 15 `.vmat` definitions. Anything present but incomplete is `mesh-partial`
    with the missing pieces named; nothing present falls back to the port's sources.
    """
    port = Path(workspace or WORKSPACE)
    base = Path(root or (ARTIFACTS / MESH_OUT))
    source = _port_geometry(port)
    dmx = base / MESH_DMX_REF
    vmdl = base / MODEL_VMDL_REF
    materials = base / MATERIALS_DIR
    vmts = sorted(materials.glob("*.vmt"))
    vmats = sorted(materials.glob("*.vmat"))
    facts: dict = {}
    error = ""
    if dmx.is_file():
        try:
            from forge import meshbuild

            facts = meshbuild.inspect_mesh_dmx(dmx)
        except (OSError, ValueError) as exc:
            error = str(exc)
    reference = ""
    if vmdl.is_file():
        found = re.search(r'filename = "([^"]+)"', vmdl.read_text(encoding="utf-8", errors="replace"))
        reference = found.group(1) if found else ""
    expected_reference = MESH_DMX_REF[len("models/"):]
    missing = []
    if not dmx.is_file():
        missing.append("mesh DMX")
    if not vmdl.is_file() or reference != expected_reference:
        missing.append("model definition")
    if len(vmts) < MATERIAL_TOTAL:
        missing.append(f"{MATERIAL_TOTAL - len(vmts)} .vmt")
    if len(vmats) < MATERIAL_TOTAL:
        missing.append(f"{MATERIAL_TOTAL - len(vmats)} .vmat")
    counts = {
        "dmx_bytes": dmx.stat().st_size if dmx.is_file() else 0,
        "vertices": int(facts.get("vertex_count") or 0),
        "faces": int(facts.get("face_count") or 0),
        "joints": int(facts.get("joint_count") or 0),
        "vmt": len(vmts),
        "vmat": len(vmats),
        "textures": source["textures"],
        "mdl_bytes": source["files"].get("scout.mdl", 0),
    }
    weights = (
        f"weights {facts['weight_min']}–{facts['weight_max']}"
        if facts.get("weight_rows")
        else "weights unread"
    )
    if not missing and not error and counts["vertices"] and counts["faces"] and counts["joints"]:
        return {
            "state": "converted",
            "refusal": "",
            "detail": (
                f"{counts['vertices']:,} verts / {counts['faces']:,} faces, {counts['joints']} joints, "
                f"{weights}, {counts['dmx_bytes']:,} B DMX, {counts['vmt']} .vmt / {counts['vmat']} .vmat"
            ),
            "counts": counts,
            "path": str(dmx),
            "model": str(vmdl),
        }
    if dmx.is_file() or vmdl.is_file() or vmts or vmats:
        reason = ", ".join(missing) if missing else error
        return {
            "state": "partial",
            "refusal": "mesh-partial",
            "detail": f"conversion incomplete, missing {reason}",
            "counts": counts,
            "path": str(dmx) if dmx.is_file() else "",
            "model": str(vmdl) if vmdl.is_file() else "",
        }
    if not source["files"].get("scout.mdl") and not source["vertices"]:
        return {
            "state": "blocked",
            "refusal": "mesh-not-built",
            "detail": f"no scout.mdl and no scout.obj under {port}",
            "counts": counts,
            "source": source,
        }
    return {
        "state": "ready",
        "refusal": "mesh-not-converted",
        "detail": (
            f"scout.mdl {source['files'].get('scout.mdl', 0):,} B, OBJ {source['vertices']:,} verts / "
            f"{source['faces']:,} faces, {source['textures']} VTF textures; Source 1 model present, "
            "mesh DMX not built"
        ),
        "counts": counts,
        "source": source,
    }


def graph_state() -> dict:
    """The authored AnimGraph 2 document, read from its own build/compile/verify receipts."""
    receipt = ARTIFACTS / "receipts" / "scout-graph.json"
    if not receipt.is_file():
        return {"state": "ready", "detail": "no graph receipt yet", "clips": 0, "compiled": 0, "bytes": 0}
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"state": "ready", "detail": f"receipt unreadable: {error}", "clips": 0, "compiled": 0, "bytes": 0}
    compiled = int(data.get("compiled_documents") or 0)
    documents = int(data.get("document_total") or 0)
    verified = data.get("result") == "PASS"
    clips = data.get("clips") or {}
    found = sum(1 for value in clips.values() if value) if isinstance(clips, dict) else 0
    states = data.get("states_in_compiled") or []
    aims = data.get("aim_poses_in_compiled") or []
    detail = (
        f"{data.get('compiled_bytes', 0)} B compiled graph, {found}/{len(clips)} port clips, "
        f"{len(states)} motion states, {len(aims)} aim poses, {data.get('skeleton_joints', 0)} joints"
    )
    state = "pass" if verified and compiled and compiled == documents else "ready"
    if not verified:
        detail += "; compiled but not verified"
    # A graph is only reached when its clip references come out of its own compiled bytes, so prefer
    # the counts `tools/scout_anim.py` parsed from the decompiled graph to the bake's own list.
    anim = ARTIFACTS / "receipts" / "scout-anim.json"
    parsed: dict = {}
    if anim.is_file():
        try:
            parsed = json.loads(anim.read_text(encoding="utf-8")).get("graph") or {}
        except (OSError, ValueError):
            parsed = {}
    if parsed.get("available"):
        references = parsed.get("clip_references") or []
        found = len(references)
        states = parsed.get("states") or []
        aims = parsed.get("aim_states") or []
        detail = (
            f"{parsed.get('compiled_bytes', 0)} B compiled graph, {found} clip references from "
            f"sequence/pose nodes, {len(states)} motion states, {len(aims)} aim states, "
            f"{data.get('skeleton_joints', 0)} joints"
        )
        state = "pass" if verified and compiled and compiled == documents and found == 4 else "ready"
    return {
        "state": state,
        "detail": detail,
        "clips": found,
        "compiled": compiled,
        "documents": documents,
        "bytes": int(parsed.get("compiled_bytes") or data.get("compiled_bytes") or 0),
        "joints": int(data.get("skeleton_joints") or 0),
        "states": len(states),
        "aim_poses": len(aims),
        "frank": bool(data.get("frank_references") or parsed.get("frank_references")),
    }


def pack_state() -> dict:
    """The addon as it sits in the live game, read back from the install receipt and its files."""
    if not PACK_RECEIPT.is_file():
        return {
            "state": "ready",
            "detail": "no install receipt: `python tools/scout_install.py install` writes it",
            "refusal": "pack-not-built",
            "counts": {},
        }
    data = json.loads(PACK_RECEIPT.read_text(encoding="utf-8"))
    files = data.get("files") or []
    missing = [row["path"] for row in files if not Path(row.get("installed", "")).is_file()]
    if not files or missing:
        return {
            "state": "ready",
            "detail": f"install receipt names {len(files)} files, {len(missing)} absent from the addon folder",
            "refusal": "pack-not-built",
            "counts": {},
        }
    counts = data.get("counts") or {}
    vpk = data.get("vpk") or {}
    return {
        "state": "pass",
        "detail": (
            f"{len(files)} compiled files installed at {data.get('target')}; "
            f"VPK {vpk.get('entries', 0)} entries, {vpk.get('bytes', 0)} B"
        ),
        "refusal": "",
        "counts": {
            "files": len(files),
            "bytes": sum(int(row.get("bytes", 0)) for row in files),
            "clips": int(counts.get("clips", 0)),
            "dmx": int(counts.get("dmx", 0)),
            "materials": int(counts.get("materials", 0)),
            "vpk_bytes": int(vpk.get("bytes", 0)),
            "vpk_entries": int(vpk.get("entries", 0)),
        },
    }


def hero_state() -> dict:
    """Scout's hero entry, read from the install receipt and resolved against the installed files."""
    if not PACK_RECEIPT.is_file():
        return {
            "state": "blocked",
            "detail": "no install receipt: `python tools/scout_install.py install` registers the hero",
            "refusal": "hero-not-registered",
            "counts": {},
        }
    data = json.loads(PACK_RECEIPT.read_text(encoding="utf-8"))
    hero = data.get("hero") or {}
    paths = hero.get("paths") or []
    missing = [row.get("named", "") for row in paths if not Path(row.get("installed", "")).is_file()]
    ui = hero.get("ui") or []
    ui_missing = [row.get("named", "") for row in ui if not Path(row.get("installed", "")).is_file()]
    if not hero or not paths or missing or not hero.get("resolved_all") or not ui or ui_missing or not hero.get("ui_resolved_all"):
        return {
            "state": "blocked",
            "detail": (
                f"hero entry {hero.get('hero', 'hero_scout')} names {len(paths)} model and {len(ui)} image paths, "
                f"{len(missing) + len(ui_missing)} absent"
            ),
            "refusal": "hero-not-registered",
            "counts": {"paths": len(paths), "resolved": len(paths) - len(missing), "ui_paths": len(ui), "ui_resolved": len(ui) - len(ui_missing)},
        }
    binding = hero.get("graph_binding") or {}
    return {
        "state": "pass",
        "detail": (
            f"{hero.get('hero')} id {hero.get('hero_id')} registered against {hero.get('table_installed')}; "
            f"{len(paths)} model and {len(ui)} image paths resolve in the installed copy; "
            f"graph md5 matches the compiled one; graph binding {binding.get('refusal', 'unchecked')}"
        ),
        "refusal": "",
        "counts": {
            "hero_id": int(hero.get("hero_id") or 0),
            "paths": len(paths),
            "resolved": len(paths) - len(missing),
            "ui_paths": len(ui),
            "ui_resolved": len(ui) - len(ui_missing),
            "maps": len(hero.get("maps") or []),
            "graph_matches_compiled": bool(hero.get("graph_matches_compiled")),
            "table_bytes": int((hero.get("table_compile") or {}).get("bytes") or 0),
        },
        "binding": binding,
    }


def superseded() -> list[dict]:
    """Artifacts built against a different rig, kept and named instead of deleted."""
    rows = []
    if (ARTIFACTS / "scout-update" / "clips").is_dir():
        rows.append(
            {
                "path": "artifacts/scout-update/clips",
                "why": "baked against models/heroes_wip/frank/frank.vnmskel, not the port's own rig",
            }
        )
    if (ARTIFACTS / "scout-update" / "vpk" / "scout_animgraph_dir.vpk").is_file():
        rows.append(
            {
                "path": "artifacts/scout-update/vpk/scout_animgraph_dir.vpk",
                "why": "packs the same frank-bound clips plus a hero table entry",
            }
        )
    return rows


def state() -> dict:
    sources = scout.scan_sources(WORKSPACE) if WORKSPACE.is_dir() else None
    sequences = list(scout.port_sequences(WORKSPACE)) if WORKSPACE.is_dir() else []
    skeleton = skeleton_state()
    clips = clips_state()
    graph = graph_state()
    mesh = mesh_state()
    pack = pack_state()
    hero = hero_state()
    dota = (ARTIFACTS / "dota-tools" / "game" / "bin" / "win64" / "resourcecompiler.exe").is_file()
    cskd_root = os.environ.get("CSDK_ROOT", "")
    cskd = Path(cskd_root) if cskd_root else None
    steps = [
        {
            "id": "inventory",
            "label": "Read the port",
            "state": "pass" if sources and sequences else "missing",
            "detail": (
                f"{len(sequences)} $sequence names, {sources.anim_smd} animation SMD"
                if sources
                else f"workspace not found: {WORKSPACE}"
            ),
        },
        {
            "id": "skeleton",
            "label": "Build Scout's own skeleton DMX and `.vnmskel`",
            "state": "pass" if skeleton["state"] == "present" else "blocked",
            "detail": skeleton.get("path") or skeleton["detail"],
            "refusal": skeleton.get("refusal", ""),
        },
        {
            "id": "clips",
            "label": "Bake the port's SMD clips onto that skeleton",
            "state": "blocked" if skeleton["state"] != "present" else clips["state"],
            "detail": clips["detail"]
            if skeleton["state"] == "present"
            else "SMD -> DMX with the skeleton's own joint order, then one `.vnmclip` per clip",
            "refusal": "skeleton-not-built" if skeleton["state"] != "present" else clips["refusal"],
            "counts": clips["counts"],
        },
        {
            "id": "graph",
            "label": "Author Scout's own AnimGraph 2 and compile it",
            "state": graph["state"] if skeleton["state"] == "present" else "blocked",
            "detail": graph["detail"]
            if skeleton["state"] == "present"
            else "the graph is authored over the port's own clips and skeleton",
            "refusal": "" if graph["state"] == "pass" else graph.get("refusal", "graph-not-compiled"),
            "counts": {
                "clips": graph["clips"],
                "compiled_documents": graph["compiled"],
                "graph_bytes": graph["bytes"],
                "joints": graph["joints"],
                "motion_states": graph["states"],
                "aim_poses": graph["aim_poses"],
            },
        },
        {
            "id": "pack",
            "label": "Pack the addon VPK and install it",
            "state": pack["state"] if graph["state"] == "pass" else "blocked",
            "detail": pack["detail"]
            if graph["state"] == "pass"
            else "the compiled graph, clips, skeleton and DMX are not packed into a `_dir.vpk` yet",
            "refusal": pack["refusal"] if graph["state"] == "pass" else "pack-not-built",
            "counts": pack["counts"],
        },
        {
            "id": "mesh",
            "label": "Convert Scout's mesh into a Deadlock mesh DMX",
            "state": mesh["state"],
            "detail": mesh["detail"],
            "refusal": mesh["refusal"],
            "counts": mesh["counts"],
        },
        {
            "id": "hero",
            "label": "Register Scout as a separate selectable hero",
            "state": hero["state"] if pack["state"] == "pass" else "blocked",
            "detail": hero["detail"]
            if pack["state"] == "pass"
            else "the hero entry is compiled into the addon with the pack",
            "refusal": hero["refusal"] if pack["state"] == "pass" else "hero-not-registered",
            "counts": hero["counts"],
            "binding": hero.get("binding", {}),
        },
        {
            "id": "in_game",
            "label": "Observe Scout playing in a match",
            "state": "blocked",
            "detail": "nothing in this slice was launched; the earlier addon crashed the client and is disabled",
            "refusal": "not-observed",
        },
    ]
    return {
        "schema": "deadlock-model-forge.scout-port-app/1",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "port": {
            "workspace": str(WORKSPACE),
            "qc": sources.qc if sources else "",
            "mdl": sources.mdl if sources else "",
            "smd": sources.smd if sources else 0,
            "anim_smd": sources.anim_smd if sources else 0,
            "anim_dirs": list(sources.anim_dirs) if sources else [],
            "sequences": len(sequences),
        },
        "tools": {
            "dota_tools": dota,
            "cskd13": bool(cskd) and (cskd / "game" / "bin" / "win64" / "resourcecompiler.exe").is_file(),
            "dota_path": str(ARTIFACTS / "dota-tools") if dota else "",
            "cskd_path": str(cskd) if cskd and (cskd / "game").is_dir() else "",
        },
        "steps": steps,
        "superseded": superseded(),
        "counts": {
            "smd": sources.smd if sources else 0,
            "anim_smd": sources.anim_smd if sources else 0,
            "sequences": len(sequences),
            "clips_parsed": clips["counts"]["clips"],
            "clip_channels": clips["counts"]["channels"],
            "clip_joints": clips["counts"]["joints"],
            "graph_compiled_documents": graph["compiled"],
            "graph_clips": graph["clips"],
            "graph_joints": graph["joints"],
            "steps_pass": sum(1 for step in steps if step["state"] == "pass"),
            "steps_blocked": sum(1 for step in steps if step["state"] == "blocked"),
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "scout-port-app/1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("scout-port: " + fmt % args + "\n")

    def send_body(self, body: bytes, kind: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
        path = urlparse(self.path).path
        if path == "/api/state":
            self.send_body(json.dumps(state()).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/sequences":
            try:
                names = list(scout.port_sequences(WORKSPACE))
            except (OSError, ValueError) as error:
                self.send_body(json.dumps({"ok": False, "refused": str(error)}).encode("utf-8"), TYPES[".json"], 409)
                return
            self.send_body(json.dumps({"sequences": names, "count": len(names)}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/":
            path = "/index.html"
        file = (UI / path.lstrip("/")).resolve()
        if not file.is_file() or UI not in file.parents:
            self.send_body(b"not found", "text/plain; charset=utf-8", 404)
            return
        self.send_body(file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"scout-port serving http://127.0.0.1:{server.server_port}/", flush=True)
    print(f"  workspace {WORKSPACE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
