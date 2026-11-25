# 2026-11-24 — Scout's port installed into the live addon folder, and read back from there

The port's compiled set had only ever been read out of the forge's CSDK mirror. This slice puts it where
the game loads addons from and verifies the copy that is actually on disk there.

## What went in

`python tools/scout_install.py install` — **41 files, 15,951,007 bytes**, installed to
`D:\SteamLibrary\steamapps\common\Deadlock\game\citadel_addons\scout_port\`, and packed to
`artifacts/scout-update/vpk/scout_port_dir.vpk` (VPK v2, **41 entries, 15,952,866 bytes**, read back
41/41, no missing and no extra):

| group | files | bytes | where it came from |
| --- | ---: | ---: | --- |
| skeleton `scout.vnmskel_c` | 1 | 7,187 | `<csdk>/game/citadel_addons/scout_port/models/heroes_wip/scout/` |
| graph `scout.vnmgraph_c` | 1 | 2,512 | same |
| clips `scout_{attack,reload,aimidle,aimrun}.vnmclip_c` | 4 | 16,387 | same, `clips/` |
| animation DMX the clips name | 4 | 349,744 | same, `dmx/` (lower-case names the documents reference) |
| mesh model `scout_body.vmdl_c` | 1 | 107,209 | `<csdk>/game/models/heroes_wip/scout/` |
| materials `.vmat_c` + textures `.vtex_c` | 30 | 15,467,968 | same, `materials/` |

A compiled `vnmclip_c` is a reference plus a checksum, not the samples, so the four animation DMX ship
with the clips; the four materials' vtex carry the real Scout textures (five real, ten placeholder plates
as recorded for the mesh slice).

## Read back from the installed copy

- Every installed file was md5-compared with its staged source (`matches_staged` true for 41/41) and the
  receipt records the installed path, size and md5 per file: `artifacts/receipts/scout-install.json`.
- `python tools/scout_graph.py verify --csdk D:/SteamLibrary/steamapps/common/Deadlock` reads the graph
  **from the installed addon** (not the CSDK mirror): decompiled 30,255 B, `Scout_Attack`, `Scout_Reload`,
  `Scout_AimIdle`, `Scout_AimRun` all present with **78 channels** each, motion states
  `state_Scout_Attack`/`state_Scout_Reload`, aim states with pose nodes, skeleton named, **78 bones in the
  compiled skeleton**, **0 frank references** — `RESULT: PASS`.
- `python tools/scout_install.py probe` reads the app's own surface over loopback and requires the `pack`
  step to be `pass` with the receipt's counts: 4/4 checks (`pack-step-pass`, `pack-counts`,
  `vpk-read-back`), receipt `artifacts/receipts/scout-install-probe.json`.

## What the app says now

`popit_apps/scout_port/server.py` gained `pack_state()`: it reads the install receipt and re-checks that
every file it names still exists in the addon folder. The `pack` step is `pass` with
`41 files, 15,951,007 B, 4 clips, 4 DMX, 30 materials, VPK 41 entries` when the install is present and
falls back to `pack-not-built` when the receipt is absent or any file is gone. The probe's downstream
check now requires `pack pass` and still requires `hero` and `in_game` to be refused by name; it stays
**12/12**.

## Superseded, kept

`D:\...\game\citadel_addons\scout_animgraph\` (4 files, frank-bound: `frank.vnmskel`,
`PRIMARY_aimmatrix_idle.vnmclip`, its DMX and `frank_skel.dmx`) and
`artifacts/scout-update/vpk/scout_animgraph_dir.vpk` are left in place. The app names them under
`superseded`; nothing in this install reads them.

## Still refused, by name

- `hero-not-registered` — no entry in the port's hero table names a Scout model, so there is no hero
  binding to register; this install makes the assets loadable, not selectable.
- `not-observed` — nothing was launched into a map session; the earlier tools-mode launch stayed resident
  and showed no motion, so no in-game claim is made.

## Checks

- `python tools/scout_install.py install` — 41/41 installed, md5 read-back 41/41, VPK 41/41.
- `python tools/scout_graph.py verify --csdk D:/SteamLibrary/steamapps/common/Deadlock` — PASS (above).
- `python tools/scout_install.py probe` — 4/4; `python popit_apps/scout_port/probe.py` — 12/12.
- `python -m pytest -q` — **415 passed** (the live app test now asserts `pack pass`, not
  `pack-not-built`).
