"""Which material paths the game's own pak01 already provides.

A port ships what it changes.  A compiled `*.vmat_c` or `*.vtex_c` whose path
already exists in pak01 shadows a working game material with a half-compiled
copy, and that is how a port loses its surfaces.  This module answers one
question for the packer: is this material path already the game's?

The listing is cached in `artifacts/receipts/pak01-material-paths.txt` so a
release does not read the pak twice.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
S2V = Path("<home>/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
PAK01 = Path("D:/SteamLibrary/steamapps/common/Deadlock/game/citadel/pak01_dir.vpk")
CACHE = REPO / "artifacts" / "receipts" / "pak01-material-paths.txt"


def game_material_paths() -> set[str]:
    """Every material path pak01 provides, lower-cased with forward slashes."""
    if not CACHE.is_file():
        if not PAK01.is_file():
            raise SystemExit(f"refused materials-shadow-game: the game's pak01 is not readable at {PAK01}")
        proc = subprocess.run(
            [str(S2V), "-i", str(PAK01), "-l", "-e", "vmat_c,vtex_c"],
            capture_output=True,
            text=True,
        )
        lines = [line.split(" CRC:")[0].strip().lower() for line in (proc.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise SystemExit(
                "refused materials-shadow-game: pak01 listing came back empty: "
                + (proc.stderr or "")[-300:]
            )
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {line.strip() for line in CACHE.read_text(encoding="utf-8").splitlines() if line.strip()}
