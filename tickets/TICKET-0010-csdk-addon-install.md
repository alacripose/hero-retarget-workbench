# TICKET-0010 — Stage and compile into the CSDK13 addon folder

**Status:** implemented; unit tests and gate pending observation at time of writing.
**Owner:** ala
**Authority:** `logs/authority/2026-11-13-csdk-addon-install.jsonl`
**Opened:** 2026-11-13

## Requirement

The owner's messages, verbatim:

> hey why the hell when I stage a model in the csdk13 and compile it there is literally nothing in the csdk13 itself? I have the model open in the modeldoc in thick mayu and I don't need the model I'm editing to be overwritten so I'm still using the normal thicc_mayu_v3 but when I stage and compile nothing changes in the folder. why does it copy to a temp directory for clering instead of just eeping th addon files in the addon directory set in the ui

> why the fuck???? when i press stage it should set up the addon with the name that is in the addon text field with the files to compile??? so I can open it in the csdk itself?? what the hell kind of backwards ass logic is this

## Problem observed

- Export & stage wrote to `<workspace>/artifacts/staged/<addon>`, never into the
  CSDK.
- Compile copied that stage into a unique
  `content/citadel_addons/dmf_build_<addon>_<random>` folder, compiled it, and
  deleted both the content folder and its `game` counterpart in `finally`.
- Result: the CSDK13 addon tree the owner has open in modeldoc never changed,
  and there was nothing under `game/citadel_addons/<addon>` to pack a VPK from.

## Contract

1. Export & stage installs the addon at
   `<csdk>/content/citadel_addons/<addon_name>`, where `<addon_name>` is the
   **Addon** field, so the addon exists in the CSDK itself.
2. The destination root is the **Install root** field; blank means the CSDK13
   root from Setup. A non-blank root is used as given (headless probes and the
   CLI pass their own output folder).
3. Staging merges into an existing addon folder. It overwrites only the files
   the stage owns and never deletes the folder, so other files in an addon the
   owner has open in modeldoc survive.
4. The stage's vmdl is still copied byte-for-byte from the S2V extraction and
   verified after staging. Nothing here writes a vmdl.
5. Compile runs `resourcecompiler` in place from
   `citadel_addons/<addon>/<vmdl>` and leaves the compiled `_c` files in
   `<csdk>/game/citadel_addons/<addon>`, the folder modeldoc opens and a VPK is
   packed from.
6. No temporary `dmf_build_*` folder and no deletion step remain. A stage built
   outside the CSDK is installed into the content addon first (merging), then
   compiled.
7. A failed compile reports zero compiled files and does not remove the
   previous compiled output or the staged addon.

## Change

- `forge/compile.py` — `compile_stage` installs to the content addon, compiles
  in place, reports `content_addon`, `game_addon`, `compiled_files` (from the
  game addon) and `output`; refuses an addon name that could leave the tree.
- `forge/stage.py` — staging no longer deletes an existing addon folder.
- `blender/hero_retarget_workbench/operators.py` — Export & stage resolves the
  destination (Install root, else the detected CSDK13 root) and reports the
  installed path; compile reports the game addon it installed into.
- `properties.py`, `ui.py` — the field is "Install root (blank = CSDK13)" and
  the hint names both CSDK paths.
- `tools/project.py` — compile ledger rows record `content_addon` and
  `game_addon` instead of `build_addon_removed`.
- `tools/blender_real_probe.py`, `tools/blender_lod_material_probe.py` — read
  the compiled output from the detected CSDK game addon.

## Not claimed

No real `resourcecompiler` run is part of this ticket's evidence yet. The
compile is exercised against a fake compiler in `tests/test_compile.py`; a real
CSDK13 compile into `thicc_mayu_v3` remains the owner's action and must be
observed before it is called working.
