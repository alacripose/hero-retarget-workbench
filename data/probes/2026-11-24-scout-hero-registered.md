# 2026-11-24 — `hero_scout` registered in the port's hero table, compiled, and resolved in the installed addon

The installed addon now carries a hero entry of its own. `hero_scout` is authored into the port's
`F:/Documents/heroes.vdata` (backup `F:/Documents/heroes.pre-scout`), compiled with CSDK 13's
`resourcecompiler` to `scripts/heroes.vdata_c`, shipped inside `game/citadel_addons/scout_port/`, and read
back out of the compiled bytes with Source 2 Viewer. Nothing here is observed in game.

## The entry

A clone of `hero_frank` — the dev hero whose abilities, item slots, stats, shop and portrait maps the
engine resolves by name — with only identity, body and hero graph changed:

| field | value |
| --- | --- |
| block | `hero_scout` (68 → 69 hero blocks) |
| `m_HeroID` | **89** (free: the table's ids ran to 88) |
| `m_strModelName` | `resource_name:"models/heroes_wip/scout/scout_body.vmdl"` |
| `m_sAG2VariationName` | `resource_name:"models/heroes_wip/scout/scout.vnmgraph"` — the field released heroes use for their hero graph |
| search/sort/tags | `#hero_scout_search`, `#hero_scout_sort`, `#Citadel_Scout_HeroTag_{1..3}` |
| kept from the template | abilities, item slots, level info, starting stats, shop/portrait/icon maps |

The block is 41,656 bytes. `m_sAG2VariationName` was absent on `hero_frank`; it is inserted after
`m_strModelName` with the same `resource_name:` spelling the released heroes carry.

## The compile, and the read-back

```
cd <csdk>/content
resourcecompiler.exe -nop4 -f -game <csdk>/game/citadel -i <csdk>/content/citadel_addons/scout_port/scripts/heroes.vdata
OK: 1 compiled, 0 failed, 0 skipped
```

- compiled `scripts/heroes.vdata_c` — **89,695 B**, md5 `7e7814698aef972a6e3c00097a5341f7` (the
  unmodified table compiles to 89,448 B through the same command, so the tool was exercised before the
  entry was added).
- **The compiled bytes carry the entry.** Source 2 Viewer decompiles the installed
  `D:\...\citadel_addons\scout_port\scripts\heroes.vdata_c` back to 2,612,838 B of text and the
  `hero_scout` block is there: `m_HeroID = 89`,
  `models/heroes_wip/scout/scout_body.vmdl`, `models/heroes_wip/scout/scout.vnmgraph`
  (`artifacts/scout-hero/installed-readback/heroes.vdata`).

## The entry resolves against the installed copy

`tools/scout_install.py install` re-registers (idempotent: an existing `hero_scout` is read, not
rewritten), compiles the table, copies **42 files / 16,040,702 B** into the live addon, and resolves every
path the entry names:

| named by the entry | compiled file expected | present in `game/citadel_addons/scout_port/` |
| --- | --- | --- |
| `models/heroes_wip/scout/scout_body.vmdl` | `…/scout_body.vmdl_c` | yes, 107,209 B |
| `models/heroes_wip/scout/scout.vnmgraph` | `…/scout.vnmgraph_c` | yes, 2,512 B, md5 equals the compiled graph |

- Installed table md5 equals the compiled table md5 (the receipt checks both).
- The installed graph is the same one verified separately: `tools/scout_graph.py verify --csdk
  D:/SteamLibrary/steamapps/common/Deadlock` → **PASS**, four clips at 78 channels, motion and aim states,
  skeleton named, 78 bones, 0 frank references.
- VPK: **42 entries, 16,042,604 B**, read back 42/42 with no missing and no extra.

## Receipts and probes

- `artifacts/receipts/scout-install.json` — `files` (42, md5 each), `vpk`, and a `hero` block with the
  authored entry, the table compile result, the decompiled entry, the resolved paths and
  `graph_matches_compiled: true`.
- `artifacts/receipts/scout-install-probe.json` — **6/6**: page served, pack step pass, pack counts,
  VPK read-back, hero step pass, hero paths resolve.
- `artifacts/receipts/scout-port-app-probe.json` — **13/13**: the new `hero-registered` check requires the
  hero step `pass` with every path resolved and the graph md5 matching; `downstream-refused` now only
  requires `in_game` to be refused, and it is.
- `python -m pytest -q` — **415 passed** (`tests/test_scout_port_app.py` asserts the hero step passes with
  `resolved == paths` and `graph_matches_compiled`, not `hero-not-registered`).
- `heredoc_audit` pass; `agents_audit --index` 7/7.

## Not observed, plainly

**In-game selection and playback were not observed.** No game session was launched, and a hero table
entry plus its loaded files is not evidence that the roster shows Scout or that his clips play. That
remains `not-observed` in the app and in this record.

## Kept

The superseded frank-bound `game/citadel_addons/scout_animgraph/` and its VPK are untouched; the app lists
them under `superseded`. The port's pre-registration table is `F:/Documents/heroes.pre-scout` (the earlier
roster backup `heroes.vdata.pre-update` is also still there).
