# 2026-11-23 — the bake: a Scout variation in the hero aim graph, compiled

The third pass. The port's hero table is on main, and the animations are in a graph the toolchain
builds. What is **not** done is the clip data itself, and this record says exactly where that line is.

## What the live build's graphs are

`Source2Viewer-CLI -d` on `animgraphs/animgraph2/hero/hero.vnmgraph+frank.vnmgraph_c` (7,252 bytes
compiled) gives a **fused** `CNmGraphDocument` (210,346 bytes of text): not a variation file beside a
base, but one document holding every hero. `hero_aim.vnmgraph_c` (20,234 bytes) decompiles to
**932,528 bytes** of the same, naming **140** heroes.

Three schemas now, and each is what it says it is:

| Schema | Header | Where |
|---|---|---|
| `animgraph19` | `format:animgraph19` | the Dota 2 tools branch (`content/dota_addons/animgraph/…/biped_standard.vanmgrph`) |
| variation | `m_variationID` + `m_skeleton` as a resource | the Kelvin document in the port workspace |
| `CNmGraphDocument` | `format:generic`, `m_pRootGraph` | **what the live build ships**, fused |

## Why a file beside the base compiles nothing

`hero_aim.vnmgraph+scout.vnmgraph` placed next to the base compiled **142** graphs and no Scout: the
base's variation list is `m_variationHierarchy.m_variations` (`m_ID`, `m_parentID`, `m_skeleton`), and
`+<hero>` files are *outputs*, not inputs. Likewise the compiler refuses a `+` file as input:
`Non-fused-child compiles cannot contain fused delimiter '+'`.

Adding a hero to the fused document is two edits, both mechanical and both checked here:

1. **One override per animation-pose node.** Every pose node carries `m_overrides`, an array of
   `{ m_variationID, m_pData { m_clip } }` — one entry per hero. The document has **18 pose nodes**,
   all 18 with overrides; Scout got 18 cloned entries with its clip path moved to
   `models/heroes_wip/frank/clips/`.
2. **One entry in the variation hierarchy**, or the overrides are data no variation selects.

Result: `hero_aim_scout.vnmgraph` (965,957 bytes) → **143 compiled, 0 failed**, and
`hero_aim_scout.vnmgraph+scout.vnmgraph_c` (**5,475 bytes**) exists. Compile receipt:
`artifacts/receipts/scout-variation-Scout.json`.

## The other graph, from the Dota branch proper

`scout_loco.vanmgrph` is the Dota `biped_standard` template with its 24 sequence slots renamed to the
port's own `$sequence` names (**379** declared by the port's QC), bound to
`models/heroes_wip/frank/frank.vmdl`, and compiled: **28,482 bytes**, 1 compiled, 0 failed, with
`StrideR: Failed to find foot with name "Foot_Left"` on the way — the template's rig is not the hero's.

Two things this cost, both learned the hard way and now refusal codes:

- The Dota compiler **cannot read the live game's content**: `-game …/Deadlock/game/citadel` fails on
  every document with `Failed to read 1437209140 bytes`. Compiling goes through a Citadel content tree
  the compiler can read (`Reduced_CSDK_13`), with the graph's model under the addon root.
- The compiler writes compiled output under `game/citadel_addons/…`, not beside the source; a receipt
  that looks only beside the source reports a pass as a failure.

## The line that is not crossed

The 18 Scout override clips point at `models/heroes_wip/frank/clips/<name>.vnmclip`, files that do not
exist yet, and the compiler does not check clip existence — so this is a **compiled graph whose Scout
clips are named but absent**. Producing them is the remaining work:

- Scout's animation source is 1,414 SMDs of TF2 `@…_corrective_animation` additive layers, against a
  Frank skeleton they were never built for.
- Frank's live clip set is 132 DMX; the graph's six aim poses use `aim_weapon_idle*` / `aim_crouch*`,
  which exist.
- So each Scout clip is: SMD → DMX on `frank.vnmskel` (rebased to the shipped joint order), then a
  `.vnmclip` doc with `m_sourceFilename` at that DMX. `tools/clip_rebase_to_skeleton.py` and the DMX
  tail tooling do the rebase step; the SMD→DMX conversion does not exist here yet.

## Evidence

- `artifacts/scout-update/animgraph/`: `hero_aim_scout.vnmgraph`, `hero_aim_scout.vnmgraph_c`,
  `hero_aim_scout.vnmgraph+scout.vnmgraph_c`, `scout_loco.vanmgrph`, `scout_loco.vanmgrph_c`
- `logs/scout-variation-hero_aim_scout.log` (143 compiled), `logs/scout-graph-scout_loco.log`
- `artifacts/scout-update/live-graphs/` — the decompiled live base and Frank variation
- `artifacts/receipts/scout-variation-Scout.json`, `scout-graph-scout_loco.json`,
  `scout-animgraph-hero_aim.vnmgraph+scout.json`, `scout-update-hero-table.json`

## Not checked

- In game: nothing was launched.
- The compiled variation was not loaded by the live build (no addon VPK exists on this machine to load
  it from).
- Clip playback: the referenced clips are absent, by design, and named in the receipt.
