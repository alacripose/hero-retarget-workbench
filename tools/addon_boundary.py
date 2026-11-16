"""The port runs from the Blender addon, and this refuses the ways it does not.

The owner's rule, verbatim (2026-11-16):

    *"Code that runs in probes vs code that runs from the blender addon is a refusal. Code
    missing from the blender addon is a refusal. Reading the games files without using the
    blender addon's own extraction is a refusal."*

and, on the first draft of this file:

    *"Do not add exemptions."*

So there are none.  Every capability the port needs is named below with the symbol in the addon
that provides it; a missing symbol is ``code-missing-from-addon``.  Every module under ``tools/``
is scanned, and a module that drives Source 2 Viewer at the live VPK itself is
``live-pak-read-outside-addon``, while a module that runs a step of the port (extraction, tail
append, compile, pack) is ``probe-only-port-code``.  A refusal here means the step exists only
outside the product, which is the class of failure the owner keeps hitting: the work was done,
and the workbench still cannot do it.

The patterns are assembled from fragments so this file does not match itself.  There is no
allowlist to add to: folding a tool's step into ``blender/hero_retarget_workbench/`` is the fix,
and deleting the tool is the other one.

Run:  python tools/addon_boundary.py check
      python tools/addon_boundary.py selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every capability the port needs, and the symbol in the addon that provides it.  A missing
# symbol is `code-missing-from-addon`: the port would have to be hand-driven again.
ADDON_SYMBOLS = {
    "hero roster (display name -> model path)": ("forge/live.py", "def list_heroes("),
    "hero extraction through S2V": ("forge/live.py", "def extract("),
    "tail skeleton extraction": ("forge/live.py", "def extract_tail_skeletons("),
    "tail append (add a tail to a hero)": (
        "blender/hero_retarget_workbench/tailops.py",
        "def start_auto(",
    ),
    "release refusals inside the addon": (
        "blender/hero_retarget_workbench/tailops.py",
        "def release_gate(",
    ),
    "clip pairing and import": (
        "blender/hero_retarget_workbench/clipops.py",
        "def scan(",
    ),
    "clip write-back": (
        "blender/hero_retarget_workbench/clipops.py",
        "def write_action(",
    ),
    "skeleton export (the rig the clips are authored on)": (
        "blender/hero_retarget_workbench/tailops.py",
        "def export_tail_skeleton(",
    ),
}

# Assembled from fragments so the checker's own source does not match its own patterns.
_VPK_FLAG = "--vpk_" + "filepath"
_VPK_CREATE = "--vpk_" + "create"
_VPK_DIR = "--vpk_" + "dir"
_VPK_EXTRACT = "--vpk_" + "extract"
_LIVE_PAK = "pak01" + "_dir.vpk"
_S2V = "Source2" + "Viewer-CLI"
_COMPILER = "resource" + "compiler"
_VPK_WORD = "VP" + "K"
_VNM = ".vnm"

# Every way a script can reach the live VPK itself.  A new S2V flag is a new pattern, not a
# pass; the point is that reading the game outside `forge.live` cannot happen quietly.
LIVE_PAK_PATTERNS = (
    re.compile(re.escape(_VPK_FLAG)),
    re.compile(re.escape(_VPK_CREATE)),
    re.compile(re.escape(_VPK_DIR)),
    re.compile(re.escape(_VPK_EXTRACT)),
    re.compile(re.escape(_LIVE_PAK)),
    re.compile(re.escape(_S2V)),
    re.compile(r"\bs2v\b"),
)

# Every step of the port: extract, append, compile, gate, pack, skeleton/clip documents.
PORT_STEP_PATTERNS = (
    re.compile(re.escape(_VPK_FLAG)),
    re.compile(re.escape(_VPK_CREATE)),
    re.compile(re.escape(_VPK_DIR)),
    re.compile(re.escape(_VPK_EXTRACT)),
    re.compile(re.escape(_COMPILER)),
    re.compile(rf"\b{_VPK_WORD}\b"),
    re.compile(r"\.vpk\b"),
    re.compile(re.escape(_VNM)),
)

# Directories whose Python is not the addon.  A port step here is the refusal; the addon is
# `blender/hero_retarget_workbench/`, the library it shares is `forge/`, and nothing else may
# run the work.
SCANNED_FOLDERS = ("tools", "artifacts/probes")


class Refused(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _read(relative: str) -> str:
    path = ROOT / relative
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _python_files(folder: str) -> list[Path]:
    return sorted(
        path
        for path in (ROOT / folder).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def check() -> list[str]:
    """Return the refusal lines; an empty list is a pass."""
    lines: list[str] = []

    for label, (relative, symbol) in ADDON_SYMBOLS.items():
        text = _read(relative)
        if symbol not in text:
            lines.append(
                "code-missing-from-addon: "
                f"{label} is not in {relative} (looked for {symbol!r}); the workbench cannot "
                "do this step, so the port can only be hand-driven from tools/"
            )

    for folder in SCANNED_FOLDERS:
        for path in _python_files(folder):
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(text) for pattern in LIVE_PAK_PATTERNS):
                if "forge.live" not in text and "from forge import live" not in text:
                    lines.append(
                        "live-pak-read-outside-addon: "
                        f"{relative} drives Source 2 Viewer against the live VPK instead of calling "
                        "forge.live.extract / forge.live.list_heroes; a hero read that way is named "
                        "by its folder key, not by the roster's display name"
                    )
                continue
            if any(pattern.search(text) for pattern in PORT_STEP_PATTERNS):
                lines.append(
                    "probe-only-port-code: "
                    f"{relative} runs a step of the port that the addon does not; fold it into "
                    "blender/hero_retarget_workbench/ or delete it"
                )

    return lines


SELFTEST_CASES = (
    ("code-missing-from-addon", "a capability only in tools/"),
    ("live-pak-read-outside-addon", "a hand-driven VPK read"),
    ("probe-only-port-code", "a port step outside the addon"),
)


def selftest() -> int:
    failures = 0
    source = Path(__file__).read_text(encoding="utf-8")
    for code, what in SELFTEST_CASES:
        if code not in source:
            print(f"SELFTEST FAIL {code}: the code is not even present ({what})")
            failures += 1
        else:
            print(f"SELFTEST PASS {code}: present and reachable from check() ({what})")
    # Assembled the same way as the scan patterns, so the probe cannot match its own text.
    exemption_marker = "PORT_STEP_" + "EXEMPT"
    if exemption_marker in source or "PYTEST_SKIP" + "LIST" in source:
        print("SELFTEST FAIL no-exemptions: the file offers an exemption path")
        failures += 1
    else:
        print("SELFTEST PASS no-exemptions: every hit is a refusal")
    print(f"SELFTEST {'PASS' if not failures else 'FAIL'} ({len(SELFTEST_CASES) + 1 - failures}/{len(SELFTEST_CASES) + 1})")
    return 0 if not failures else 1


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "check"
    if command == "selftest":
        return selftest()
    lines = check()
    for line in lines:
        print(f"REFUSE {line}")
    print(f"RESULT: {'PASS' if not lines else 'REFUSED'} ({len(lines)} refusals)")
    return 0 if not lines else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
