# Scout's UI assets, and whether the hero graph field takes a standalone graph

Date: 2026-11-24. Command run: `python tools/scout_ui.py build`, `python tools/scout_install.py install`,
`python tools/scout_install.py probe`, `python popit_apps/scout_port/probe.py`, `python -m pytest -q`.

## What the entry named before

`hero_scout` was cloned from `hero_frank` and kept every UI field Frank had:

| field | before | now |
| --- | --- | --- |
| `m_strUIShoppingMap` | `maps/ui/hero_shop/frank_shop.vmap` | `maps/ui/hero_shop/default_shop.vmap` |
| `m_strUITeamRevealMap` | `maps/ui/team_reveal_hero/frank_team_reveal.vmap` | `maps/ui/team_reveal_hero/default_team_reveal.vmap` |
| `m_strUIPostgamePortraitMap` | `maps/ui/hero_postgame_portrait/frank_postgame_portrait.vmap` | `maps/ui/hero_postgame_portrait/default_postgame_portrait.vmap` |
| `m_strIconImageSmall` | `file://{images}/heroes/frank_sm.psd` | `file://{images}/heroes/scout_sm.psd` |
| `m_strMinimapImage` | `file://{images}/heroes/frank_mm.psd` | `file://{images}/heroes/scout_sm.psd` |
| `m_strIconHeroCard` | `file://{images}/heroes/frank_card.psd` | `file://{images}/heroes/scout_card.psd` |
| `m_strIconHeroCardCritical` | `file://{images}/heroes/frank_card_critical.psd` | `file://{images}/heroes/scout_card.psd` |
| `m_strIconHeroCardGloat` | `file://{images}/heroes/frank_card_gloat.psd` | `file://{images}/heroes/scout_card.psd` |
| `m_strTopBarVertical` | `file://{images}/heroes/frank_vertical.psd` | `file://{images}/heroes/scout_vertical.psd` |
| `m_strUIPortraitMap` | `maps/ui/hero_prefabs/frank.vmap` | dropped |
| `m_strLogoImageEnglish` / `…Localized` | `file://{images}/heroes/hero_names/victor*.svg` | dropped |

The two drops follow the shipped table: 14 of 69 hero blocks carry no `m_strUIPortraitMap` and 23 carry
no logo images. The three maps are the defaults 13 shipped entries already name; no new map was authored,
and no map is claimed to be Scout art.

## The images

Three Scout images were authored as placeholders (generated art, 1392x752 card, 1024x1024 portrait,
752x1392 vertical; it is placeholder art for a port, not extracted TF2 UI art) and compiled by the CSDK 13
compiler. The compiler has **no direct image compiler** — `-i …\scout_sm.png` refuses with
`Failed to find compiler for file "…scout_sm.png"` — so each image is compiled through a one-texture
`.vmat`, the same route the port's 15 material textures take.

| image | compiled | installed panorama |
| --- | --- | --- |
| `scout_sm` | 1,400,244 B | `panorama/images/heroes/scout_sm_psd.vtex_c` |
| `scout_card` | 1,398,612 B | `panorama/images/heroes/scout_card_psd.vtex_c` |
| `scout_vertical` | 1,398,612 B | `panorama/images/heroes/scout_vertical_psd.vtex_c` |

The `_psd.vtex_c` name is the shipped convention, not an invention: `panorama/images/heroes/frank_sm_psd.vtex_c`
is 67,636 B in `pak01_dir.vpk` (plus a 23,956 B hashed twin), i.e. the `_psd` name holds a full compiled
texture. Each of the three installed files was decompiled by Source 2 Viewer
(`artifacts/scout-hero/ui-verify/…`), 630,642 / 939,115 / 871,220 B back out.

## The install

`hero_scout`'s block is now 41,414 B (was 41,656 B: the replaced values are shorter and two fields are
gone). The compiled table is 89,798 B and was decompiled to read the block back: six Scout image fields,
three default maps, model and graph unchanged, none of the dropped fields present.

The addon is now **45 files, 20,238,273 B** (was 42 / 16,040,702 B); VPK
`artifacts/scout-update/vpk/scout_port_dir.vpk` **45 entries, 20,240,300 B**, read back 45/45. The
installed graph still verifies: PASS, 4 clips × 78 channels, 78 bones, no Frank reference.

`tools/scout_install.py probe` is **7/7** (new `hero-ui-resolve`); the app probe is **14/14** (new
`ag2-binding-named`); `pytest -q` is **415 passed**.

## The graph field question

`m_sAG2VariationName` occurs in **3** of the table's 69 hero blocks:

| entry | value |
| --- | --- |
| `hero_vampirebat` | `animgraphs/animgraph2/hero/hero.vnmgraph+vampirebat.vnmgraph` |
| `hero_necro` | `animgraphs/animgraph2/hero/hero.vnmgraph+vampirebat.vnmgraph` |
| `hero_scout` | `models/heroes_wip/scout/scout.vnmgraph` |

The other **66** heroes set no such field. Both shipped entries that set it name a
`hero.vnmgraph+<hero>.vnmgraph` variation; no shipped entry names a standalone graph. The tool branch's
`game/citadel/animgraphs/animgraph2/hero/` holds **51** `hero.vnmgraph+*.vnmgraph_c` variations and **26**
standalone `*.vnmgraph_c` graphs — the standalone ones are auxiliary graphs (`*_abilitymask`,
`*_loco_set_*`, `*_upperbodyreplace`, `*_event_id`), and no hero entry names one.

Decompiling both forms (Source 2 Viewer):

| document | bytes | `m_nodes` | `m_overrides` | `m_variationHierarchy` |
| --- | --- | --- | --- | --- |
| `hero.vnmgraph+abrams.vnmgraph_c` | 210,364 | 37 | 17 | 1 |
| installed `scout.vnmgraph_c` | 30,255 | 12 | 4 | 1 |

Both decompile as complete graph documents, so `hero.vnmgraph+<hero>.vnmgraph` is a full hero graph
selected through its `+` family name, not a small delta over a base. A binary string scan of the live
`client.dll`/`server.dll`/`animationsystem.dll` finds no `m_sAG2VariationName` and no `hero.vnmgraph`
literal, so the field is data-driven and its exact acceptance cannot be settled by inspection; only one
`.vnmgraph` literal exists in `client.dll`.

**Conclusion.** The observed contract for this field is a `hero.vnmgraph+scout.vnmgraph` hero variation.
A standalone `.vnmgraph` is not observed being accepted there, and nothing here proves it would load. The
entry keeps naming the authored standalone graph — it is the port's only graph — and the install receipt,
the app's hero step and the app probe all name that as **unverified** (`ag2-hero-variation-required`),
rather than claiming it plays. Producing an accepted `hero.vnmgraph+scout.vnmgraph` is not a rename: the
shipped hero graphs carry 37 nodes and 17 overrides over locomotion/ability clips, while the port has four
baked clips (attack, reload, aim idle, aim run) and 12 authored nodes; that retarget is the remaining work.

## Not observed

No game session was launched. Icon/card rendering, map prefabs, roster selection and clip playback in
game are **not observed**; the app step for that remains `not-observed`.
