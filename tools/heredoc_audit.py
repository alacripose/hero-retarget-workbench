"""Refuse a heredoc written into a script this repository runs.

The family has the failure four times: a `python - <<'PY'` or `cat > f <<'EOF'` payload loses its
terminator to line endings, the shell takes the rest of the command with it, and the command that
"ran" wrote nothing. `tools/record_row.py` is the tool that replaced the record path; this is the
check that keeps the pattern out of the scripts that do the work.

It only flags a heredoc where a shell would parse one — a `.sh`/`.ps1`/`.cmd`/`.bat`/`.yml` line,
or a Python line that hands a command to a shell (`shell=True`). The same text inside a docstring
is inert, and this repository's own records quote the pattern on purpose.

usage:
  python tools/heredoc_audit.py
  python tools/heredoc_audit.py --selftest   # prove the refusal fires on a planted file
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"<<-?\s*['\"]?(?:PY|EOF|EOT|BASH|SH|PS1|CMD)\b")
SHELL_SUFFIXES = (".sh", ".ps1", ".cmd", ".bat", ".yml", ".yaml")
SKIP_DIRS = {".git", "logs", "artifacts", "__pycache__", "node_modules", ".pytest_cache", "backup"}
REFUSAL = "heredoc-invocation"


def scan(root: Path) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or set(path.parts) & SKIP_DIRS:
            continue
        suffix = path.suffix.lower()
        if suffix not in SHELL_SUFFIXES and suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if not PATTERN.search(line):
                continue
            if suffix == ".py" and "shell=True" not in line and '"-c"' not in line and "'-c'" not in line:
                continue
            rows.append({"path": str(path.relative_to(root)).replace("\\", "/"), "line": number,
                         "text": line.strip()[:120]})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heredoc_audit", description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true", help="prove the refusal fires on a planted file")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.selftest:
        with tempfile.TemporaryDirectory(prefix="heredoc-audit-") as temporary:
            planted = Path(temporary) / "probe.sh"
            planted.write_text("python - <<'PY'\nprint(1)\nPY\n", encoding="utf-8")
            found = scan(Path(temporary))
        print(f"selftest: planted file reported {len(found)} offender(s)")
        if len(found) != 1:
            print(f"REFUSED {REFUSAL}: the planted heredoc was not reported", file=sys.stderr)
            return 1
        print("RESULT: selftest pass")
        return 0

    rows = scan(root)
    if rows:
        for row in rows:
            print(f"{REFUSAL}: {row['path']}:{row['line']} {row['text']}", file=sys.stderr)
        print(f"RESULT: fail ({len(rows)} heredoc invocation(s))", file=sys.stderr)
        return 1
    print("RESULT: pass (no heredoc in a runnable script)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
