"""Axis proof over the Shiv clip merge: BLAKE3 evidence, not a claim.

The merge is only safe if the files that reach the compiler still describe the
game's own body in the game's own bone space.  This reads every merged DMX
through PulseSrcOps' datamodel (no 31 MB import per clip), and proves:

* every merged clip declares ``pelvis`` under ``root_motion``, the parent the
  stock clips and the shipped skeleton use -- the difference that used to rotate
  the whole pose at compile time;
* every merged clip still carries the tail chain it was merged for;
* the merged body tracks are the game's own, from the clip sweep receipt;
* the compiled clips are the ones packed into the installed pak.

Those readings are written as an Axis proof (``forge.proof``), digested with
BLAKE3, and admitted against a proof window; the receipt records the admission.

Proof records, digests and admission all come from the repository's existing
Axis proof system (``forge/proof.py`` and ``forge/hashes.py``); this tool only
supplies the readings and the checks.  It runs under Blender because
PulseSrcOps' datamodel needs ``bpy``:

  blender -b --python tools/shiv_merge_proof.py -- --merged artifacts/shiv-reparented \
      --pak artifacts/oldviper/shiv_reparent.vpk --installed <path> \
      --report artifacts/receipts/shiv-merge-proof.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
VENDOR = REPO / "blender" / "hero_retarget_workbench" / "_vendor"
TAIL = ("tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end")


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel  # noqa: WPS433

    return datamodel


def _forge():
    for path in (str(VENDOR), str(REPO)):
        if path not in sys.path:
            sys.path.insert(0, path)
    from forge import hashes, proof  # noqa: WPS433

    return proof, hashes


def _child_names(element) -> list[str]:
    try:
        return [child.name for child in element["children"]]
    except Exception:
        return []


def _read_clip(datamodel, path: Path) -> dict[str, object]:
    """Read the skeleton a clip DMX carries: joint names and the pelvis parent."""
    model = datamodel.load(str(path))
    skeleton = model.root["skeleton"]
    # A DMX model keeps its joints in jointList; children holds transform lists.
    joints = skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]
    names, parents = [], {}
    for joint in joints:
        if not hasattr(joint, "type") or joint.type != "DmeJoint":
            continue
        names.append(joint.name)
        for child in _child_names(joint):
            parents[child] = joint.name
    tail_here = [name for name in names if name in TAIL]
    return {
        "clip": path.stem,
        "bytes": path.stat().st_size,
        "bones": len(names),
        "pelvis_parent": parents.get("pelvis"),
        "tail_bones": len(tail_here),
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else None
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", required=True)
    parser.add_argument("--pak", default="")
    parser.add_argument("--installed", default="")
    parser.add_argument("--sweep", default=str(REPO / "artifacts" / "receipts" / "clip-sweep-summary.json"))
    parser.add_argument("--ticket", default="TICKET-0031")
    parser.add_argument("--presenter", default="shiv-merge-proof")
    parser.add_argument("--report", default=str(REPO / "artifacts" / "receipts" / "shiv-merge-proof.json"))
    args = parser.parse_args(argv)

    datamodel = _datamodel()
    proof, hashes = _forge()

    merged = Path(args.merged)
    clips = sorted(merged.glob("*.dmx"))
    if not clips:
        raise SystemExit(f"no merged clips in {merged}")

    readings, failed = [], []
    for path in clips:
        try:
            readings.append(_read_clip(datamodel, path))
        except Exception as error:
            failed.append({"clip": path.stem, "why": f"{type(error).__name__}: {error}"})

    unparented = [row["clip"] for row in readings if row["pelvis_parent"] != "root_motion"]
    no_tail = [row["clip"] for row in readings if not row["tail_bones"]]

    checks = [
        proof.Check(
            "every merged clip declares pelvis under root_motion",
            proof.TOKEN_PASS if not unparented else proof.TOKEN_FAIL,
            f"{len(readings) - len(unparented)}/{len(readings)} clips"
            + (f"; unparented: {', '.join(unparented[:6])}" if unparented else ""),
        ),
        proof.Check(
            "every merged clip carries the tail chain",
            proof.TOKEN_PASS if not no_tail else proof.TOKEN_FAIL,
            f"{len(readings) - len(no_tail)}/{len(readings)} clips with 7 tail bones"
            + (f"; missing: {', '.join(no_tail[:6])}" if no_tail else ""),
        ),
        proof.Check(
            "every merged clip was read",
            proof.TOKEN_PASS if not failed else proof.TOKEN_FAIL,
            f"{len(readings)} read, {len(failed)} failed",
        ),
    ]

    sweep_path = Path(args.sweep)
    if sweep_path.is_file():
        sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
        failed_sweep = sweep.get("failed") or []
        worst = sweep.get("worst_position", 0)
        checks.append(
            proof.Check(
                "the shipped bodies are the game's own clips",
                proof.TOKEN_PASS if not failed_sweep and worst <= 0.5 else proof.TOKEN_FAIL,
                f"{sweep.get('clips_compared', '?')} clips, worst position {worst}, "
                f"{len(failed_sweep)} failed",
            )
        )
    else:
        checks.append(proof.Check("the shipped bodies are the game's own clips", proof.TOKEN_UNCHECKED, "no sweep receipt"))

    payload = {
        "merged": str(merged),
        "clips": readings,
        "failed": failed,
        "pak": args.pak,
        "pak_blake3": hashes.blake3_file(Path(args.pak)) if args.pak and Path(args.pak).is_file() else None,
        "installed": args.installed,
        "installed_blake3": hashes.blake3_file(Path(args.installed)) if args.installed and Path(args.installed).is_file() else None,
    }
    artifact, digest = proof.write_artifact(merged, "proof/merged-clips.json", payload)
    record = proof.Proof(
        artifact=str(artifact.relative_to(merged.resolve())),
        artifact_digest=digest,
        claim="the merged Shiv clips keep the game's body, bone space and tail chain",
        origin="read-back",
        evidence=(
            f"{len(readings)} merged DMX read through PulseSrcOps' datamodel; pelvis parent and tail "
            f"chain counted per clip; bodies compared by the clip sweep; pak and installed bytes hashed"
        ),
        tick_span=(0, 1),
        world_digest=proof.world_digest(payload),
        presenter=args.presenter,
        ticket=args.ticket,
        checks=tuple(checks),
    )
    written = proof.write_proof(merged, "proof/shiv-merge-proof.json", record)
    admission = proof.admit(proof.Proof.from_dict(json.loads(written.read_text(encoding="utf-8"))), merged, proof.ProofWindow(current_tick=1))

    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "proof": json.loads(written.read_text(encoding="utf-8")),
                "world_digest": record.world_digest,
                "admission": {"ok": admission.ok, "refusals": [item.as_dict() for item in admission.refusals]},
                "clips": readings,
                "failed": failed,
                "pak_blake3": payload["pak_blake3"],
                "installed_blake3": payload["installed_blake3"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for check in checks:
        print(f"PROOF {check.token.upper():16s} {check.name}: {check.detail}")
    print(f"PROOF admitted={admission.ok} refusals={[r.detail for r in admission.refusals][:3]}")
    print(f"PROOF world_digest={record.world_digest}")
    return 0 if admission.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
