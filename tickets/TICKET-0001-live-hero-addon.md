# TICKET-0001 — Live-hero model porting addon

**Status:** active  
**Owner:** ala  
**Authority:** `logs/authority/2026-11-12-deadlock-model-forge.jsonl`  
**Opened:** 2026-11-12

## Problem

Porting a custom Deadlock model currently requires manually reconciling a live
hero's skeleton, its extracted vmdl, materials, and the CSDK13 compiler. A
custom model needs to be fitted and skinned to the live hero skeleton without
touching the hero vmdl that S2V already produced.

## Scope

- Blender 5.4 sidebar addon with a hero picker and a custom-model picker.
- Live game detection and S2V hero inventory/extraction.
- Hero body DMX import through PulseSrcOps.
- Custom model import (glTF, GLB, FBX, OBJ, DMX).
- Axis fit and optional height scale; weights untouched by the axis transform.
- Conservative name mapping or hero-body weight transfer.
- Live hero material-slot assignment; copied `.vmat` files remain verbatim.
- Source 2 DMX export.
- Compiler handoff containing the unchanged S2V vmdl, the replacement DMX,
  copied materials, and a hash manifest.
- CSDK13 `resourcecompiler` invocation and log.

## Non-goals

- Parsing, reconstructing, rewriting, or generating the hero vmdl.
- A KV3 parser or any model metadata reconstruction.
- Using CSDK13's hero files as source data.
- A web UI or a custom model interchange format.
- Rebuilding `.vmat` contents instead of copying them.

## Acceptance criteria

1. `python tools/project.py doctor` finds the live game, S2V, Blender, and
   CSDK13 on the observed machine; build 6861 is read from `steam.inf`.
2. `python tools/project.py heroes` lists the live heroes from S2V.
3. The Blender addon registers and unregisters cleanly in Blender 5.4.
4. A real live Haze body DMX imports with a skeleton and a skinned mesh.
5. Fit applies the selected exact axis transform; weights are not transformed.
6. Retarget produces a hero armature modifier, maps or transfers weights, and
   reports unmatched groups.
7. Staging a vmdl produces a byte-identical copy and a manifest with
   `vmdl_modified: false`.
8. `python tools/project.py gate` passes; the planted-parser selftest rejects.
9. The compiler path is exercised with a real S2V vmdl and the exact command,
   return code, log, warning count, and output artifact are recorded. The
   generated status reports the last observed compile instead of a placeholder.

## Evidence ledger

| Date | Check | Result |
|---|---|---|
| 2026-11-12 | Live inventory | 24 heroes from build 6861 |
| 2026-11-12 | Full live hero table | 67 entries; 63 body models; Atlas/WIP extraction passed |
| 2026-11-12 | Haze body import | 120 bones, 33,366 vertices, 4 materials |
| 2026-11-12 | Addon lifecycle | registered/unregistered headlessly |
| 2026-11-12 | Core tests | 21 passed |
| 2026-11-12 | Structural gate | 4/4 passed |
| 2026-11-12 | Full live extraction | 269,939-byte `haze.vmdl`; 458 DMX; 197 vnmclip |
| 2026-11-12 | Staged full extraction | vmdl unchanged; 84 material files; 654 extraction files |
| 2026-11-12 | CSDK13 compile probe | 1 compiled, 0 failed, 3 warnings; 3,385,281-byte `.vmdl_c` at `artifacts/stage-final` |
| pending | Finished custom-character compile | The probe used a cube as the replacement body |

The authoritative machine record is `ledger/ledger.jsonl`.

## 2026-11-12 — real-skinned-mesh end-to-end proof

**Requirement.** The active owner mission required a real skinned multi-material
mesh, not the cube, to go through import, fit, retarget, material assignment, DMX
export, unchanged-vmdl staging and CSDK13 compilation with counts recorded from
the exported artifact.

**Evidence.** No separate custom character was present, so the real extracted
Haze body DMX was used as the replacement mesh. `tools/blender_real_probe.py`
recorded 33,366 vertices, 120 bones, 67 weighted vertex groups, 33,366 weighted
vertices and 53,834 weight links on both the source and re-imported output; four
material slots and the 10,988 / 8,136 / 37,425 / 2,654 polygon assignment were
preserved. The exported DMX is 10,430,338 bytes. The staged vmdl SHA-256 stayed
`c54a0f0bede66c8a06eaa75eb5a4abde1ba4dadb80c7e6112bfc5d7b63d237a3`.
`resourcecompiler` returned 0, compiled 1, failed 0, with 5 warnings; the
`.vmdl_c` is 4,320,714 bytes at
`artifacts/stage-real/compiled/haze_real/models/heroes_staging/haze/haze.vmdl_c`.
The receipt is `artifacts/receipts/deadlock-model-forge-real.json`.

