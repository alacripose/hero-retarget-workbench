# TICKET-0008 — Multi-part Mayu export and the vmdl head slot

**Status:** implemented; owner visual acceptance pending.
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-mayu-all-parts.jsonl`
**Opened:** 2026-11-12

## Requirement

The owner's message, verbatim:

> god we're supposed to be porting the thicc mayu over the doorman and not have
> the doorman be the only thing visible, that includes the deagle parts and the
> hair

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
6. A root `de_Mods_2.vmat` copy of `deagle.vmat` makes the DMX material token
   resolve. `deagle.vmat` remains under the nested material path for the DMX
   path spelling.

## Non-goals

- Fixing the CSDK modeldoc crash. It remains a separate investigation.
- Parsing, rebuilding, or rewriting the extracted vmdl.
- Bundling a `.vnmskel` or treating the skeleton as the crash cause.
- Replacing the Doorman door/keyglow meshes. Their material warnings come from
  the reduced CSDK not containing the base Doorman door materials.

## Evidence

- `artifacts/mayu_export_probe.log` — all seven parts joined; export/stage
  returns `FINISHED` after the nested-undo fix.
- `artifacts/mayu_split_export.log` — body and head subset exports, four DMXs
  each, 0 errors.
- `artifacts/mayu-split/body/` — `DMF_body_export.dmx` and LOD1–3.
- `artifacts/mayu-split/head/` — `DMF_head_export.dmx` and LOD1–3.
- `artifacts/mayu-all-stage/content/citadel_addons/thicc_mayu_v3/stage.json` —
  body/head DMX and LOD hashes, vmdl hash unchanged.
- `logs/mayu-split-compile.log` — CSDK13 return code 0; 43 compiled files;
  23 warnings (six >4-weight warnings and the reduced-CSDK door material
  warnings).
- `artifacts/mayu-all-stage/compiled/thicc_mayu_v3/models/heroes_wip/doorman_v2/doorman.vmdl_c`
  — 4,820,622 bytes; `Body`, `Head`, `Lenses`, `hair`, `de_mods_2` present;
  `doorman_head` and `doorman_hair` absent.
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
