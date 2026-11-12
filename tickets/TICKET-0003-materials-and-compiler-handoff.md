# TICKET-0003 — Materials staging and the CSDK build mirror

**Status:** implemented; owner visual/compile acceptance pending.
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-materials-compile.jsonl`
**Opened:** 2026-11-12

## Requirement

The owner rejected the material staging and the compile mirror:

> the materials staging is currently total ass and the way it's flooding the
> csdk13 game addon folder with uncompiled files is dumb, the text for the
> materials path makes no note of what it's looking for

The concrete requirements:

1. A material root means a **content root**. Staging preserves its relative
   paths and copies a closed material inventory: `.vmat`/`.vmat_c`, texture
   images, and `.vtex` assets. Notes, JSON, thumbnails, model files, and
   arbitrary files in the root are not materials.
2. The hero material root is optional; leaving it blank uses the extraction's
   material tree. A custom material root is copied after the hero materials and
   overrides the same relative paths.
3. The UI and property descriptions must say what the path is looking for:
   `models/**/materials/*.vmat` plus the texture images, at paths preserved
   below the chosen root.
4. `stage.json` records material and texture counts separately.
5. Compile must not leave uncompiled source files in CSDK's
   `content/citadel_addons`. It uses a unique temporary
   `dmf_build_<addon>_<random>` folder, compiles it, copies only compiled `_c`
   files back under `<stage>/compiled/<addon>/`, and removes both the temporary
   `content` and `game` folders in `finally`.
6. A failed compile removes the temporary mirror and preserves the previous
   compiled output rather than replacing it with a partial tree.
7. The source vmdl remains byte-identical.

## Non-goals

- Parsing, rewriting, or compiling the hero vmdl outside CSDK13.
- Inventing a material format or flattening `.vmat` layers.
- Deleting the owner's existing CSDK addon folders.
- Copying arbitrary files from a material root because they happen to be
  non-DMX.

## Acceptance

- `tests/test_stage.py` covers the closed inventory, texture counts, and the
  absence of notes/JSON in a material-only stage.
- `tests/test_compile.py` proves the temporary mirror is removed on success and
  failure, only compiled `_c` files are copied, and old output survives a failed
  compile.
- The real CSDK13 compile reports the compiled file count and leaves no
  `dmf_build_*` directory under either `content/citadel_addons` or
  `game/citadel_addons`.
- The addon zip imports and all panel draw paths still work.

## Evidence

- `artifacts/receipts/compile-temp-mirror.log`
- `artifacts/receipts/deadlock-model-forge-real-workbench.json`
- `artifacts/receipts/deadlock-model-forge-lod-material-workbench.json`
- `artifacts/receipts/deadlock-model-forge-zip.json`
- `dist/deadlock_model_forge-0.2.2.zip`
- `ledger/ledger.jsonl`
