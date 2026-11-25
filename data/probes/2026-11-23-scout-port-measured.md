# 2026-11-23 — what the second pass actually measured on the Scout port

The first record established the tool and its Popit surface. This one is the readings the tool produced
against the machine, and the two refusals that are the real state of the port.

## Staged, verbatim

`python tools/scout_update.py stage --workspace F:/Documents --hero frank --graph <dota graph> --out artifacts/scout-update/stage`
copied the port's own `heroes.vdata` (2,242,348 bytes, 63 hero entries) with `verbatim: true` and its BLAKE3
`bf6147c3328a84af…` checked against the source after the copy. The staged graph is the Dota
`biped_standard.vanmgrph` (`animgraph19`, 164 nodes, 24 sequence names), digest `c74bc274b9d2abb8…`.

The hero was **declared** (`--hero frank`), not inferred: `frank` is the only hero model in the port
workspace, and the staged manifest records that the port carries `frank.vmdl_c` and no source `.vmdl`
(`"source": false`). The tool refuses `hero-not-declared` without that flag.

## The join the bake needs, measured on both sides

| Graph sequences | Against the port's animation SMDs | Against the live Frank clips |
|---|---|---|
| 24 (`walkn`, `crouch_walkne`, `turn_left_90`, `idle`, …) | **0 bound** (1,414 SMD, named `@…_corrective_animation`) | **0 bound** (132 animation DMX, named `weapon_run_n`, `aim_crouch`, …) |

So the Dota graph's sequence names are neither the TF2 port's names nor Deadlock's own clip names. The bake is
first an **authoring** task: the graph must name the clips the model actually declares, or the model must be
given sequences with those names. The tool reports both sides and refuses `animgraph-sequence-unbound` instead
of inventing a synonym table.

## The compile chain, end to end

- Port graph → Dota toolchain: `biped_standard.vanmgrph` → `biped_standard.vanmgrph_c`, **62,191 bytes**,
  `OK: 1 compiled, 0 failed`, with the graph's own `biped_standard.vmdl` under the addon root
  (`models/biped_standard/`) — the addon root is the content root the compiler resolves against.
- Reduced CSDK13: every graph fails with `FS: Tried to FileExists NULL filename`; its `game/bin/win64` carries
  `-animationsystem.dll` **disabled**. The owner's direction holds: the animgraph editor and its compiler come
  from the Dota tools tree, not the reduced CSDK.
- `game/bin` is load-bearing. Extracting only `content/dota_addons/animgraph/` leaves the compiler a
  `binlaunch` wrapper with no `game/bin` above it; the extraction now keeps `game/bin/`, `game/dota/gameinfo.gi`
  and the animgraph content (278 files, 588,314,380 bytes).

## Not checked

- The retarget of a Deadlock *variation* document: no verified DMX skeleton for Frank sits in the extraction
  (S2V's model dump emitted 150 clips and no skeleton), so `animgraph` was not run against an invented path.
- In game. No launch.
