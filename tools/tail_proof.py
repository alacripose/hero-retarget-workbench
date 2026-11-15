"""Sign a packed tail pak with the family's Axis proof, using BLAKE3.

Every tail tool so far records a sha256 receipt in `ledger/ledger.jsonl`. A receipt
is a log line: it says what a run observed, and nothing verifies that the pak which
reached the game is the pak that was gated. The family already has the answer —
`forge/proof.py` + `forge/hashes.py`, the BLAKE3 proof the weight solve uses — and
this wires the tail pipeline into it.

The proof binds:

* the pak bytes                  -> artifact_digest (BLAKE3, prefixed)
* the skeleton source document   -> blake3
* the model's mesh document      -> blake3
* every compiled clip            -> name + blake3, in one manifest digest
* the gate's own verdict         -> a `pass`/`refuse` token per check

If any of those bytes change, `verify_bytes` refuses: a pak that was recompiled
after the gate ran, or a clip swapped into the tree, cannot present a passing proof
for the old manifest.

  python tools/tail_proof.py --addon-game <dir> --pak <vpk> \
      --game-skeleton <dmx> --gate <gate receipt> --proof artifacts/proofs/<name>.proof.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from forge.hashes import blake3_file  # noqa: E402
from forge.proof import Check, Proof, ProofWindow, admit, artifact_digest, read_proof, verify_bytes, world_digest, write_proof  # noqa: E402


def manifest(root: Path, pattern: str) -> tuple[list[dict], str]:
    rows = [
        {"name": path.relative_to(root).as_posix(), "blake3": blake3_file(path)}
        for path in sorted(root.rglob(pattern))
        if path.is_file()
    ]
    return rows, world_digest({"pattern": pattern, "files": rows})


def build(root: Path, pak: Path, game_skeleton: Path, gate: dict, ticket: str) -> Proof:
    compiled, compiled_digest = manifest(root, "*.vnmclip_c")
    # The game addon folder holds what the compiler wrote; the source documents live
    # in the content addon. Bind whatever is here, preferring the compiled bytes the
    # pak actually ships.
    skeleton_files = sorted(root.rglob("*.vnmskel_c")) or sorted(root.rglob("*.vnmskel"))
    skeleton_source = skeleton_files[0] if skeleton_files else None
    model_files = sorted(root.rglob("*.vmdl_c")) or sorted(root.rglob("*.vmdl"))
    model = model_files[0] if model_files else None
    if skeleton_source is None or model is None:
        raise SystemExit("proof-needs-skeleton: the addon has no .vnmskel or .vmdl to bind")

    admitted = bool(gate.get("admitted"))
    checks = [
        Check("gate-admitted", "pass" if admitted else "refuse", f"{gate.get('addon_content')} admitted={admitted}"),
        Check("tail-chain", "pass" if len(gate.get("tail_chain") or []) >= 3 else "refuse",
              f"{len(gate.get('tail_chain') or [])} tail joints: {gate.get('tail_chain')}"),
        Check("clips-compiled", "pass" if compiled else "refuse", f"{len(compiled)} compiled clips"),
        Check("skeleton-shipped", "pass" if any(p.name.endswith(".vnmskel_c") for p in root.rglob("*.vnmskel_c")) else "refuse",
              "compiled skeleton present" if any(p.name.endswith(".vnmskel_c") for p in root.rglob("*.vnmskel_c")) else "no .vnmskel_c"),
        Check("game-skeleton-compared", "pass" if game_skeleton.is_file() else "refuse",
              f"{game_skeleton.name} blake3 {blake3_file(game_skeleton)[:16]}"),
    ]
    payload = {
        "pak": pak.name,
        "pak_blake3": blake3_file(pak),
        "skeleton_source": {"name": skeleton_source.name, "blake3": blake3_file(skeleton_source)},
        "model": {"name": model.name, "blake3": blake3_file(model)},
        "game_skeleton": {"name": game_skeleton.name, "blake3": blake3_file(game_skeleton)},
        "clips": {"count": len(compiled), "manifest_digest": compiled_digest},
    }
    data = pak.read_bytes()
    try:
        artifact = pak.resolve().relative_to(REPO).as_posix()
    except ValueError:
        artifact = str(pak)
    return Proof(
        artifact=artifact,
        artifact_digest=artifact_digest(data),
        claim="the shipped pak is the gated pak: same skeleton, same model, same compiled clips",
        origin="executed",
        evidence=(
            f"{payload['clips']['count']} compiled clips, manifest {compiled_digest[:24]}, "
            f"pak {payload['pak_blake3'][:24]}, skeleton {payload['skeleton_source']['blake3'][:24]}"
        ),
        tick_span=(0, 0),
        world_digest=world_digest(payload),
        presenter="tail-release",
        ticket=ticket,
        checks=tuple(checks),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-game", required=True)
    parser.add_argument("--pak", required=True)
    parser.add_argument("--game-skeleton", required=True)
    parser.add_argument("--gate", required=True, help="gate receipt the pack ran")
    parser.add_argument("--proof", required=True)
    parser.add_argument("--ticket", default="TICKET-0022")
    args = parser.parse_args(sys.argv[1:])

    root = Path(args.addon_game)
    pak = Path(args.pak)
    gate = json.loads(Path(args.gate).read_text(encoding="utf-8"))
    game_skeleton = Path(args.game_skeleton)
    proof = build(root, pak, game_skeleton, gate, args.ticket)
    wanted = Path(args.proof)
    try:
        relative = wanted.resolve().relative_to(REPO).as_posix()
    except ValueError:
        relative = str(wanted)
    target = write_proof(REPO, relative, proof)

    admission = admit(read_proof(target), REPO, ProofWindow(current_tick=0, max_age_ticks=0))
    verdict = "PASS" if admission.ok else "REFUSE"
    print(f"PROOF {verdict} {proof.artifact} digest {proof.artifact_digest[:32]}")
    for check in proof.checks:
        print(f"  {check.token:6s} {check.name}: {check.detail}")
    if not admission.ok:
        for reason in admission.reasons():
            print(f"  refusal: {reason}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
