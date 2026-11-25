"""Probe: does the owner's old VPK update now that the roster lookup cannot refuse?

The Mods page failed with:

    failed: Live hero models/heroes_staging/nano/nano_v2/nano.vmdl_c is no longer in the roster

That text is a *model path*, because `settings.hero_slug` holds the picker's model path. The probe
reproduces the GUI's own call headlessly: read the live roster, resolve that exact string with
`forge.live.resolve_hero`, then run `forge.migrate.update_from_package` with the owner's settings
(preserve custom only, keep cloth/physics, copy old materials).

It writes `artifacts/receipts/update-old-vpk-probe.json` and prints one line per step. Run it with the
repository's Python, from the repository root:

    python data/probes/2026-11-25-update-old-vpk-probe.py [--hero <slug-or-path>] [--keep]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from forge import live, migrate  # noqa: E402
from forge.paths import Environment  # noqa: E402

def _from_env(name: str, fallback: str = "") -> Path:
    """A path the probe reads from the environment, so no user folder is committed.

    Set `DMF_PACKAGE`, `DMF_GAME`, `DMF_CSDK` and `DMF_S2V` (the Source 2 Viewer **CLI** build; the
    GUI builds emit no `heroes.vdata`).
    """
    value = os.environ.get(name, fallback)
    if not value:
        raise SystemExit(f"{name} is not set; see this file's docstring")
    return Path(value)


PACKAGE = _from_env("DMF_PACKAGE", r"F:\Downloaded Files\avahead_calico_v2\pak04_dir.vpk")
GAME = _from_env("DMF_GAME", r"D:\SteamLibrary\steamapps\common\Deadlock")
CSDK = _from_env("DMF_CSDK")
S2V = _from_env("DMF_S2V")
# The exact value the Mods page reported as the hero.
FAILING = "models/heroes_staging/nano/nano_v2/nano.vmdl_c"


def environment() -> Environment:
    return Environment(
        game_root=GAME,
        game_dir=GAME / "game",
        vpk=GAME / "game" / "citadel" / "pak01_dir.vpk",
        gameinfo=GAME / "game" / "citadel" / "gameinfo.gi",
        s2v=S2V,
        csdk_root=CSDK,
        resourcecompiler=CSDK / "game" / "bin" / "win64" / "resourcecompiler.exe",
        csdk_gameinfo=CSDK / "game" / "citadel" / "gameinfo.gi",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero", default=FAILING)
    parser.add_argument("--keep", action="store_true", help="keep the migrated tree for inspection")
    args = parser.parse_args()

    receipt = {
        "schema": "dmf.update-old-vpk-probe/1",
        "package": str(PACKAGE),
        "hero_selected": args.hero,
        "heroes_in_roster": 0,
        "resolution": None,
        "resolution_note": "",
        "migration": None,
        "error": "",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    print(f"package present: {PACKAGE.is_file()}", flush=True)
    print(f"s2v present: {S2V.is_file()}  csdk present: {CSDK.is_dir()}", flush=True)

    env = environment()
    started = time.time()
    try:
        heroes = live.list_heroes(env)
        receipt["heroes_in_roster"] = len(heroes)
        print(f"roster: {len(heroes)} heroes in {time.time() - started:.1f}s", flush=True)

        hero, note = live.resolve_hero(heroes, args.hero)
        receipt["resolution"] = None if hero is None else {
            "slug": hero.slug,
            "model_path": hero.model_path,
            "title": hero.title,
        }
        receipt["resolution_note"] = note
        print(f"resolution: {receipt['resolution']}  note={note}", flush=True)

        output = ROOT / "artifacts" / "probes" / "old-vpk-update"
        result = migrate.update_from_package(
            env,
            PACKAGE,
            output,
            "avahead_calico_v3_probe",
            hero=hero,
            preserve_model="auto",
            preserve_materials=True,
            sections=None,
            force=True,
        )
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        receipt["migration"] = {
            "output": str(result.output),
            "vmdl": str(result.vmdl),
            "preserved_model": result.preserved_model,
            "model_files": result.model_files,
            "new_model_files": result.new_model_files,
            "material_count": result.material_count,
            "material_texture_count": result.material_texture_count,
            "sections": {name: value.get("action", "") for name, value in result.sections.items()},
            "cloth_chains": manifest.get("cloth_chains", 0),
            "cloth_hinges": manifest.get("cloth_hinges", 0),
            "seconds": round(time.time() - started, 1),
        }
        print(json.dumps(receipt["migration"], indent=2), flush=True)
    except Exception as error:  # the probe records the refusal instead of hiding it
        receipt["error"] = f"{type(error).__name__}: {error}"
        print("PROBE ERROR: " + receipt["error"], flush=True)
        traceback.print_exc()
    finally:
        receipts = ROOT / "artifacts" / "receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        if not args.keep:
            receipt["kept_tree"] = False
        (receipts / "update-old-vpk-probe.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        print("receipt: artifacts/receipts/update-old-vpk-probe.json", flush=True)
    return 0 if not receipt["error"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
