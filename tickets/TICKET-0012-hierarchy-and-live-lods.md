# TICKET-0012 — bone hierarchy view and built LOD meshes

**Status:** implemented; headless probe passes; the export path itself was not run
against a real addon in this change.
**Owner:** ala
**Authority:** this message and `logs/authority/2026-11-13-live-lods-hierarchy.jsonl`
**Opened:** 2026-11-13

## Requirement

The owner's message, verbatim:

> the ui in the blender addon has no visual hierarchy editor and as well when you
> press the staging button it creates extra copies of the armature which causes
> export time to really lag, what I'd prefer is that the extra lods are made live
> as edits/weights are made/changes and they don't require regenerating them each
> time because each time the staged stuff in the blender collection view has to be
> deleted otherwise it duplicates

## What was wrong

1. The Skeleton panel showed a flat bone map. The hero rig's parent chain was
   nowhere in the UI, so a re-parented bone (the `head` under `spine_3` defect)
   was invisible in Blender.
2. `dmf.export_stage` let PulseSrcOps generate LODs. `exports/plan.py`
   `_make_lod_collection` copies **every** exportable object of the export scope,
   armature included, into a `<scope>_lodN` collection per level and links the
   copies into the scene collection. The addon's cleanup only removed the
   `DMF Export` collection, so each Export & stage left a LOD collection and an
   armature copy per level behind, and the next export copied them again.

## Contract

1. **Bone hierarchy.** `dmf.refresh_hierarchy` reads the hero armature depth
   first into `settings.hierarchy`; `DMF_UL_hierarchy` draws it indented with the
   parent on the right; `dmf.select_hierarchy_bone` makes the highlighted bone
   active and selects it in edit mode. It never re-parents, edits or guesses.
   Blender 5.4 dropped `Bone.select`, so object mode sets `bones.active` and edit
   mode narrows `edit_bones[].select`; `object.select_all` is not called in edit
   mode because its poll fails there.
2. **Built LODs.** `dmf.build_lods` joins the export scope once per level,
   applies a Decimate modifier with ratio `1 - decimate% * level`, keeps the mesh
   bound to the hero armature, and stores it in `DMF LODs <addon>`. The meshes
   stay in the file; `dmf.clear_lods` removes them. Rows carry level and vertex
   count, and `lod_tick` records the work tick they were built at so the panel can
   say when weights or fit have moved on.
3. **Export reuses them.** With **Use built LODs** on, export copies each built
   level into the export scope under `<stem>_lodN`, shares its mesh data, and sets
   `generate_lods = False`, so PulseSrcOps neither decimates nor copies the
   armature. `dmf.export_stage` refuses when the toggle is on and nothing is built.
4. **Cleanup.** After an export, `_purge_export_leftovers` removes every
   collection and object created by that export (the temp scope, its `_lodN`
   collections, the joined mesh, generated LOD meshes and armature copies) and
   purges only zero-user datablocks. Objects that existed before the export are
   never touched.

## Non-goals

- Re-parenting, re-ordering or renaming bones from the hierarchy panel.
- Making the built LODs follow later weight edits automatically. They are a
  snapshot at `lod_tick`; the panel says when they are stale and Rebuild LODs
  replaces them.

## Evidence

- `tools/blender_skeleton_lods_probe.py` (headless, `--factory-startup`):
  hierarchy rows/depth/parent/child counts, active bone and edit-bone selection,
  three LOD levels with decreasing vertex counts, a rebuild that replaces the old
  objects without leaving duplicates or a second armature, clear, registration of
  the UIList and both operators, and a purge that removes an export's LOD
  collection and armature copy while leaving the user rig alive.
  Log: `artifacts/skeleton-lods-probe.log`.
- `python tools/project.py gate` passes (unit tests, compileall, no KV3 parser,
  no vmdl writes, blake3).

## Correction 2026-11-13: an indented list is not a visual editor

**Owner, verbatim:** *"and I swear to god a list tree for the visual heirarchy
editor is literally the worst fucking thing you could have gone for, instead of
something that actually displays bone positions relative to each other?"*

Requirement 1 above was implemented as an indented name list. That is a text
index, not a spatial view: it cannot show that a neck offset was folded into its
parent, or that a bone hangs sideways off the wrong joint.

The delivered surface is `hierarchy_view.py`: a bone map drawn as a POST_PIXEL
overlay in the 3D viewport.

- Every bone is drawn from its rest `head_local` to `tail_local`, projected on a
  chosen plane (front/side/top), fitted into a card with one uniform scale so an
  angle in the map is the angle in the rig (`forge/rigmap.layout`).
- Heads are joints and get a dot; parent links are drawn between heads, which is
  what makes a folded or re-pointed parent visible.
- Colour carries depth (warm root, cool tips). The selected bone is amber, its
  ancestors orange, its children teal; the chain is also printed as text.
- `dmf.pick_bone_map` is a modal picker: hover highlights the joint under the
  pointer, left click selects that bone in the rig, Esc cancels. It is an
  editor, not a picture.
- The map reports its own draw failure through `bone_map_error`, because a
  raising POST_PIXEL handler otherwise repeats silently every frame.
- The name list stays as a secondary index (`Bone list`) with the same selection.

Evidence: `forge/rigmap.py` layout/hit-test unit tests (`tests/test_rigmap.py`,
12 tests), the headless probe's placement/pick/draw assertions, and a real GUI
render of the viewport overlay at
`artifacts/hierarchy-diag/bone-map-viewport.png`.

## Remaining witness

The real Export & stage run into a CSDK addon was not exercised here: it needs a
proof, a live extraction and PulseSrcOps. The next real export is the witness
that the LOD collections no longer accumulate.
