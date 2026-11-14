# TICKET-0031 — Clear tail writes, per-hero clips, and the missing model variants

**Status:** implemented in 0.12.0; gate with all five probes and the installed zip pass.
**Owner:** ala
**Opened:** 2026-11-14

## Requirement

The owner's request, verbatim:

> I ave some feedback from you, currently the animations pane makes it hard to
> understand how to merge tails from models, so I just accidentally added
> werewolfs animations into the clps panel where shiv's animations are after
> loading werewolfs model, so the map channels and blend all buttons are
> ambiguous and I don't know how to merge them. Also some heroes like drifter for
> example import at a lagrer size and rotated weirdly, and the hero scanner should
> be expanded, since currently stuff like werewolf transform aren't included,
> there's two nanos, familiar wip is the right familiar and I don't know if it
> handles it so it might be operating off of familiar without the wip, minions and
> troopers and npcs aren't included in things, currently the tail previews are too
> large and stretch the side by side panes instead of having multiple smaller panes

## Findings

- `clipops.roots` added `extraction_dir`, the body folder, the live model and the
  vmdl, so a stale Shiv extraction could contribute rows after a Werewolf body
  was selected.
- `DMF_OT_import_hero` never rescanned clips, so the previous hero's rows stayed
  in the panel.
- The clip AnimGraph filter was inverted (`row.ag != wanted`), so choosing AG2
  showed everything except AG2.
- `DMF_OT_blend_tail` used `settings.clips[settings.clip_index]` implicitly;
  `blend_tail_all` wrote every row in the panel, including another hero's clips.
- `live.list_heroes` only read top-level `heroes.vdata` entries. It missed
  `models/heroes_wip/werewolf/transform/werewolf_transform.vmdl_c`, the alternate
  Familiar/Nano bodies, Ratking minions, troopers and NPC models.
- `Forge.live.choose_body` did not recognise `drifter_model` or `werewolf_hull`
  as body names, and it allowed animation DMX files into the fallback.
- Drifter's mesh data was 28.8 x 83.7 x 108.9 units, but after companion imports
  all 128 pose bones held a sampled pose. The evaluated body was 90 x 75 x 60 and
  looked rotated. The cause was `drifter_weapon_stand_idle.dmx` satisfying a part
  word and its animation being left on the armature, plus failed-candidate action
  removal re-evaluating the stale pose.
- The Tails grid used two columns and `template_icon(scale=5.0)`, so previews
  stretched the panel.

## Fixes

- Clip roots now follow the current body/model; a stale extraction is only read
  when the body still lives inside it.
- Every hero import clears old rows, rescans clips for the current hero, resets
  the tail pairing, and tags each row with `source_hero`.
- The AnimGraph filter shows the selected graph.
- The Tails page now has a selected-source card, a named **Source clip** enum, a
  three-column small-tile grid (`scale=2.2`), **Pair hero tail bones**, **Write
  selected clip to tail**, and **Write every &lt;hero&gt; clip to tail**. "Write all"
  only includes clips whose `source_hero` matches the current hero.
- `live.list_heroes` augments the roster from `models/heroes_wip`,
  `models/heroes_staging` and `models/npc`, keeps real character variants
  (transform, WIP body, V2 body, minions, troopers, bosses, neutrals) and excludes
  guns, FX, break pieces, particles and props. Exact duplicate model paths are
  collapsed; the WIP Familiar is titled `Familiar · WIP` and its base is
  `Familiar · Base`; Calico's Nano model is titled `Calico · Nano`.
- `looks_like_body` accepts `model` and `hull`; `_body_score` rejects
  clips/animation/anims folders.
- `DMF_OT_import_hero` resets the bind pose after the body import.
  `import_companions` snapshots the pose and NLA state, restores the action and
  bone bases after every candidate, removes failed-candidate actions, and resets
  the bind pose after the loop.
- Version bumped to 0.12.0.

## Evidence

- `python -m pytest tests -q`: 245 passed.
- `python -m compileall -q forge blender/hero_retarget_workbench tests tools`: pass.
- `python tools/project.py gate ...`: all gate checks pass.
- `blender_pages_gui_probe`: 20/20 page draws, 0 exceptions.
- `blender_tail_ui_probe`: 8/8; 40 tail options (31 live) drawn.
- `blender_tail_live_probe`: 20/20.
- `blender_cloth_probe`: 23/23.
- Drifter operator probe: body field repaired from a head to
  `drifter_drifter_model.dmx`; mesh dimensions returned to 28.84 x 83.71 x 108.86;
  pose bones moved back to 0; 218 drifter clips, none from Shiv; tail rows 0.
- Installed zip probe: 10/10.
- Built `dist/hero_retarget_workbench-0.12.0.zip`: 62 files, 422,501 bytes,
  sha256 `4d76274e3e49053f7d32e390b346f21816ae41aa8852b272a11481586934ffd4`,
  BLAKE3 `460f07672790415f04d27a7b866884608963f8d1ba91238032041a658c7807b9`.

## Not checked

- A real click on the new Source model variants and extracting an NPC.
- A visual review of the new three-column tail grid at multiple panel widths;
  the draw pass executed, but the probe screenshot shows the Setup page.
- A tail write in-game.
