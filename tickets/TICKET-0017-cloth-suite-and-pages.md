# TICKET-0017 — the cloth suite, and one page per view

Status: implemented in 0.6.0
Authority: `logs/authority/2026-11-14-cloth-suite.jsonl`

## Owner request (verbatim)

> so the next step is going to be the cloth suite of tools that will handle stuff
> like cloth meshes, the cloth node systems, and the cloth chains on the blender
> side, in the modeldoc there's a ton of features for cloth and s2v actually now
> exports cloth accuratley for hero models, but the blender side doesn't handle it
> at all in any of the addons, so for example importing shiv using the workbench he
> doesn't have his hair or his jacket. Also, splitting up the panels into their own
> views would be nice instead of it being one view with lots of panels, maybe we
> could do something that's not in the tools panel but instead a actual viewport
> type based on the properties panel instead (please) because the n button tools
> panel is my least favorite part of old blende.

## What was actually wrong

An S2V extraction of a hero is **several** mesh DMXs. Shiv's extraction folder
carries `shiv_body.dmx`, `shiv_hair3.dmx`, `shiv_jacket4.dmx`, `shiv_glasses2.dmx`
and `shiv_gun1.dmx`, each with its own LODs. `dmf.import_hero` opened
`settings.body_dmx` with `append="NEW_ARMATURE"` and `_pick_imported` kept one
mesh plus one armature, so every other file in the folder was never opened. That
is the whole reason a ported Shiv had no hair and no jacket.

## Contract

1. **Every mesh beside the body is imported onto the hero armature.**
   `forge/cloth.py:mesh_files` names the candidates from the extraction itself: a
   mesh is the base of a `_lod<N>` family (the LOD is named after the part, the
   base may carry an index, so `shiv_glasses_lod17` belongs to `shiv_glasses2`) or
   a name that ends in a part word. `cloth_ops.import_companions` imports each
   with `append="APPEND"` and keeps only files that actually produce a mesh, so a
   clip sharing the hero's prefix is skipped by observation, not by guess. The
   page reports what was imported and what was skipped.
2. **The chains are read from the skeleton, not from a vmdl.**
   `forge/cloth.py:chains` groups numbered bones by base and side
   (`coat_0..coat_3`, `sleeve_L`, `hair_01`), requires at least two segments and
   orders by the number, not by text. `cloth_ops.scan_chains` records each chain's
   name, side, segments, first bone and member list.
3. **One page at a time in the Properties editor.** Blender addons cannot add an
   editor type, so the surface is a tab: `DMF_PT_props_main` under
   `PROPERTIES`/`scene` draws a page selector (Setup, Source, Parts, Cloth,
   Skeleton, Rules, Animations, Compare, Weights, Handoff). Every sidebar panel is
   mirrored by a subclass that inherits its `draw` body and changes only space,
   context, parent and `poll`; `poll` compares `scene.dmf.props_page`. Nothing is
   duplicated, so a fix in `ui.py` reaches both surfaces. The sidebar stays
   registered too — the mirrors are the same panels, not a fork.
4. **Cloth nodes stay in the modeldoc.** The page says, in those words, that it
   imports meshes and shows chains and does not author simulation nodes.

## Evidence

`tools/blender_cloth_probe.py` against the owner's real Shiv extraction, with
PulseSrcOps enabled and the installed addon copy disabled:

- 14 of 14 checks passed. Receipt: `artifacts/receipts/cloth.json`.
- Hero imported: `shiv_body` armature, 161 bones.
- Five meshes on that one rig, all skinned to it: `shiv_body.001` (35,077 verts),
  `shiv_glasses2` (1,374), `shiv_gun1` (4,664), `shiv_hair3` (2,068),
  `shiv_jacket4` (3,880) — 47,063 vertices total.
- 19 chains; the cloth-like ones include `coat` (4), `hair` (3), `sleeve_L` (2),
  `sleeve_R` (2); `collar_L/R/back` are two-segment chains.
- Properties surface: 16 mirrored pages registered, 17 sidebar panels still
  present, and switching pages makes `DMF_PT_props_cloth`,
  `DMF_PT_props_skeleton` and `DMF_PT_props_handoff` poll true only on their own
  page.
- Unit tests: `tests/test_cloth_suite.py` (9), whole suite 174 passing.

## Not proven

- The Properties tab has not been looked at in a running Blender window: the probe
  proves registration and `poll` switching, not how the page selector draws. The
  sidebar GUI probe still cannot reach the Properties editor.
- No cloth simulation was run on the imported meshes; the chains are named, not
  bound to any solver.
- Cloth constraint nodes and their modeldoc sections are unchanged and still only
  scanned by `forge/modeldoc.py`; a game compile of a cloth model was not run.
