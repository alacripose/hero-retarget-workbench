# TICKET-0008 — Multi-part Mayu export and the vmdl head slot

**Status:** implemented; clean VPK source installed; owner visual acceptance pending.
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-mayu-all-parts.jsonl`
**Opened:** 2026-11-12

## Requirement

The owner's message, verbatim:

> god we're supposed to be porting the thicc mayu over the doorman and not have
> the doorman be the only thing visible, that includes the deagle parts and the
> hair

The owner then rejected the material layout that the first port installed:

> Okay well when I create the vpk from the csdk game folder it's going to include
> all of the files in the addon directory and with the materials not in the you
> know materials folder that makes it break valve convention

The addon source had root-level `body.vmat`, `head.vmat`, `hair.vmat`,
`lenses.vmat`, and `de_Mods_2.vmat_c`, plus tool caches and stale assets, so a VPK
built from `game/citadel_addons/thicc_mayu_v3` was not a conventional compiled
tree. The material references themselves also resolved at the content root.

The installed `thicc_mayu_v3` addon was showing the original Doorman because its
`doorman_doorman.dmx` was still the original binary. The workbench also joined
only the active part, so a collection containing body, head, lenses, hair,
ribbon tail and two Deagle meshes could not be exported as one model.

The Doorman vmdl keeps its visible head in separate mesh files
(`doorman_head4.dmx`, `doorman_head_ui_confident5.dmx` and their LODs). Replacing
only the body DMX therefore leaves the original Doorman head and hair on screen.

## Implemented requirement

1. `parts.export_meshes(settings)` returns every non-empty mesh in the selected
   collection (including child collections), then the scanned part list, then
   the active mesh as a last resort.
2. `DMF_OT_export_stage` duplicates and joins every returned part into a
   temporary `DMF Export` collection; the scene meshes are not renamed, joined,
   or deleted.
3. PulseSrcOps' nested `bpy.ops.ed.undo()` is skipped during the export by
   raising `bpy.app.debug_value` above 1 for the call and restoring it in
   `finally`. The nested undo crashed Blender 5.4 after PulseSrcOps wrote the
   four DMXs. The temporary collection is unlinked, not aggressively deleted.
4. For the Mayu port, the source collection is split along the vmdl's own mesh
   slots:
   - body: `doorman_doorman.002` (9,764 verts), `Deagle` (1,660),
     `Deagle.001` (5,635), `Fluffy Ribbon Tail 2 - Gell3D` (3,280), for 20,339
     vertices and `Body`/`DE_Mods_2`/`hair` materials;
   - head: `doorman_doorman.001` (9,494), `doorman_doorman` lenses (438),
     `CrescentHairMesh-Mayu` (5,041), for 14,973 vertices and
     `Head`/`Lenses`/`hair` materials.
5. The body DMX, its three LODs, the head DMX, its three LODs, and both head UI
   variants replace the vmdl's existing DMX paths. The vmdl itself is copied
   byte-for-byte and is never parsed or rewritten.
6. Material references are qualified at the model's content folder. PulseSrcOps
   writes `mtlName` as `scene.vs.material_paths[index]` joined with the material
   basename; the workbench sets that path to `models/heroes_wip/doorman_v2/materials`
   (derived from the vmdl/target DMX path) and restores the scene's previous paths
   and material indices after the export. Material names stay basenames, so the
   DMX carries `models/heroes_wip/doorman_v2/materials/body.vmat` and friends
   instead of a bare `body` token or a slash-sanitized underscore name.
7. The 12 Mayu material assets are copied under the same nested materials folder.
   The installed game addon is the clean compiled tree only: 38 files, 149 MB, no
   root vmats, no `tools_asset_info.bin`, thumbnails, stale particles, or old
   clips. The installed content source tree is 587 files, 148 MB, with no root
   material files; the 588-file clean stage includes its `stage.json` tool
   metadata. The previous 343-file/746 MB game tree and 1,019-file/473 MB content
   tree were moved to `_backup_*_thicc_mayu_v3_20261112` outside the scanned
   `content`/`game` addon folders.

## Non-goals

- Fixing the CSDK modeldoc crash. It remains a separate investigation.
- Parsing, rebuilding, or rewriting the extracted vmdl.
- Bundling a `.vnmskel` or treating the skeleton as the crash cause.
- Replacing the Doorman door/keyglow meshes. Their material warnings come from
  the reduced CSDK not containing the base Doorman door materials.

## Evidence

- `artifacts/mayu_export_probe.log` — all seven parts joined; export/stage
  returns `FINISHED` after the nested-undo fix.
- `artifacts/mayu_split_export_vpk.log` — body and head subset re-export with
  the material path set through `scene.vs.material_paths`; four DMXs each, 0
  errors. DMX material strings are full `models/heroes_wip/doorman_v2/materials/*.vmat`
  paths; no underscore-qualified names.
- `artifacts/mayu-vpk-stage.log` — clean stage: 12 custom material assets under
  `models/heroes_wip/doorman_v2/materials`, zero root material files, 588 files
  including `stage.json`; the installed content tree is 587 after removing it.
- `logs/mayu-vpk-compile.log` — CSDK13 return code 0; 38 compiled files; 23
  warnings (the same six >4-weight and reduced-CSDK door warnings). Every
  compiled `.vmat_c` is under `models/heroes_wip/doorman_v2/materials/` or
  `materials/default/`; there are no root vmats.
- `artifacts/mayu-vpk-gltf/doorman.glb` — six meshes: body, keyglow, both doors,
  head, and head UI. Body has three material primitives; each head mesh has
  three. Geometry still includes Mayu's body, head, hair, lenses, ribbon tail and
  both Deagles; this is group evidence, not a render witness.
- Installed clean game tree:
  `...\game\citadel_addons\thicc_mayu_v3` — 38 files, 149 MB, no root files.
  Installed content tree:
  `...\content\citadel_addons\thicc_mayu_v3` — 587 files, 148 MB, 12 nested
  material assets, no root files.
- `artifacts/mayu-split/body/` — `DMF_body_export.dmx` and LOD1–3.
- `artifacts/mayu-split/head/` — `DMF_head_export.dmx` and LOD1–3.
- `artifacts/mayu-vpk-stage/content/citadel_addons/thicc_mayu_v3/stage.json` —
  body/head DMX and LOD hashes, vmdl hash unchanged.
- `logs/mayu-split-compile.log` — CSDK13 return code 0; 43 compiled files;
  23 warnings (six >4-weight warnings and the reduced-CSDK door material
  warnings).
- `artifacts/mayu-vpk-stage/compiled/thicc_mayu_v3/models/heroes_wip/doorman_v2/doorman.vmdl_c`
  — 4,821,144 bytes; full-path `body`, `head`, `hair`, `lenses`, and `de_mods_2`
  references present; `doorman_head` and `doorman_hair` absent. The installed
  game addon contains this compiled tree only.
- `artifacts/mayu-all-proof/doorman_split.glb` — body mesh has three material
  primitives; head and head UI each have three. S2V did not mount the addon root
  for material lookup, so material appearance is not a visual witness.
- Installed:
  `C:\Users\ala\Downloads\Reduced_CSDK_13\content\citadel_addons\thicc_mayu_v3`
  and `...\game\citadel_addons\thicc_mayu_v3`.

## Remaining witness

The owner must launch the addon in Deadlock and confirm the Mayu body, head,
lenses, hair, ribbon tail and both Deagles are visible without the original
Doorman head/hair. The compile and glTF group counts are not a render witness.
