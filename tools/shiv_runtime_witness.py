"""Launch the retail client against an installed pak and read what the engine says.

The loaded game is the only acceptance surface, but a launch witness and a visual
acceptance are different claims.  This tool makes only the first one: it starts
`deadlock.exe` with the flags recorded in
`artifacts/mayu-launch/launch-report.json`, waits for `game/citadel/console.log`
to grow, collects every line that names the hero, the addon pak, a skeleton, a
clip document, or a resource failure, and then stops the process it started.

It never sends a keystroke, a click or a console command to the client: the
owner drives the game, and a scripted input stream both guesses keybinds and
steals focus.  What it can prove is that the pak mounts, that the model and its
clips load, and which assets the engine reports missing.  What it cannot prove
is how the character looks.

  python tools/shiv_runtime_witness.py --pak artifacts/oldviper/shiv_noskel.vpk --wait 150
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = Path(r"D:\SteamLibrary\steamapps\common\Deadlock")
CLIENT = GAME / "game" / "bin" / "win64" / "deadlock.exe"
ADDONS = GAME / "game" / "citadel" / "addons"
CONSOLE = GAME / "game" / "citadel" / "console.log"
INSTALLED = ADDONS / "pak97_dir.vpk"

ARGV = [
    str(CLIENT),
    "-steam",
    "-console",
    "-condebug",
    "-dev",
    "-windowed",
    "-w",
    "1280",
    "-h",
    "720",
    "-allow_no_lobby_connect",
    "-insecure",
    "-noassert",
    "-DANGER_MODE_ignore_schema_mismatches",
]

# Every pattern is a claim the engine makes in its own words, so a match is
# evidence and the absence of one is reported as absence rather than as success.
PATTERNS = {
    "addon_pak": re.compile(r"pak97", re.I),
    "hero": re.compile(r"hero_shiv|Loaded hero", re.I),
    "model": re.compile(r"shiv\.vmdl", re.I),
    "skeleton": re.compile(r"vnmskel", re.I),
    "clip": re.compile(r"clips/.*vnmclip", re.I),
    "missing_resource": re.compile(r"Failed loading resource|doesn't exist|Unable to load|CModel|bone", re.I),
}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def running() -> list[str]:
    try:
        text = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq deadlock.exe"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in text.splitlines() if "deadlock.exe" in line.lower()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pak", default=str(INSTALLED))
    parser.add_argument("--wait", type=int, default=150)
    parser.add_argument("--report", default=str(ROOT / "artifacts" / "receipts" / "shiv-runtime-witness.json"))
    args = parser.parse_args()

    report: dict = {
        "schema": "hero-retarget-workbench.runtime-witness/1",
        "at": datetime.now(timezone.utc).isoformat(),
        "source": "agent",
        "visual_confirmation": "outstanding: this tool cannot see the character",
    }
    if not CLIENT.is_file():
        report["result"] = "blocked"
        report["blocked"] = f"client missing: {CLIENT}"
    elif running():
        report["result"] = "refused"
        report["blocked"] = "deadlock.exe already running; not touching the owner's session"
    else:
        before = CONSOLE.stat().st_size if CONSOLE.is_file() else 0
        report["installed_sha256"] = sha256(INSTALLED)
        report["launch_argv"] = ARGV
        process = subprocess.Popen(ARGV, cwd=str(CLIENT.parent))
        report["pid"] = process.pid
        deadline = time.time() + args.wait
        text = ""
        while time.time() < deadline:
            if process.poll() is not None:
                break
            time.sleep(5)
            if CONSOLE.is_file() and CONSOLE.stat().st_size > before:
                # Slice by BYTES: the log mixes encodings, so a character offset
                # derived from a byte size silently re-reads old lines and reports
                # a previous session as this one.
                raw = CONSOLE.read_bytes()[before:]
                text = raw.decode("utf-8", errors="replace")
                if PATTERNS["hero"].search(text):
                    break
        report["console_offset"] = before
        report["first_line"] = text.strip().splitlines()[0][:160] if text.strip() else None
        report["last_line"] = text.strip().splitlines()[-1][:160] if text.strip() else None
        report["exit_code"] = process.poll()
        report["console_bytes_read"] = len(text)
        hits: dict[str, list[str]] = {}
        for name, pattern in PATTERNS.items():
            lines = [line.strip() for line in text.splitlines() if pattern.search(line)]
            hits[name] = lines[:40]
        report["hits"] = hits
        report["counts"] = {name: len(lines) for name, lines in hits.items()}
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                process.kill()
            report["stopped"] = "terminated by witness after the wait window"
        report["result"] = "observed" if text else "no-log"
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("result", "blocked", "counts", "console_bytes_read")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
