# TICKET-0032 — Components read a model's render list, not a hero name list

Status: implemented in 0.12.1
Authority: `logs/authority/2026-11-14-components-non-hero.jsonl`

## Owner report (verbatim)

> components tab doesn;t detect components of things if they're not heroes, might
> be one of those cases where the older versions expected specfic functions per
> page which need to be updated with the expanded scope

## What was wrong

`forge.components.inventory` walked the extraction and kept files whose stem
contained `gun`, `weapon`, `hat`, `head`, `hair`, `attachment`, `cosmetic` or
`prop`. That is a hero naming convention, not a model rule. A non-hero model's
parts are commonly generic: `midboss_unnamed_1.dmx`, `ratking_minion_ratking_minion.dmx`,
`mirage_nashala_unnamed_1.dmx`. The scan returned zero rows even though the vmdl
listed those meshes, and it also returned zero when the saved extraction belonged
to the previous hero instead of the imported body.

## What changed

- `forge/components.py` now reads the model's vmdl `RenderMeshFile` list through
  the existing `forge.modeldoc.render_mesh_files` section reader. The render list
  is the authority for both heroes and non-heroes.
- LOD meshes (`_lodN` in the render name or filename) are excluded. The primary
  body is identified by a body/model/hull name, or by the first non-LOD render
  mesh for a generic non-hero model, and is left unselected by the page. Other
  render meshes are components.
- A filename-word scan remains only as the fallback when no readable vmdl or
  render list exists. That keeps the old behaviour for a hand-made folder.
- `dmf.scan_components` derives its source from the imported body first. A stale
  `extraction_dir`/`vmdl` from the previous hero is ignored when it does not
  contain that body; the vmdl beside the body is used.
- The page's note distinguishes render meshes from real components, and says
  plainly when a model has one render mesh and no separate components.
- `stage` records `primary` in the manifest and never registers the primary body
  as a body-group choice.
- `tools/blender_components_probe.py` is the persistent probe for this page. It
  deliberately points the saved fields at Shiv while importing the midboss NPC
  body, then scans Familiar WIP, so both stale-source repair and non-hero render
  lists are exercised.

## Evidence

- `python -m pytest tests -q`: 248 passed, including non-hero render list, LOD
  exclusion, primary-body selection, and primary-body merge refusal.
- `tools/blender_components_probe.py`: 9/9 checks.
  - midboss: one render mesh, body row unselected, note `1 render mesh, no
    separate components`; the scan followed the NPC vmdl, not the stale Shiv one.
  - Familiar WIP: 11 components and 12 render meshes; `familiar_wip_8inf_body8.dmx`
    unselected; `familiar_wip_weapon2.dmx` selected.
- Real pure inventories: Drifter 1 body + 2 head parts; Familiar 11 components;
  Shiv body + gun/glasses/hair/jacket; Kelvin body + gun; midboss and Ratking
  minion one body each; Werewolf body + `primary_weapon_only1`.
- Built `dist/hero_retarget_workbench-0.12.1.zip`: 62 files, 424,371 bytes,
  sha256 `a8c88865e2b48f03eda8ba27ca114b25bc639052ff10029bda2197f6c69255c1`,
  BLAKE3 `eb1f82480879c8e3ef7d3ec9909756cf5b8d041d71bd32f9a651f20494faef27`.
  Installed-zip probe 10/10.
- Not checked: staging/compiling a non-hero component, or clicking the
  Components page in a running Blender window. The operator path and draw code
  are registered, but this pass did not take a UI screenshot.
