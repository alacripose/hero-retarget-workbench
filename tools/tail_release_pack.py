"""Pack a hero port's compiled addon into a VPK, without shipping what the game has.

A port ships what it changes: the model, the shipped skeleton and the compiled
clips.  Materials that already exist in the game are not copied into the pak --
the client resolves them from `pak01`, and bundling them only makes the pak
bigger and can shadow a working game material with a half-compiled copy.

  python tools/tail_release_pack.py \
      --addon-game <csdk>/game/citadel_addons/<addon> \
      --out artifacts/<hero>-tail/<name>.vpk \
      --report artifacts/receipts/<hero>-tail-pack.json [--include-materials]

`tools_asset_info.bin`, DMX sources, `.vmat`/`.png` sources and thumbnails are
never packed.  `--include-materials` adds the compiled `*.vmat_c`/`*.vtex_c`
for the case where a port introduces a material the game does not have.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
S2V = Path("<home>/Downloads/cli-windows-x64/Source2Viewer-CLI.exe")
BLENDER = Path(
    "<home>/Downloads/blender-PR165087/"
    "blender-5.4.0-alpha+main-PR165087.ca9a25cceea7-windows.amd64-release/blender.exe"
)
GATE = REPO / "tools" / "tail_release_gate.py"
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))
from pak_materials import game_material_paths  # noqa: E402
MODEL_SUFFIXES = (".vmdl_c", ".vnmskel_c", ".vnmclip_c")
MATERIAL_SUFFIXES = (".vmat_c", ".vtex_c")
SOURCE_SUFFIXES = (".dmx", ".vnmclip", ".vnmskel", ".vmdl")
NEVER = ("tools_asset_info.bin",)


def _selected(root: Path, include_materials: bool) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        if name in NEVER or name.endswith((".vmat", ".png", ".jpg", ".tga")):
            continue
        # Sources are never shipped.  The 15:18 Haze pak carried every clip's DMX and
        # every decompiled .vnmclip text beside the compiled files (427 .dmx / 197
        # .vnmclip, ~30 MB of the 54 MB pak) and the client reads none of it: the
        # compiled *.vnmclip_c holds the sampled tracks (decompiled and checked:
        # tail_0..tail_end position and orientation tracks are in there).  The pinned
        # Shiv pak's own sources are a leftover of how it was built, not a requirement.
        if name.endswith((".dmx", ".vnmclip", ".vnmskel", ".vmdl")):
            continue
        if name.endswith(MODEL_SUFFIXES):
            files.append(path)
            continue
        if include_materials and name.endswith(MATERIAL_SUFFIXES):
            files.append(path)
    return files


def _sources_under(root: Path) -> list[Path]:
    return [
        path for path in sorted(root.rglob("*"))
        if path.is_file() and path.name.endswith((".dmx", ".vnmclip"))
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-game", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--include-materials", action="store_true")
    parser.add_argument("--skip-gate", action="store_true", help="diagnostics only; never for a release")
    parser.add_argument("--clips", default="", help="merged clip DMX the gate reads; needs a DmeModel per clip")
    parser.add_argument(
        "--game-skeleton",
        default="",
        help="the game's own skeleton DMX; the gate then requires every shared joint to keep its parent",
    )
    parser.add_argument(
        "--game-model",
        default="",
        help="the game's own mesh DMX; the gate then requires the shipped bind not to move",
    )
    parser.add_argument(
        "--proof",
        default="",
        help="where to write the BLAKE3 Axis proof binding the pak to the gated bytes (default artifacts/proofs/<pak>.proof.json)",
    )
    parser.add_argument(
        "--game-clips",
        default="",
        help="the hero's extracted clips folder (*.vnmclip); a shipped skeleton must carry this whole inventory",
    )
    parser.add_argument(
        "--skeleton-convention",
        choices=("shipped", "in-model"),
        default="shipped",
        help=(
            "which rule this pak follows: 'shipped' carries a compiled .vnmskel_c beside the model "
            "(the pinned Shiv pak), 'in-model' carries the tail joints inside the model's own "
            "skeleton and ships no .vnmskel_c (the addon's tail path). The two cannot both hold."
        ),
    )
    args = parser.parse_args()

    root = Path(args.addon_game)
    if not root.is_dir():
        raise SystemExit(f"addon game folder not found: {root}")
    out = Path(args.out)
    # Refuse before packing, not after a crash in game.  A pak whose skeleton cannot
    # render its model (missing tail joints, mask bones, divergent joint order) must
    # not exist: see tools/tail_release_gate.py for the three checks.
    # A release build must have been compared to the game's own skeleton. The pak
    # shipped on 2026-11-15 carried `pelvis` as a root, `weaponHand_L/R` under
    # `hand_L/hand_R` and a flat tail chain, and every one of those is only visible
    # against the game's document: refusing here is what makes the comparison
    # happen instead of being remembered.
    if not args.skip_gate and not args.game_skeleton:
        raise SystemExit(
            "refused gate-needs-game-skeleton: pass the game's own skeleton DMX "
            "(<hero>.vnmskel's m_sourceFilename, extracted from pak01); without it the "
            "gate cannot check parents, rests or the tail chain against what the client plays"
        )
    gate_report = REPO / "artifacts" / "receipts" / f"{out.stem}-gate.json"
    if not args.skip_gate:
        content = Path(str(root).replace("game/citadel_addons", "content/citadel_addons").replace("game\\citadel_addons", "content\\citadel_addons"))
        probe = subprocess.run(
            [str(BLENDER), "-b", "--python", str(GATE), "--", "--addon-content", str(content), "--report", str(gate_report)]
            + (["--clips", args.clips] if args.clips else [])
            + (["--game-skeleton", args.game_skeleton] if args.game_skeleton else [])
            + (["--game-model", args.game_model] if args.game_model else []),

            capture_output=True,
            text=True,
        )
        verdict = [line for line in (probe.stdout or "").splitlines() if line.startswith("GATE ")]
        print(verdict[-1] if verdict else f"GATE (no verdict) {probe.stdout[-400:]}{probe.stderr[-400:]}")
        if probe.returncode != 0:
            raise SystemExit(f"refused: the shipped skeleton cannot render this model; see {gate_report}")
    out = Path(args.out)
    sys.path.insert(0, str(REPO / "tools"))
    from work_record import finish, refuse_ephemeral_paths

    # The pak and its receipt are the deliverable: neither may live in a temp dir.
    refuse_ephemeral_paths([out, args.report])
    staging = REPO / "artifacts" / "pack-staging" / out.stem
    if staging.exists():
        shutil.rmtree(staging)
    # Refuse a tree whose compiled clips are not exactly the clips that were merged
    # and gated.  A stale `.vnmclip_c` left in the addon from an earlier run ships
    # the skeleton of that run: 228 compiled clips beside 197 merged ones is how a
    # pak reaches the game with clips authored against a rig nobody gated.
    if args.clips:
        merged = {path.stem for path in Path(args.clips).glob("*.dmx")}
        # The compiler generates a `<clip>.vnmclip+non_additive_c` beside the base
        # clip's own output; it has no merged document because it is derived, so
        # counting it as an orphan refused a correct build (31 of them, written by
        # the same compile run). Everything else must still be accounted for.
        compiled = {
            path.name[: -len(".vnmclip_c")]
            for path in root.rglob("*.vnmclip_c")
            if "+non_additive" not in path.name
        }
        extra = sorted(compiled - merged)
        absent = sorted(merged - compiled)
        if extra or absent:
            raise SystemExit(
                f"refused stale-compiled-clips: {len(extra)} compiled clips have no merged source "
                f"({extra[:4]}) and {len(absent)} merged clips were never compiled ({absent[:4]}); "
                "the pak would ship clips the gate never read",
            )

    files = _selected(root, args.include_materials)
    if not files:
        raise SystemExit(f"nothing to pack under {root}")
    excluded_sources = _sources_under(root)
    if excluded_sources:
        print(f"SOURCES-EXCLUDED {len(excluded_sources)} uncompiled .dmx/.vnmclip are not packed", flush=True)

    # Whether a skeleton ships is a measured decision, not a preference.  The structure the
    # owner accepted on 2026-11-15 01:19/01:26 (`haze_noskel.vpk`, sha256 b849c6bf…, visible
    # tail and cloth chain, no tail motion) ships NO skeleton: the client keeps the game's own
    # rig, which is why the body was coherent everywhere.  Bundling one is only allowed when
    # the gate proves it is slot- and frame-identical to the model (skeleton-slots-differ-
    # from-model / skeleton-rest-differs-from-model); it can never be assumed.
    # The pinned Shiv pak ships its skeleton (`shiv_tailbones.dmx` + `.vnmskel_c`), and the owner's
    # correction is explicit: "we can have the fucking vnmskeleton included literally look at the shiv
    # vpk in its slot".  So a release ships one.  What is not allowed is a skeleton whose slots or
    # frames disagree with the model — the gate refuses that as `skeleton-slots-differ-from-model`
    # and `skeleton-rest-differs-from-model`, which is how the 15:18/15:36 builds became impossible.
    skeleton_shipped = any(path.name.endswith(".vnmskel_c") for path in files)
    # Two shipped conventions exist and they are mutually exclusive.  The pinned Shiv pak carries a
    # compiled `.vnmskel_c` beside its model; the addon's tail path appends the tail joints to the
    # model's own skeleton and ships none.  A pak that does both ships two competing rigs, and one
    # that states neither is the ambiguity the Haze and Shiv builds were stuck in, so the convention
    # is declared on the command line and checked against what is actually in the tree.
    if args.skeleton_convention == "in-model" and skeleton_shipped:
        raise SystemExit(
            "refused skeleton-convention-conflict: --skeleton-convention in-model means the tail "
            "joints live in the model's own skeleton, but a compiled *.vnmskel_c is in this addon; "
            "the pak would ship two competing rigs for the same model"
        )
    if args.skeleton_convention == "shipped" and not skeleton_shipped:
        raise SystemExit(
            "refused skeleton-not-shipped: the addon has no compiled *.vnmskel_c and the declared "
            "convention is 'shipped'. The pinned Shiv pak ships its skeleton and so does a Haze "
            "release; without one the client animates the model with the game's own rig and the tail "
            "never moves. If the tail joints are inside the model's own skeleton, declare "
            "--skeleton-convention in-model instead of packing a pak with no stated rig."
        )
    print(f"SKELETON {args.skeleton_convention}", flush=True)

    # A pak that ships a skeleton replaces the rig the client animates this model with, so every
    # clip the client can play has to be present or the model is bound to a rig whose clips are
    # missing -- the 2026-11-15 refuted builds.  Picking a subset by hand is exactly how a pak
    # ships a model and skeleton with one clip and goes invisible: the refusal is that a shipped
    # skeleton requires the *whole* clip inventory, not that a subset looks plausible.
    if args.game_clips:
        inventory = {
            path.stem
            for path in Path(args.game_clips).rglob("*.vnmclip")
            if not path.stem.endswith("+non_additive")
        }
        shipped = {
            path.name[: -len(".vnmclip_c")]
            for path in files
            if path.name.endswith(".vnmclip_c") and "+non_additive" not in path.name
        }
        if not inventory:
            raise SystemExit(
                f"refused clip-inventory-empty: {args.game_clips} holds no *.vnmclip documents, so "
                "the pak cannot be checked against what the game plays"
            )
        missing = sorted(inventory - shipped)
        if missing:
            raise SystemExit(
                f"refused clip-inventory-partial: a skeleton ships, so the pak must carry the game's "
                f"whole clip inventory, but {len(missing)} of {len(inventory)} are absent "
                f"({missing[:4]}). The client binds the model to this skeleton and plays the game's "
                "own missing clips against it, which is how a port goes invisible after a frame. "
                "Ship every clip or ship no skeleton."
            )
        print(f"CLIP-INVENTORY complete {len(inventory)} of {len(inventory)}", flush=True)
    else:
        raise SystemExit(
            "refused clip-inventory-missing: pass --game-clips <the hero's extracted clips folder>; "
            "a pak that ships a skeleton without proving it carries the game's whole clip inventory "
            "is a hand-picked clip set, and that is the failure this refusal exists for"
        )

    # Materials the game already provides are never shipped: they shadow pak01
    # with a half-compiled copy and cost a port its surfaces.
    shipped_materials = [path for path in files if path.name.endswith(MATERIAL_SUFFIXES)]
    if shipped_materials:
        provided = game_material_paths()
        shadowed = [
            path for path in shipped_materials
            if path.relative_to(root).as_posix().lower() in provided
        ]
        if shadowed:
            raise SystemExit(
                f"refused materials-shadow-game: {len(shadowed)} compiled materials in this addon "
                f"already exist in pak01 ({[path.name for path in shadowed[:4]]})"
            )
    for path in files:
        destination = staging / path.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    proc = subprocess.run(
        [str(S2V), "-i", str(staging), "--vpk_create", str(out.resolve()), "-q"],
        capture_output=True,
        text=True,
    )
    if not out.is_file():
        raise SystemExit(f"vpk_create failed: {(proc.stdout or proc.stderr or '')[-600:]}")
    packed = sorted(path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file())
    receipt = {
        "addon_game": str(root),
        "out": str(out),
        "bytes": out.stat().st_size,
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "file_count": len(packed),
        "include_materials": args.include_materials,
        "skeleton_convention": args.skeleton_convention,
        "kinds": {
            "models": sum(name.endswith(".vmdl_c") for name in packed),
            "skeletons": sum(name.endswith(".vnmskel_c") for name in packed),
            "clips": sum(name.endswith(".vnmclip_c") for name in packed),
            "materials": sum(name.endswith(MATERIAL_SUFFIXES) for name in packed),
        },
        "files": packed[:12],
    }
    # Sign what was packed, with the family's BLAKE3 Axis proof instead of a receipt
    # line. The proof binds the pak bytes to the skeleton, the model, the whole
    # compiled-clip manifest and the gate's verdict: a pak recompiled after the gate
    # ran, or one clip swapped in, cannot present a passing proof for those bytes.
    proof_path = Path(args.proof) if args.proof else REPO / "artifacts" / "proofs" / f"{out.stem}.proof.json"
    sign = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools" / "tail_proof.py"),
            "--addon-game", str(root),
            "--pak", str(out.resolve()),
            "--game-skeleton", str(Path(args.game_skeleton).resolve() if args.game_skeleton else Path("missing")),
            "--gate", str(gate_report),
            "--proof", str(proof_path),
        ],
        capture_output=True,
        text=True,
    )
    verdict_lines = [line for line in (sign.stdout or "").splitlines() if line.startswith("PROOF ")]
    print(verdict_lines[-1] if verdict_lines else f"PROOF (no verdict) {(sign.stdout or '')[-300:]}{(sign.stderr or '')[-300:]}")
    receipt["proof"] = str(proof_path)
    if sign.returncode != 0 and not args.skip_gate:
        raise SystemExit(f"refused proof-not-verified: the pak cannot be signed against the gated bytes; see {proof_path}")
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        f"PACK {out.name} {receipt['bytes']}b files={receipt['file_count']} "
        f"models={receipt['kinds']['models']} skeletons={receipt['kinds']['skeletons']} "
        f"clips={receipt['kinds']['clips']} materials={receipt['kinds']['materials']} "
        f"sha256={receipt['sha256'][:16]}"
    )
    finish(
        "tail_release_pack",
        [out, args.report],
        f"PACK {out.name} bytes={receipt['bytes']} files={receipt['file_count']} sha256={receipt['sha256'][:16]}",
        "pass",
        {"clips": args.clips, "include_materials": args.include_materials},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
