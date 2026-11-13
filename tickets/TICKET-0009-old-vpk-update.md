# TICKET-0009 — Old addon VPK import and live hero-model update

**Status:** implemented; real Mayu migration, CSDK13 compile, unit tests, addon zip probe, compiled addon installation, and an agent-run retail launch witness pass; owner visual acceptance pending.
**Owner:** ala
**Authority:** `logs/authority/2026-11-13-old-vpk-update.jsonl`
**Opened:** 2026-11-13

## Requirement

The owner's message, verbatim:

> okay I need a new feature for it that allows importing an old vpk and updating it's hero model to the version that the game's updated files use, while still preserving cloth chain/cloth physics nodes and the materials and models in the hero retarget workbench

## Contract

1. Accept an old compiled addon VPK or an already-extracted addon content directory.
2. Extract a VPK through Source 2 Viewer CLI; a directory is used in place. The
   old modeldoc is found by the current live model's relative path when that
   path exists. An explicit `--old-vmdl` / **Old model vmdl** selection handles
   packages with several models; ambiguity is refused by name rather than
   guessed.
3. Use the current live hero extraction as the base. The old addon must not
   replace the live extraction wholesale.
4. Discover the old model's cloth/physics top-level sections by class marker
   (`softbody`, `cloth`, `physicsjoint`) and transplant their text exactly. The
   current `Softbody`/`PhysicsJointList` names are examples, not a closed list;
   nested `ClothChain`, `ClothChainHinge`, clusters, shapes and
   `PhysicsJointConical` joints are copied byte-for-byte. No cloth chain or
   joint is inferred or rebuilt.
5. Preserve an old custom render model by comparing its `RenderMeshList` paths
   and DMX bytes with the live extraction. The default `auto` policy keeps the
   old model only when it differs; `old` always keeps it and `live` always uses
   the live meshes. The old `RenderMeshList`/`MaterialGroupList` are transplanted
   when the old model or its groups differ.
6. Overlay the old addon's `.vmat`, `.vmat_c`, texture and `.vtex` assets onto the
   live extraction with relative paths preserved. Old model files, physics
   hulls, and the old skeleton are copied beside the preserved meshes.
7. Expose the operation in the Blender **Update old addon** subpanel: old
   VPK/folder, output stage, updated addon name, old-model policy, cloth/physics
   preservation, material preservation, replace-output, and the update action.
   The job runs off the main thread, then fills the stage/vmdl/addon fields and
   exposes the old content root and largest old model for the existing workbench
   import/material flows.
8. Write `stage.json` with the merged vmdl hash, old/new vmdl hashes, model
   policy, preserved model files, material/texture counts, section actions,
   missing sections, and cloth-chain/hinge counts.
9. Append a ledger row for the migration. A compile is only recorded when a
   compiler actually ran; a missing compiler is a limitation, not a pass.

## Deliberate boundary change

The earlier workbench rule said the live vmdl is opaque and must never be
parsed or rewritten. This feature supersedes that sentence for migration only:
it reads **top-level modeldoc sections** and writes a new merged vmdl. It does
not introduce a general KV3 parser, and `forge/modeldoc.py` is line/brace section
extraction, not a KeyValues3 reader. The live vmdl remains byte-identical when
no old model is being merged.

## Non-goals

- Rebuilding or simulating cloth/physics from the live model.
- Guessing a missing old section, DMX, material, or texture.
- Parsing arbitrary KV3 or adding a KV3 dependency.
- Claiming a compile when the current CSDK has no `resourcecompiler.exe` or a
  required compiler module is missing.
- Automatically installing the migrated addon into the game or rebuilding a VPK.

## Evidence

- `tests/test_modeldoc.py` and `tests/test_migrate.py`: 15 tests pass. They cover
  exact section insertion/replacement/absence, arbitrary cloth/joint section
  discovery, explicit old-vmdl selection, duplicate-section refusal, custom DMX
  preservation, live-model policy with cloth retained, old material overlay,
  missing-model refusal, output collision, and the merged manifest.
- Real Mayu source addon:
  `C:\Users\ala\Downloads\Reduced_CSDK_13\content\citadel_addons\mayu`.
  Live extraction:
  `artifacts/live-doorman-vmdl/models/heroes_wip/doorman_v2/doorman.vmdl`.
  Output:
  `artifacts/updates/mayu_current/content/citadel_addons/mayu_updated`.
  Result: 2 `ClothChain`, 9 `ClothChainHinge`, 18 `PhysicsJointConical`,
  23 old model files (custom DMX retained), 111 old material assets and 89
  textures; old `Softbody` and `PhysicsJointList` output hashes equal their old
  hashes. The output is 343 MB.
