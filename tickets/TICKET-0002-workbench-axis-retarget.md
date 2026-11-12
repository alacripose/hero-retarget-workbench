# TICKET-0002 — Manual workbench and Axis retarget proof

**Status:** implemented; native visual acceptance pending owner
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-deadlock-workbench.jsonl`
**Opened:** 2026-11-12

## Requirement

The owner rejected a one-click button queue. The addon must make the work easier
without pretending to do the judgement: it needs a split 3D comparison, manual
bone mapping, renaming and alignment, and a weight solve that handles assets
larger than the hero body. The owner also named the family Axis civilian proof
system, not a percentage or a generic transfer claim, and required a modern
dependency rather than a legacy fallback.

The owner's corrections are recorded verbatim in the authority file. The
operative requirements are:

1. A split 3D viewport that shows the hero and the custom model for animation
   comparison.
2. Manual bone mapping, source-to-target renaming, rest alignment and pose
   nudging; unmatched bones are a decision the user can resolve, not an opaque
   error wall.
3. Weights that are not Blender's `DATA_TRANSFER` slop. Mapped custom weights
   are a prior; the hero surface is sampled when close; geometry outside the
   body uses mapped bone envelopes; extra appendage bones can be folded or kept.
4. Large/furry assets need explicit extra-bone policy, fallback bone, protected
   groups, maximum influences and manual weight-paint tools.
5. Long operations do not freeze the main Blender thread. S2V detection and
   extraction, CSDK13 compilation, and the weight solve run off the main thread
   or in timer-sized chunks.
6. A retarget has an Axis-shaped proof: artifact bytes, claim, origin, evidence,
   tick span, world digest, presenter, ticket and named checks. A proof alone is
   not a pass. A stale or unchecked proof blocks export.
7. Modern identity is BLAKE3. The addon carries the dependency and does not fall
   back to SHA-256. SHA-256 remains only as legacy stage evidence.

## Non-goals

- Parsing, reconstructing, rewriting, or generating the hero vmdl.
- A KV3 parser.
- Replacing the custom material slots as an export side effect.
- Automatically guessing a nearest bone for an unmatched weighted group.
- Making a passing test define the project or reducing the work to a slice.

## Acceptance criteria

1. `DMF_PT_skeleton` shows a filterable bone-map list; each row can be mapped,
   marked extra or ignored. Renaming checks the custom rig and matching vertex
   group before changing either, and refuses an occupied name by name.
2. `dmf.align_bone`, `dmf.align_all_bones`, `dmf.copy_pose` and `dmf.nudge_bone`
   operate on the custom rig and leave the hero rig unchanged.
3. `dmf.compare_split` creates two 3D areas and local views: hero body and hero
   rig on one side, custom mesh and the rig it is bound to on the other.
4. `WeightSolver` has `HYBRID`, `CUSTOM` and `ENVELOPE` methods. None creates a
   `DATA_TRANSFER` modifier. Extra policy is `FOLD`, `KEEP` or `DROP`; `KEEP`
   copies extra bones into the hero armature.
5. The solver runs in timer chunks, reports progress, can be cancelled between
   chunks, and does not block the main thread for the whole mesh.
6. `forge.proof` writes a BLAKE3 artifact and proof with the Axis fields. `admit`
   refuses a stale tick, changed bytes, missing presenter/ticket, or any check
   that is not `pass`.
7. `dmf.export_stage` calls the proof gate before export and refuses a stale,
   refused or missing proof with `axis-proof-refused`.
8. The addon zip carries `blake3` and a vendored extension; import works from the
   installed zip without the checkout.
9. `python -m unittest discover -s tests` passes; `python tools/project.py gate`
   passes; `tools/blender_workbench_probe.py` passes headlessly.
10. The split viewport is visually checked by the owner in native Blender. The
    agent does not claim that a headless object-set check is a visual witness.

## Evidence

- `artifacts/receipts/deadlock-model-forge-workbench.json` — pass; proof
  `current`; artifact digest
  `blake3:abac30e5219bcdb61af5d855a64571b76dc4d032ca45cb976f2ff1414d4eb988`;
  stale-byte tamper refused; export refused with `axis-proof-refused`.
- `artifacts/receipts/deadlock-model-forge-real-workbench.json` — real Haze body,
  `CUSTOM` solve; 33,366 vertices, 120 bones, 67 groups, 53,834 links, 4
  materials; proof `current` at
  `blake3:56ab5000287956d82687b0a0301f3402a2dcb580431b3a95fdaec6a26c5cfba8`;
  exported DMX re-import matched all seven comparisons; vmdl unchanged. This
  run used `--skip-compile`; the earlier real compile receipt remains separately
  recorded.
- `artifacts/receipts/deadlock-model-forge-lod-material-workbench.json` — pass;
  3 LODs at 36,429 / 24,286 / 12,142 polygons; custom `pbr.vfx` material kept on
  every LOD; vmdl unchanged; proof `current` at
  `blake3:d2bb9808ed071e4389f2c82fcdd31f3665f7e2f84b5724c7f7bd498863a78f81`.
- `artifacts/receipts/deadlock-model-forge-zip.json` — extracted-zip import
  pass; vendored `blake3` loaded from the zip; 6 panels, 24 workbench operators,
  34 operator classes total, 45 UI icons validated.
- `artifacts/receipts/compare-panel.png` — real-window agent probe: two 3D areas
  and both local views created; all five subpanels drew without a Python error.
  This closes the blank Compare panel caused by the invalid `SPLITSCREEN` icon;
  `SMOOTH` and `NORMALIZE` in Weights & Proof were invalid too and were replaced.
- `dist/deadlock_model_forge-0.2.2.zip` — 29 files, 268,057 bytes, SHA-256
  `646d9a30c5445db08fcdea3e83160a5cfa33c13b57d9da7d18abf68efa5b6a43`,
  BLAKE3 `a619381da1a715089a257d88e2c922143f5422ba3022e12e750cb2a0a41de276`.
- `artifacts/receipts/compile-temp-mirror.log` — real CSDK13 compile after the
  disposable-mirror change: 36 compiled files (1 `.vmdl_c`, 6 `.vmat_c`, 29
  `.vtex_c`); no `dmf_build_*` directory remained in CSDK `content` or `game`.
- Real Haze stage after the material inventory change: 84 material assets (70
  textures), 651 extraction files; notes and JSON were not staged.
- 53 unit tests pass; `python tools/project.py gate` passes all five checks;
  `python tools/project.py selftest` rejects the planted parser.
- `impeccable detect --json blender/deadlock_model_forge/ui.py` returned `[]`.
- `ledger/ledger.jsonl`, `STATUS.md`.

## Open

- A real custom furry/huge-asset fixture is not present in the environment. The
  headless probe uses a synthetic tail and an extra bone; the owner's real model
  is the next bind-pose check.
- Native Blender panel and split-viewport visual inspection of the installed
  build remain the owner's. The real-window agent probe saved a screenshot and
  proves the five panels draw and the split creates two local views; it is not
  the owner's witness.
- Timer-sized weight chunks were driven manually in headless Blender; a real
  event-loop session is still the owner's check.
- PulseSrcOps reports some decimated LOD vertices with more than four weight
  links (21/79/124 on the three Haze LODs). The base solve is capped at four;
  this warning is in the LOD decimation/export path, not the weight solve.