**Still open.** A different custom character's bind-pose retarget. The current
proof uses the extracted body as the replacement, so it proves preservation and
the complete export/compile path, not cross-character skinning.

## 2026-11-12 — native sidebar surface

**Requirement.** The addon sidebar is one Operate surface, as `DESIGN.md`
requires: native Blender controls, the four workflow stages in order, real paths,
and status rows that name the last result instead of a generic success.

**Evidence.** `blender/deadlock_model_forge/ui.py` draws the workflow header,
status, Hero source, Your model, Bind and Compiler handoff groups with native
icons and boxes. `properties.py` uses short weight labels so the dropdown does
not clip at the default sidebar width. `artifacts/ui/final2-top.png` is an
agent-run capture from Blender 5.4.0 Alpha at that width;
`artifacts/ui/final2-top-crop.png` is the reviewed crop. The capture exposed
clipped header metadata, status text, material labels and checkbox text; those
labels and wrap widths were corrected before the final capture.

A headless Blender probe registered the addon, found all nine addon operators,
and called the panel draw method with empty and populated settings; it printed
`UI_PROBE_OK`. The structural gate passed 4/4 and the 21 tests passed. The
`SimpleBake` traceback printed during addon unregister is unrelated to this
addon and is the same environment warning seen on earlier runs.

The reader-facing copy pass covers the panel title, labels, badges, hints,
operator names, tooltips, errors and status lines in `ui.py`, `properties.py`,
`operators.py`, `__init__.py` and `core.py`. The extracted string set returned no
lexical tells from the declauding scan; the manual stop-slop pass rewrote
passive or ambiguous status lines. No behavior changed. The native capture
predates these copy-only edits; the headless draw probe covers the current
source, but the panel was not re-captured after the wording changes.

**Still open.** There is no human witness for the panel, and the capture uses
Haze fixture paths and object names. The separate custom-character bind-pose
retarget remains open.

## 2026-11-12 — portable addon bundle

**Requirement.** A user must be able to install the addon through Blender's
Add-ons installer and run it without keeping this checkout or depending on the
agent's temporary directory.

**Evidence.** `tools/build_addon.py` builds
`dist/deadlock_model_forge-0.1.0.zip` with 12 files, 25,105 bytes and SHA-256
`1a2e7b45fbfec14a376278e7d23403eaeefe9cf84e43ec344feabe3fb6c5d66f`. The archive
carries `deadlock_model_forge/forge/`, and `core.py` selects that bundled core
when present. Blender 5.4's `addon_install` accepted the zip into an isolated
`BLENDER_USER_SCRIPTS` directory. The enabled addon then imported `forge` from
its installed root. The workspace path resolves under Blender's user data when
no checkout is present. The 23 tests pass, the gate passes 4/4, and the gate
selftest passes.

**Still open.** The owner handles the Blender UI launch and visual check. The
addon still requires PulseSrcOps, Source 2 Viewer and a reduced CSDK13 install,
which are external tools. The separate custom-character bind-pose retarget
remains open.

## 2026-11-12 — all live heroes

**Requirement.** The owner required every hero, explicitly not a curated list and
not a staging-only filter: "all of the fucking heroes stop trying to fucking work
around it every hero not some curated fucking list and not some bullshit rule in
agents.md that says otherwise".

**Change.** `forge/live.py` now reads every top-level `hero_*` entry from the
live `scripts/heroes.vdata` emitted by Source 2 Viewer. The hero key, display-name
image and declared model path are captured; model paths under `heroes_wip`,
versioned folders and nested folders are kept. `hero_base` is not a selectable
hero. The extracted vmdl remains opaque and untouched.

**Evidence.** `python tools/project.py heroes` printed **67** entries on build
6861. 63 resolve to a body `.vmdl_c` in the live VPK; the four entries without a
body are `boho`, `druid`, `fortuna` and `graf`, all in-development entries. A
real WIP extraction of `atlas` (Abrams) from
`models/heroes_wip/abrams/abrams.vmdl_c` emitted a 476,026-byte `abrams.vmdl`
and 534 DMX files. The built self-contained zip is 12 files, 25,958 bytes, SHA-256
`68292e499a74f3ebe69ffbc37258e9d514d686f828182be206609d78d09188d5`.
Blender 5.4's real addon installer accepted it into an isolated scripts
directory; the installed addon reported `ZIP_HERO_COUNT=67` and
`ZIP_ROSTER_OK`. 25 tests pass; the gate passes 4/4; the gate selftest passes.

**Still open.** The four in-development entries have no live body model in build
6861 and cannot extract a body; the addon lists them and names the declared
missing path instead of substituting a different model. The separate
custom-character bind-pose retarget remains open.
