# TICKET-0030 — Every live hero's tail, a probe lane, and a non-blocking scan

**Status:** implemented in 0.11.0; gate with all five probes passes.
**Owner:** ala
**Opened:** 2026-11-14

## Requirement

The owner's request, verbatim:

> the tail scanner is wrong again part of the ui pass and gate checker and probe
> fixes for one needs to be about making sure shit doesn't block the main thread
> if possible and for two the scanner got a tail from gen_man and hornet who don't
> have tails in the live release game but it didn;t get the tails from other heroes
> who do have tails. It got familiar but you blindseded me because you only tested
> on familiar and not every hero

and:

> why would I want it to only scan decompiled heroes when the built in source page
> detects all the heroes

## Findings

- `forge.tails.is_tail_bone` used `word in name`. `brow_inner_detail`, Hornet's
  `a_hair_braid_*`, `ponytail`, `coattail` and `cloak_tail` therefore became tail
  chains. The substring was the false positive, not the hero.
- `tailops.discover` only scanned the current extraction, its siblings when the
  parent was literally named `extractions`, and an optional folder. It never saw
  heroes the owner had not extracted, and the prior probe only used Familiar.
- `dmx_bone_names` returned whole printable structural runs, so a chain was named
  `name_string_owl_tail` rather than `owl_tail`.
- S2V can decompile only `vnmskel_c` under `models/heroes_` (59 DMX skeletons on
  build 6861). That is the live roster's bones without extracting hundreds of
  clips per hero.
- The gate never ran probes; missing Blender was invisible, and the cloth/pages
  probe failures were not reported by a green gate.
- The cloth probe measured pin drift against one bone head, so normal chain
  rotation failed as drift; it also expected Properties mirrors on the stock
  sidebar. The pages probe hosted its panel in `WINDOW` and never opened the
  sidebar, so 0/20 draws was reported as a probe failure rather than a probe bug.

## Contract

1. **Live roster first.** `forge.live.extract_tail_skeletons` extracts
   `models/heroes_/*.vnmskel_c` into `artifacts/tail-skeletons`, keyed by VPK
   mtime. `tailops.discover` scans those skeletons before local folders.
2. **Real tails only.** A name qualifies when a token is `tail` or starts with
   `tail`; clothing, hair, braid, ponytail, cuff, detail and weapon target tokens
   are excluded. Chain labels use the hero title from the Source page roster.
3. **No main-thread S2V.** `tailops.start_discover` returns immediately, runs the
   skeleton extraction through `jobs`, and schedules names/imports on a timer.
   A fresh cache scans without a subprocess.
4. **All tiles are shown.** The Tails grid no longer caps at 16; it shows every
   live option and names the live count.
5. **The gate runs probes.** `tools/probe_lane.py` produces PASS/FAIL/SKIP per
   probe, a summary, fresh-receipt validation, and a regression exit when a
   previously passing probe now fails. Missing prerequisites are SKIP, never PASS.
6. **Probe truth.** Pin drift compares simulated pinned vertices with an
   armature-only evaluation; sidebar panels are not treated as Properties
   mirrors; the pages probe opens the UI region and draws from a UI panel.
7. **Teardown noise is not evidence.** A fresh passing receipt survives a
   nonzero Blender exit caused by an unrelated add-on's `unregister`; a missing or
   failing receipt still fails.
8. **UI pass.** Tails, Source 2 IK, Bone map, Weights and the Mods/Components/Tools
   sections use the Popit title/micro/glyph grammar; the Tails page keeps one
   message bubble.

## Evidence

- `blender_tail_live_probe`: 19/19; 59 skeletons, 31 chains from the live VPK;
  Viper/Familiar/Tengu/Vindicta/Nano found; Hornet/Artist/Magician/Wraith/McGinnis
  and detail/braid/coattail/ponytail/cloak_tail absent.
- `blender_cloth_probe`: 25/25; pin drift 0.0 for jacket and hair, free motion
  bounded, page surface sidebar, pages switch correctly.
- `blender_pages_gui_probe`: 20/20 page draws, no addon exceptions.
- `blender_tail_ui_probe`: 6/6 with a real draw and 18 mapped channels.
- `python tools/project.py gate --blender ... --extractions ...`: unit tests,
  compileall, both source scans, BLAKE3, all five probe receipts pass.
- Not checked: a real mouse click on a live-roster tile, a game patch refresh, a
  tail in game, a hero whose skeleton has no `vnmskel_c`, or the installed zip's
  all-heroes grid.
