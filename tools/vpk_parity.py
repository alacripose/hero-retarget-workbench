"""Verify a hero pak reaches the pinned Shiv pak, one measured dimension at a time.

**Owner instruction, verbatim:** *"The work isn't done until we can verify that the
haze vpk reaches the shiv vpk"*.

"Reaches" is not a feeling and not a file-size comparison.  The pinned Shiv pak is
the only pak this project has in a slot with a visible, animated tail, a coherent
body and a skeleton the client accepted, so it defines the target: what a release
ships, at what counts, under which exclusions.  This tool reads both paks' own
entry lists (Source 2 Viewer `--vpk_list`, no reimplementation of the format) and
refuses with a named code for every dimension where the candidate falls short.

The reference is data, from `ledger/pins/shiv.json`: the same pin the project gate
already runs, so a re-pin cannot leave this comparison pointing at an old file.

    python tools/vpk_parity.py --candidate artifacts/haze-tail/haze_tail_signed.vpk \
        --clips <csdk>/content/citadel_addons/haze_tail/models/heroes_staging/haze/clips \
        --report artifacts/receipts/haze-parity.json

What parity means here, and what it deliberately does not:

* **The skeleton ships** (`skeleton-not-shipped`).  The pinned Shiv pak carries
  `shiv.vnmskel_c`; the owner's correction is explicit — *"we can have the fucking
  vnmskeleton included literally look at the shiv vpk in its slot"*.
* **Every clip document is compiled** (`clip-document-uncompiled`) and the set is
  not thinner than the reference's (`clip-count-below-reference`).  A pak that
  animates one clip is not a port.
* **The model ships** (`model-not-shipped`).
* **Sources are not shipped** (`sources-shipped`).  The pinned *release* pak carries
  zero `.dmx` and zero `.vnmclip` texts, which settles the 2026-11-15 note that
  read its sources as a requirement: they were a leftover of how the older builds
  were packed.  They are compiled data or they are not shipped.
* **Materials the game already has are not shipped** (`materials-shadow-game`), the
  owner's rule — *"for everything that uses an in game material the vpk doesn't
  need to include them that's wasteful as fuck"*.  The reference is exempt because
  its material set is a leftover of the same older builds; parity is about what
  makes the pak work, not about copying what it wasted.
* **The gate admitted this exact tree** (`gate-not-admitted`) and **the BLAKE3 proof
  verifies over these bytes** (`proof-not-verified`).  Those two are the functional
  half: inventory parity alone says nothing about whether the skeleton can render
  the model, and the proof is what binds the pak on disk to the bytes that were
  gated.

A dimension with no input is reported as `unchecked`, never as a pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

S2V = Path("<home>/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
SHIV_PIN = REPO / "ledger" / "pins" / "shiv.json"
DEFAULT_REFERENCE = REPO / "artifacts" / "oldviper" / "shiv_tail_all.vpk"
DEFAULT_REPORT = REPO / "artifacts" / "receipts" / "vpk-parity.json"

MODEL = ".vmdl_c"
SKELETON = ".vnmskel_c"
CLIP = ".vnmclip_c"
NON_ADDITIVE = "non_additive"
MATERIAL = (".vmat_c", ".vtex_c")
SOURCE = (".dmx", ".vnmclip", ".vnmskel", ".vmdl")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entries(pak: Path) -> list[str]:
    """The pak's own entry list, straight from the format's only reader we ship."""
    if not pak.is_file():
        raise SystemExit(f"pak not found: {pak}")
    proc = subprocess.run(
        [str(S2V), "-i", str(pak), "--vpk_list"],
        capture_output=True,
        text=True,
    )
    paths = []
    for line in (proc.stdout or "").splitlines():
        line = line.replace("\r", "").strip()
        if not line:
            continue
        marker = line.rfind(" CRC:")
        paths.append((line[:marker] if marker > 0 else line).strip())
    if not paths:
        raise SystemExit(f"no entries read from {pak}: {(proc.stdout or proc.stderr or '')[-300:]}")
    return paths


def inventory(paths: list[str]) -> dict:
    def is_source(name: str) -> bool:
        # A compiled clip is `x.vnmclip_c`, its source is `x.vnmclip`.
        return name.endswith(SOURCE) and not name.endswith(CLIP)

    clips = [p for p in paths if p.endswith(CLIP)]
    base = [p for p in clips if NON_ADDITIVE not in p]
    return {
        "entries": len(paths),
        "models": sum(p.endswith(MODEL) for p in paths),
        "skeletons": sum(p.endswith(SKELETON) for p in paths),
        "clips": len(clips),
        "clip_documents": len(base),
        "clip_non_additive": len(clips) - len(base),
        "materials": sum(p.endswith(MATERIAL) for p in paths),
        "sources": sum(is_source(p) for p in paths),
        "clip_paths": base,
        "skeleton_paths": [p for p in paths if p.endswith(SKELETON)],
        "model_paths": [p for p in paths if p.endswith(MODEL)],
        "material_paths": [p for p in paths if p.endswith(MATERIAL)],
        "source_paths": [p for p in paths if is_source(p)],
    }


def pin_sha() -> tuple[str, str]:
    if not SHIV_PIN.is_file():
        raise SystemExit(f"refused reference-not-pinned: {SHIV_PIN} is missing")
    pin = json.loads(SHIV_PIN.read_text(encoding="utf-8"))
    pak = REPO / pin["pak"] if not Path(pin["pak"]).is_absolute() else Path(pin["pak"])
    return str(pak), str(pin.get("sha256") or "")


def clip_documents(folder: Path) -> list[str]:
    return sorted(path.stem for path in folder.glob("*.vnmclip") if path.is_file())


def verify_proof(pak: Path) -> tuple[bool | None, str]:
    """Admit the BLAKE3 proof written for this pak, if one exists."""
    candidates = [
        REPO / "artifacts" / "proofs" / f"{pak.stem}.proof.json",
        REPO / "artifacts" / "proofs" / f"{pak.name}.proof.json",
    ]
    proof_path = next((path for path in candidates if path.is_file()), None)
    if proof_path is None:
        return None, "no proof for this pak"
    try:
        from forge.proof import ProofWindow, admit, read_proof
    except Exception as error:  # pragma: no cover - import guard for headless use
        return None, f"forge.proof unavailable: {error}"
    try:
        relative = proof_path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return None, f"proof outside the repository: {proof_path}"
    admission = admit(read_proof(REPO / relative), REPO, ProofWindow(current_tick=0, max_age_ticks=0))
    detail = relative if admission.ok else f"{relative}: {'; '.join(admission.reasons())[:300]}"
    return bool(admission.ok), detail


def game_materials() -> set[str]:
    try:
        from pak_materials import game_material_paths

        return {path.lower() for path in game_material_paths()}
    except Exception:
        return set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, help="the pak to verify")
    parser.add_argument("--reference", default="", help="override the pinned Shiv pak")
    parser.add_argument(
        "--clips",
        default="",
        help="the addon's clip document folder (*.vnmclip); without it coverage is unchecked",
    )
    parser.add_argument(
        "--joint-sets",
        default="",
        help="a tools/dmx_joint_sets.py receipt of <mesh>=<model document> pairs; "
        "without it the mesh-to-skeleton binding is unchecked",
    )
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--allow-unchecked",
        action="store_true",
        help="diagnostics only: record UNCHECKED dimensions instead of refusing (never a release)",
    )
    args = parser.parse_args(argv)

    candidate = Path(args.candidate)
    if not candidate.is_absolute():
        candidate = REPO / candidate
    reference = Path(args.reference) if args.reference else None
    pinned_sha = ""
    if reference is None:
        reference_path, pinned_sha = pin_sha()
        reference = Path(reference_path)

    checks: list[dict] = []

    def check(code: str, state: str, detail: str = "") -> None:
        checks.append({"code": code, "state": state, "detail": detail})

    if not reference.is_file():
        check("reference-missing", "refuse", str(reference))
    else:
        actual = sha256(reference)
        if pinned_sha:
            check(
                "reference-pinned",
                "pass" if actual == pinned_sha else "refuse",
                f"{actual[:16]} vs pin {pinned_sha[:16]}",
            )
        else:
            check("reference-pinned", "unchecked", "no sha256 in ledger/pins/shiv.json")

    if not candidate.is_file():
        check("candidate-missing", "refuse", str(candidate))
        report = {"summary": "refused", "candidate": str(candidate), "checks": checks}
        print(json.dumps(report, indent=2))
        return 2

    ref = inventory(entries(reference))
    cand = inventory(entries(candidate))

    # ---- structure ------------------------------------------------------------
    check(
        "model-not-shipped",
        "pass" if cand["models"] >= 1 else "refuse",
        f"{cand['models']} .vmdl_c (reference {ref['models']})",
    )
    check(
        "skeleton-not-shipped",
        "pass" if cand["skeletons"] >= 1 else "refuse",
        f"{cand['skeletons']} .vnmskel_c (reference {ref['skeletons']})",
    )
    check(
        "clip-count-below-reference",
        "pass" if cand["clip_documents"] >= ref["clip_documents"] else "refuse",
        f"{cand['clip_documents']} documents (reference {ref['clip_documents']})",
    )

    # ---- the pak does not carry what the game already has or what is compiled ---
    check(
        "sources-shipped",
        "pass" if cand["sources"] == 0 else "refuse",
        f"{cand['sources']} uncompiled .dmx/.vnmclip/.vnmskel/.vmdl "
        f"(reference release ships {ref['sources']})",
    )
    provided = game_materials()
    shadowed = sorted(
        path for path in cand["material_paths"] if path.lower() in provided
    )
    if not provided:
        check("materials-shadow-game", "unchecked", "pak01 material inventory unavailable")
    else:
        check(
            "materials-shadow-game",
            "pass" if not shadowed else "refuse",
            f"{len(shadowed)} of {cand['materials']} materials already in pak01"
            + (f": {shadowed[:3]}" if shadowed else ""),
        )

    # ---- clip coverage, against the documents this addon actually compiles -----
    if args.clips:
        folder = Path(args.clips)
        documents = clip_documents(folder) if folder.is_dir() else []
        if not documents:
            check("clip-document-uncompiled", "unchecked", f"no *.vnmclip under {folder}")
        else:
            shipped = {path.rsplit("/", 1)[-1][: -len(CLIP)] for path in cand["clip_paths"]}
            missing = [name for name in documents if name not in shipped]
            check(
                "clip-document-uncompiled",
                "pass" if not missing else "refuse",
                f"{len(documents) - len(missing)}/{len(documents)} documents compiled"
                + (f"; missing {missing[:4]}" if missing else ""),
            )
    else:
        check("clip-document-uncompiled", "unchecked", "no --clips folder given")

    # ---- the functional half of parity ----------------------------------------
    gate = REPO / "artifacts" / "receipts" / f"{candidate.stem}-gate.json"
    if gate.is_file():
        receipt = json.loads(gate.read_text(encoding="utf-8"))
        admitted = bool(receipt.get("admitted"))
        joints = f"model {receipt.get('model_joints')} / skeleton {receipt.get('skeleton_joints')}"
        check("gate-not-admitted", "pass" if admitted else "refuse", f"{gate.name}: admitted={admitted}, {joints}")
    else:
        check("gate-not-admitted", "unchecked", f"no {gate.name}")

    # ---- the meshes bind by index into the document the skeleton comes from ---
    # The count in the gate receipt is NOT this comparison.  `model_joints` there is
    # the union of every render mesh *plus* the object-like entries `_joint_table`
    # walks (the armature object the extraction writes), while `skeleton_joints` is
    # the bone tree alone; on this tree that is 144 against 131 and nothing is wrong,
    # because every mesh (120 or 129 joints) is a **subsequence** of the 131-joint
    # document.  Comparing those two numbers refuses a correct build — the same
    # one-reading bug this project already recorded twice.  What actually matters is
    # that each mesh names only joints the document declares (no extra) and names
    # them in its order (no move), which is what the joint-sets receipt measures.
    if args.joint_sets:
        receipt_path = Path(args.joint_sets)
        if not receipt_path.is_file():
            check("mesh-joint-not-in-skeleton", "unchecked", f"no {receipt_path.name}")
        else:
            rows = json.loads(receipt_path.read_text(encoding="utf-8"))
            rows = rows if isinstance(rows, list) else [rows]
            extra = {
                Path(row["clip"]).name: row["extra_in_clip"]
                for row in rows
                if row.get("extra_in_clip")
            }
            moved = [
                Path(row["clip"]).name
                for row in rows
                if row.get("order_subsequence") is False
            ]
            check(
                "mesh-joint-not-in-skeleton",
                "pass" if not extra else "refuse",
                f"{len(rows)} meshes read; "
                + (", ".join(f"{name} adds {bones[:3]}" for name, bones in list(extra.items())[:3]) if extra else "no mesh declares a joint the document lacks"),
            )
            check(
                "mesh-joint-order-differs",
                "pass" if not moved else "refuse",
                f"{len(moved)} meshes out of order" + (f": {moved[:3]}" if moved else ""),
            )
    else:
        check("mesh-joint-not-in-skeleton", "unchecked", "no --joint-sets receipt")

    proof_ok, proof_detail = verify_proof(candidate)
    if proof_ok is None:
        check("proof-not-verified", "unchecked", proof_detail)
    else:
        check("proof-not-verified", "pass" if proof_ok else "refuse", proof_detail)

    refused = [row for row in checks if row["state"] == "refuse"]
    unchecked = [row for row in checks if row["state"] == "unchecked"]
    report = {
        "summary": "reaches the reference" if not refused else "does not reach the reference",
        "candidate": {
            "pak": str(candidate),
            "sha256": sha256(candidate),
            "bytes": candidate.stat().st_size,
            **{key: value for key, value in cand.items() if not key.endswith("_paths")},
        },
        "reference": {
            "pak": str(reference),
            "sha256": sha256(reference) if reference.is_file() else "",
            "bytes": reference.stat().st_size if reference.is_file() else 0,
            **{key: value for key, value in ref.items() if not key.endswith("_paths")},
        },
        "checks": checks,
        "refused": [row["code"] for row in refused],
        "unchecked": [row["code"] for row in unchecked],
    }
    destination = Path(args.report) if args.report else DEFAULT_REPORT
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"PARITY {report['summary'].upper()} {candidate.name}")
    print(
        f"  candidate: {cand['entries']} entries, {cand['models']} model, "
        f"{cand['skeletons']} skeleton, {cand['clips']} clips "
        f"({cand['clip_documents']} documents + {cand['clip_non_additive']} non_additive), "
        f"{cand['materials']} materials, {cand['sources']} sources"
    )
    print(
        f"  reference: {ref['entries']} entries, {ref['models']} model, "
        f"{ref['skeletons']} skeleton, {ref['clips']} clips "
        f"({ref['clip_documents']} documents + {ref['clip_non_additive']} non_additive), "
        f"{ref['materials']} materials, {ref['sources']} sources"
    )
    for row in checks:
        label = {"pass": "PASS", "refuse": "REFUSE", "unchecked": "UNCHECKED"}[row["state"]]
        print(f"  {label:9s} {row['code']}: {row['detail']}")
    print(f"  report: {destination}")
    # An unchecked dimension is not a pass.  `mesh-joint-not-in-skeleton` used to print
    # UNCHECKED when no --joint-sets receipt was passed and the tool still exited 0, so a pak
    # whose meshes might bind a joint the document lacks could be called "parity" and shipped.
    unchecked = [row for row in checks if row["state"] == "unchecked"]
    if unchecked and not getattr(args, "allow_unchecked", False):
        print(
            f"RESULT: REFUSED ({len(unchecked)} unchecked): "
            + ", ".join(row["code"] for row in unchecked)
            + " -- a dimension nobody measured is not a dimension that passed. "
            "Pass the missing input, or --allow-unchecked to record a diagnostic run."
        )
        return 2
    print(f"RESULT: {'PRESENT' if not refused else 'REFUSED'} ({len(checks) - len(unchecked)}/{len(checks)} measured)")
    return 0 if not refused else 2


if __name__ == "__main__":
    raise SystemExit(main())
