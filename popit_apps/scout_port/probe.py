"""Gate the Scout Port application the way the family gates a Popit surface: read the page.

A print can say pass while the surface the owner would read shows nothing, so this probe starts the
application's own server on an ephemeral port, fetches `/` and `/api/state` over loopback HTTP, and
fails by name unless the page carries its contract and the served state agrees with itself.

  python popit_apps/scout_port/probe.py
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT))

import server  # noqa: E402

REQUIRED_IDS = ("port-state", "step-table", "superseded", "counts")


def fetch(port: int, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=15) as response:
        return response.status, response.read()


def main() -> int:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    checks: list[dict] = []
    try:
        status, page = fetch(port, "/")
        text = page.decode("utf-8", errors="replace")
        checks.append({"name": "page-served", "ok": status == 200 and "<html" in text.lower(), "detail": f"HTTP {status}"})
        checks.append(
            {"name": "page-popit-attribute", "ok": 'data-popit="scout-port"' in text, "detail": 'data-popit="scout-port"'}
        )
        missing = [identifier for identifier in REQUIRED_IDS if f'id="{identifier}"' not in text]
        checks.append({"name": "page-ids", "ok": not missing, "detail": f"missing {missing}" if missing else "all present"})

        status, raw = fetch(port, "/api/state")
        body = json.loads(raw)
        checks.append(
            {
                "name": "state-schema",
                "ok": body.get("schema") == "deadlock-model-forge.scout-port-app/1",
                "detail": str(body.get("schema")),
            }
        )
        steps = body.get("steps") or []
        shaped = bool(steps) and all({"id", "label", "state", "detail"} <= set(step) for step in steps)
        checks.append({"name": "steps-shaped", "ok": shaped, "detail": f"{len(steps)} steps"})

        skeleton = next((step for step in steps if step["id"] == "skeleton"), {})
        refusal_ok = skeleton.get("state") == "pass" or skeleton.get("refusal") == "skeleton-not-built"
        checks.append(
            {
                "name": "skeleton-named",
                "ok": refusal_ok,
                "detail": skeleton.get("detail", "no skeleton step"),
            }
        )

        clips_step = next((step for step in steps if step["id"] == "clips"), {})
        clips_state = clips_step.get("state", "")
        clips_counts = clips_step.get("counts") or {}
        clips_ok = (
            clips_state == "pass"
            and clips_counts.get("clips") == 4
            and clips_counts.get("channels") == 156
            and clips_counts.get("joints") == 78
            and clips_counts.get("frames") == "21/20/2/2"
            and not clips_step.get("refusal")
        )
        checks.append(
            {
                "name": "clips-step",
                "ok": clips_ok,
                "detail": f"{clips_state}: {clips_step.get('detail', '')[:110]}",
            }
        )

        graph_step = next((step for step in steps if step["id"] == "graph"), {})
        graph_counts = graph_step.get("counts") or {}
        graph_ok = (
            graph_step.get("state") == "pass"
            and graph_counts.get("clips", 0) == 4
            and graph_counts.get("joints", 0) == 78
            and graph_counts.get("motion_states", 0) == 2
            and graph_counts.get("aim_poses", 0) == 2
            and graph_counts.get("graph_bytes", 0) > 0
        )
        checks.append(
            {
                "name": "graph-step",
                "ok": graph_ok,
                "detail": f"{graph_step.get('state')}: {graph_step.get('detail', '')[:110]}",
            }
        )
        downstream = {step["id"]: step for step in steps}
        pack_step = downstream.get("pack", {})
        pack_ok = (
            pack_step.get("state") == "pass"
            and (pack_step.get("counts") or {}).get("files", 0) > 0
            and (pack_step.get("counts") or {}).get("vpk_entries", 0) > 0
        )
        hero_step = downstream.get("hero", {})
        hero_counts = hero_step.get("counts") or {}
        hero_ok = (
            hero_step.get("state") == "pass"
            and not hero_step.get("refusal")
            and hero_counts.get("paths", 0) > 0
            and hero_counts.get("resolved") == hero_counts.get("paths")
            and hero_counts.get("ui_paths", 0) > 0
            and hero_counts.get("ui_resolved") == hero_counts.get("ui_paths")
            and hero_counts.get("graph_matches_compiled") is True
        )
        checks.append(
            {
                "name": "hero-registered",
                "ok": hero_ok,
                "detail": f"{hero_step.get('state')}: {hero_step.get('detail', '')[:130]}",
            }
        )
        binding = hero_step.get("binding") or {}
        checks.append(
            {
                "name": "ag2-binding-named",
                "ok": binding.get("state") == "unverified"
                and binding.get("refusal") == "ag2-hero-variation-required"
                and binding.get("form") == "standalone",
                "detail": f"{binding.get('named', 'no graph')}: {binding.get('refusal', 'no refusal')} — {binding.get('detail', '')[:110]}",
            }
        )
        refused = [
            name
            for name in ("in_game",)
            if downstream.get(name, {}).get("refusal")
        ]
        checks.append(
            {
                "name": "downstream-refused",
                "ok": pack_ok and hero_ok and len(refused) == 1 and downstream.get("graph", {}).get("state") == "pass",
                "detail": f"pack {pack_step.get('state', 'missing')}; hero {hero_step.get('state', 'missing')}; refused by name: {', '.join(refused)}",
            }
        )

        mesh_step = downstream.get("mesh", {})
        mesh_counts = mesh_step.get("counts") or {}
        mesh_ok = (
            mesh_step.get("state") == "converted"
            and not mesh_step.get("refusal")
            and mesh_counts.get("vertices") == 8261
            and mesh_counts.get("faces") == 7814
            and mesh_counts.get("joints") == 78
            and mesh_counts.get("vmt") == 15
            and mesh_counts.get("vmat") == 15
            and mesh_counts.get("dmx_bytes", 0) > 0
        )
        checks.append(
            {
                "name": "mesh-converted",
                "ok": mesh_ok,
                "detail": f"{mesh_step.get('state')}: {mesh_step.get('refusal', '') or 'no refusal'} — {mesh_step.get('detail', '')[:110]}",
            }
        )

        counts = body.get("counts") or {}
        agrees = counts.get("steps_pass", -1) + counts.get("steps_blocked", -1) <= len(steps)
        checks.append({"name": "counts-agree", "ok": agrees, "detail": json.dumps(counts)})

        port = body.get("port") or {}
        sequences_ok = isinstance(port.get("sequences"), int) and port.get("workspace")
        checks.append(
            {
                "name": "port-read",
                "ok": bool(sequences_ok),
                "detail": f"{port.get('workspace')} · {port.get('sequences')} sequences · {port.get('anim_smd')} anim SMD",
            }
        )
    finally:
        httpd.shutdown()
        httpd.server_close()

    failed = [check for check in checks if not check["ok"]]
    receipt = ROOT / "artifacts" / "receipts" / "scout-port-app-probe.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "schema": "deadlock-model-forge.scout-port-app-probe/1",
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "checks": checks,
                "failed": [check["name"] for check in failed],
                "result": "PASS" if not failed else "FAIL",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for check in checks:
        print(f"  [{'PASS' if check['ok'] else 'FAIL'}] {check['name']}: {check['detail'][:120]}")
    print(f"RESULT: {'PASS' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)} checks)")
    print(f"receipt: {receipt}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
