# TICKET-0029 — Tail tiles from any hero, and the import blind spots

**Status:** implemented in 0.10.0; gate and real Familiar probes pass.
**Owner:** ala
**Opened:** 2026-11-14

## Requirement

The owner's request, verbatim:

> okay a nother popit and family project ui pass needs to be done also the tail section needs to be able to detect tails from any hero not just ones from the custom model and not just the ones from the imported hero, which is why I mentioned clip scanning, many of the heroes who have tails their tail animations are contained in their clips/ag2 animations, I was expecting more of a visual tile selector that shows a preview window that shows the heroes tails as options. also, currently it's still only been designed with tests on shiv and the mayu which has left serious blind spots in the import process for many heroes and older models on my drive

## Findings

- Familiar's body is `models/heroes_wip/familiar/familiar_wip_8inf_body8.dmx`. It has
  195 bones and the tail names `tail_0..tail_8`, `tail_end`, `tail_finger_0..5`
  and `weapon_target_tail`.
- `familiar_wip_head5.dmx` is larger than the body. The old inventory fallback
  picked the largest DMX, saved the head as the body, and PulseSrcOps then
  raised `IndexError` in `flex.addDrivers` because the fresh fcurve had no
  modifier to remove.
- `forge.cloth.mesh_files` accepted cloth words, an exact body suffix and LOD
  families only. Familiar's numbered head did not match, so the import skipped it.
- The tail section matched the imported hero skeleton against the selected custom
  armature. It did not inspect the extraction's clip/AG2 DMX headers.
- A DMX name table is NUL-separated ASCII in the binary header. Reading it is
  enough to find `tail` tokens in a clip without importing the clip or decoding
  compiled data.

## Contract

1. **Body choice is name-led, never size-led.** `forge.live.looks_like_body`
   accepts `body`, `body8`, `bodyN`, `body_lodN` and numbered body variants.
   `choose_body` rejects head/hair/clothes/weapon/appendage words and never
   prefers a larger head. The import repairs a stale non-body `settings.body_dmx`
   from the same folder before opening it.
2. **A hero import carries its real parts.** `PART_WORDS` includes head, eyes,
   glasses, weapon, balloon, pillow and similar meshes. `VARIANT_WORDS` excludes
   `ui`, `static_ui`, `eyes_closed`, `no_shirt`, `no_sim`, `nosim`, `proxy` and
   `bindpose` variants so a body group does not appear three times.
3. **PulseSrcOps' empty-modifier bug is contained.** `source2.import_dmx` wraps
   only the corrective-shape driver call, restores the original classmethod, and
   does not change the importer's data. This is the reason the Familiar head can
   be imported at all on Blender 5.4.
4. **Tail sources are broader than the current two rigs.** `tailops.discover`
   collects chains from the imported hero, the custom rig, one representative
   skeleton per hero in sibling S2V extractions, and an optional user folder.
   It prefers a declared body over a clip with the same hero key.
5. **Clip scanning does not need an import.** `forge.tails.dmx_bone_names` reads
   the binary DMX header, groups numbered chains with `tails.chains`, and excludes
   `weapon_target_tail` from discovery. A clip the importer cannot open still gets
   a named tile rather than disappearing.
6. **The selector is visual and Popit-shaped.** The Tails page has one title card,
   uppercase micro groups, glyph actions, a two-column tile grid with a generated
   chain preview per tile, a selected alert tile, and one message bubble. Selecting
   a tile loads that skeleton as `settings.tail_armature` and maps the hero
   channels. A tile can be loaded before the hero is imported; mapping then waits.
7. **The preview is geometry, not an icon guess.** `forge.tailimage` projects the
   chain's head/tail positions onto the two axes with the most spread and writes a
   transparent PNG with the standard library. `tailpreview` loads those images as
   Blender preview icons.

## Evidence

- `python tools/project.py gate`: unit tests, compileall, no KV3 parser, no vmdl
  writes, blake3 dependency — all pass.
- `artifacts/probes/familiar_import.py`: `dmf.import_hero` on Familiar with the
  head saved as body returned `FINISHED`, repaired `settings.body_dmx` to
  `familiar_wip_8inf_body8.dmx`, and produced 195 bones / 17,245 vertices plus
  balloon, clothes, head, pillow and weapon parts.
- `artifacts/probes/tail_discover.py`: 2 Familiar tail chains discovered from the
  body, both PNG previews written; 3 roots scanned; 1 representative opened.
- `artifacts/probes/tail_load.py`: selecting the `tail` tile produced
  `DMF Tail tail` with 195 bones and mapped 18 hero channels.
- `tools/blender_tail_ui_probe.py`: 6/6, with the Tails page drawn against a real
  `UILayout`; receipt `artifacts/receipts/tail-ui.json`, screenshot
  `artifacts/receipts/tail-ui.png`.
- Not checked: a tail rig from a hero outside the three local extractions; a real
  click on a tile; an in-game tail render; an older non-DMX custom model.