- `artifacts/mayu_update.log` and the `update-addon` ledger row.
- VPK-input smoke test: `Bepop Shocked.vpk` was extracted through S2V and
  migrated onto the live Doorman extraction. The old Bebop modeldoc has no
  `Softbody`/`PhysicsJointList`, so those two sections were recorded `absent`
  rather than invented; its `RenderMeshList` and 5 model files were preserved,
  and 13 old material assets/12 textures were overlaid. Log:
  `artifacts/vpk_update_probe.log`. The Bepop probe output was temporary and
  removed after recording; the Mayu migration is the cloth-bearing evidence.
- Blender UI probe: `artifacts/ui_update_probe.py` and `artifacts/ui_update_probe.log`;
  `dmf.update_old_addon` returned `FINISHED`, the background job finished `OK`,
  the workbench fields were filled with the migrated vmdl/body/custom model/material
  root, and the output manifest contained 2 chains, 9 hinges, 23 model files and
  111 material assets. A `blender-update-probe` ledger row records the run.
- `artifacts/addon-build/hero_retarget_workbench-0.2.5.zip`: 32 files, including
  `forge/migrate.py` and `forge/modeldoc.py`.
- `tools/blender_zip_probe.py`: 9 panels, 43 operators, 50 icons, old-addon
  update operator registered, `.blend` path persistence and namespace isolation
  pass. Report: `artifacts/receipts/hero-retarget-workbench-zip-update.json`.
- Restored-CSDK compile: `logs/update-addon-compile.log` and the `compile`
  ledger row with `result: pass`. `resourcecompiler` returned 0 with **1
  compiled, 0 failed, 42 compiled files, 21 warnings**; `doorman.vmdl_c` is
  5,470,101 bytes. A control compile with the `Softbody` block removed is a
  different 5,459,202-byte file, proving the compiler retained the transplanted
  cloth data. The compiled tree is installed at
  `Reduced_CSDK_13/game/citadel_addons/mayu_updated` (42 files, 158 MB); the
  source stage is `Reduced_CSDK_13/content/citadel_addons/mayu_updated`
  (688 files, 343 MB).
- Retail launch witness (agent-run, 2026-11-13): packed the compiled tree as
  `artifacts/mayu-launch/mayu_updated.vpk` (165,051,918 bytes, SHA-256
  `f64fd09e79c2cedbd77dad075184658c899520c9ca6b66f710d002dd32073b2c`) and
  installed it as `game/citadel/addons/pak01.vpk`; the retail client's
  filesystem log mounts that path as `(vpk)`. The client log records
  `Loaded hero 45/hero_doorman` and `VMDL Camera Pose Success` for
  `models/heroes_wip/doorman_v2/doorman.vmdl`. In Sandbox the Mayu custom model
  replaced the Doorman body; the screenshots are `desktop-13.png` and the
  `move-1..3.png` walk sequence under `artifacts/mayu-launch/`. The dangling
  key/cloth remained attached and moved with the character; the source has two
  `ClothChain` entries (`gun_key_center`, `key_pivot`), 9 hinges and 18 physics
  joints.
- The material warning is recorded, not erased: 50
  `Texture g_tAltColor_Reveal doesn't exist` lines occur for the old
  `hair`/`body`/`head`/`lenses` vmats. The old source vmat carries the same
  stale derived-texture path, and the base body/head/hair textures render in
  the captures. The old `models/heroes_wip/doorman_v2/clips/ui_hero_reveal.vnmclip_c`
  is also absent from the old addon; the client logs `ERROR_FILEOPEN` for it.
- Full witness: `artifacts/mayu-launch/launch-report.json`; script:
  `artifacts/mayu-launch/record_launch.py`. The row `command: launch` in the
  ledger carries the hashes and observed lines.

## Remaining witness

An agent-run launch and render observation is recorded above; the owner's visual
acceptance is still separate. The current captures are rear views because the
retail third-person camera stayed behind the hero. The compile and the control
compile prove the `.vmdl_c` changed when `Softbody` was removed; they are not a
render witness. The inherited alt-reveal texture warnings and missing old
reveal clip remain named material limitations, not migration failures claimed
as clean.
