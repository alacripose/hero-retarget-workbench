"""Compile merged Shiv clips in the accepted pak97 addon shape, against the live docs.

The accepted `item_run_center` build (pak97 v1) is a CSDK addon holding the
31 MB `shiv_tailbones.dmx` (md5 `ae3d181321cce008d3d5fa2293efe6d7`), the 06:47
`shiv.vnmskel`, and a clip document whose `m_sourceFilename` points at the merged
DMX.  The rejected bulk build differed in the skeleton the merge ran on
(`artifacts/golden/...` 93 KB, md5 `0c837723126ec8cc5c88ae383b94f912`), which is
why the body came back horizontal.

The documents come from the live game (`--extraction`, written by
`Source2Viewer-CLI -f models/heroes_staging/shiv/clips/ -d`), and every document
names its own animation DMX.  Many clips share one body animation and some point
outside the shiv folder (`models/heroes_staging/gen_man/...`), so the merged DMX
is written to the path the document names rather than to a folder this tool
invents, and the document itself is never edited.

  python tools/shiv_merge_compile.py --csdk <csdk root> --addon shiv_merge_live \
      --merged artifacts/live-shiv-merge/out \
      --shipped artifacts/shiv-168-full-baked3 \
      --extraction artifacts/live-shiv-stock \
      --sources artifacts/receipts/live-shiv-clip-sources.txt \
      --skeleton <31 MB shiv_tailbones.dmx> --vnmskel <06:47 shiv.vnmskel> \
      --report artifacts/receipts/shiv-merge-live-compile.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERO = Path("models/heroes_staging/shiv")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csdk", required=True)
    parser.add_argument("--addon", required=True)
    parser.add_argument("--merged", required=True)
    parser.add_argument("--shipped", required=True, help="extracted 06:47 base tree with the shipped *_c files")
    parser.add_argument("--extraction", required=True, help="live stock extraction with the clip documents")
    parser.add_argument("--sources", required=True, help="tab separated <clip>\\t<source dmx path>")
    parser.add_argument(
        "--inputs",
        default="",
        help="json map <staged name> -> <source dmx path> from the merge pass; lets clips that share one body reuse its merged DMX",
    )
    parser.add_argument(
        "--include-non-additive",
        action="store_true",
        help="compile the <clip>.vnmclip+non_additive documents too; resourcecompiler emits them from the base document",
    )
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--vnmskel", required=True)
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-merge-compile.json"))
    return parser.parse_args()


def _sources(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or "\t" not in line:
            continue
        name, source = line.split("\t", 1)
        rows[name.strip()] = source.strip()
    return rows


def main() -> int:
    args = _arguments()
    csdk = Path(args.csdk)
    compiler = csdk / "game" / "bin" / "win64" / "resourcecompiler.exe"
    gameinfo = csdk / "game" / "citadel" / "gameinfo.gi"
    for required in (compiler, gameinfo):
        if not required.is_file():
            raise SystemExit(f"missing: {required}")
    merged = Path(args.merged)
    extraction = Path(args.extraction)
    sources = _sources(Path(args.sources))
    owners: dict[str, str] = {}
    if args.inputs:
        for name, source in json.loads(Path(args.inputs).read_text(encoding="utf-8")).items():
            owners.setdefault(source, name)
    addon = args.addon.strip().strip("/\\")
    content = csdk / "content" / "citadel_addons" / addon
    clips = content / HERO / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    (content / HERO / "dmx" / "mesh").mkdir(parents=True, exist_ok=True)
    for source, target in (
        (Path(args.skeleton), content / HERO / "dmx" / "mesh" / "shiv_tailbones.dmx"),
        (Path(args.vnmskel), content / HERO / "shiv.vnmskel"),
    ):
        shutil.copyfile(source, target)

    doc_dir = extraction / HERO / "clips"
    docs = sorted({path.name[:-2] for path in (Path(args.shipped) / HERO / "clips").glob("*.vnmclip_c")})
    if not args.include_non_additive:
        docs = [doc for doc in docs if "+non_additive" not in doc]
    report: dict[str, object] = {
        "csdk": str(csdk),
        "addon": addon,
        "merged": str(merged),
        "clips": [],
        "failed": [],
        "skipped": [],
        "placed": {},
    }
    compiled_names: list[str] = []
    for doc in docs:
        name = doc[: -len(".vnmclip")]
        doc_source = doc_dir / doc
        source = sources.get(name)
        # Many documents name one shared body animation; the merge pass staged it
        # under the first document that uses it, so follow that name.
        owner = owners.get(source or "", name)
        merged_dmx = merged / f"{owner}.dmx"
        if not doc_source.is_file() or not merged_dmx.is_file() or not source:
            report["skipped"].append(
                {
                    "clip": name,
                    "why": f"doc={doc_source.is_file()} merged={merged_dmx.is_file()} source={bool(source)} owner={owner}",
                }
            )
            continue
        shutil.copyfile(doc_source, clips / doc)
        target = content / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(merged_dmx, target)
        report["placed"][name] = {"source": source, "merged_from": owner}
        compiled_names.append(doc)
    for doc in compiled_names:
        name = doc[: -len(".vnmclip")]
        relative = Path("citadel_addons") / addon / HERO / "clips" / doc
        result = subprocess.run(
            [str(compiler), "-nop4", "-f", "-game", str(gameinfo.parent), "-i", str(relative)],
            cwd=str(csdk / "content"),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=1800,
        )
        output = "".join(part for part in (result.stdout, result.stderr) if part)
        # resourcecompiler prints "OK: 1 compiled" for a clean run and
        # "WARNING: 1 compiled, 0 failed" when it only had event-range warnings;
        # the exit code stays 0 in both. Pass on the code and the failed count.
        clean = result.returncode == 0 and "0 failed" in output
        row = {"clip": name, "returncode": result.returncode, "clean": clean, "output": output.strip()[-600:]}
        report["clips"].append(row)
        if not clean:
            report["failed"].append(row)
            print(f"COMPILE-FAIL {name}: {output.strip()[-200:]}", flush=True)
        else:
            print(f"COMPILE {name}", flush=True)
    game_clips = csdk / "game" / "citadel_addons" / addon / HERO / "clips"
    compiled = sorted(path.name for path in game_clips.glob("*.vnmclip_c")) if game_clips.is_dir() else []
    report["compiled"] = compiled
    report["content_addon"] = str(content)
    report["game_addon"] = str(game_clips.parent)
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"COMPILE done {len(report['clips']) - len(report['failed'])}/{len(compiled_names)} compiled, "
        f"{len(report['skipped'])} skipped, {len(compiled)} _c files",
        flush=True,
    )
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
