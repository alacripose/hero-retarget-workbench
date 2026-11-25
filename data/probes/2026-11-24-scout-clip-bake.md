# 2026-11-24 — the Scout clips exist, compile, and mount

The fourth slice of TICKET-0037 closes the gap the third slice named: every clip reference in both
graphs now resolves to a generated clip document, the documents compile into `_c` resources that carry
the Frank skeleton, and the compiled set rides in an addon VPK that reads back.

## What was asked, and what was measured

| Asked | Measured |
|---|---|
| how many clips exist | **36** generated clips, `artifacts/scout-update/clips/vnmclip`, 7,368,484 bytes of binary DMX |
| how many the graphs reference | **36** references — 24 locomotion slots + 12 aim clip paths, 36 **distinct** names, 0 missing |
| reconcile the shortfall | none: `plan` reports `rows 36, missing 0`; the 36 references come from **24** Scout sequences, so 12 names share a source pose by design |
| compile both graphs | `hero_aim_scout.vnmgraph` → **143 compiled, 0 failed** (142 variation outputs); `scout_loco.vanmgrph` → 28,481 B |
| prove references resolve to real keyframes | 36/36 `.vnmclip_c` compiled, 36 distinct md5s, **520 animated quaternion channels**, **39,962 samples** |

## Why the first compile looked green and was not

`resourcecompiler` answers `ERROR: 0 compiled, 0 failed, 0 skipped` for a relative `-i` path — no error
word a caller greps for, and no output. It needs an **absolute** path with the working directory at the
content root, exactly as `forge/animgraph.py` does. Three further facts had to be true before the clip
would compile:

1. **The skeleton has to compile first.** With `frank.vnmskel` present the compiler says
   `Invalid skeleton file: models\heroes_wip\frank\frank.vnmskel`; the fix is the decompiled skeleton plus
   its `dmx/mesh/frank_skel.dmx` beside the clips, and then the skeleton itself compiles
   (`OK: 1 compiled`, 9,203 B) against the shipped `frank.vnmskel_c` (9,142 B).
2. **Output does not land beside the source.** It lands at
   `<csdk>/game/citadel_addons/scout_animgraph/<mirror>/<name lower-cased>_c`. The receipt records that
   path; a check that looks beside the document reports 0/36 while the compiler reported success.
3. **The pack needs the DMX.** The compiled clip is a `CNmClipDocument` that *names* its DMX; the
   decompile of a `_c` writes the document back at 394 bytes and cannot produce the animation itself, so
   the 36 DMX are packed with the clips.

Decompiled back, a clip reads:

```
_class = "CNmClipDocument"
m_sourceFilename = "models/heroes_wip/frank/dmx/animation/aim_weapon_crouch.dmx"
m_animationSkeletonName = "models/heroes_wip/frank/frank.vnmskel"
```

## Joint binding, by name not by index

Every clip writes 54 of the 76 SMD nodes onto **54 Frank joints** through an explicit `BONE_MAP`; the 22
unmapped nodes are named in the report (`weapon_bone_1..4`, `weapon_bone_L`, `medal_bone`, `mvm`,
`effect_hand_L/R`, the dogtag and pack chains, the prop chains) and never guessed onto a joint. Rotations
are converted (SMD Euler radians → quaternion); positions keep the template's values because the rigs have
different bone lengths.

## The pack

`artifacts/scout-update/vpk/scout_animgraph_dir.vpk` — VPK **version 2**, 76 entries, 7,594,282 bytes of
payload, 7,597,467 bytes on disk:

- `animgraphs/hero_aim_scout.vnmgraph_c` (16,922 B) and **`animgraphs/hero_aim_scout.vnmgraph+scout.vnmgraph_c`** (5,667 B)
- `animgraphs/scout_loco.vanmgrph_c` (28,481 B)
- `models/heroes_wip/frank/frank.vnmskel_c`
- 36 `models/heroes_wip/frank/clips/*.vnmclip_c`
- 36 `models/heroes_wip/frank/dmx/animation/*.dmx`

Read back two ways: `forge.oldmods.read_vpk` reports 76/76 entries with no missing and no extra, and
Source 2 Viewer lists the tree and extracts the Scout variation, which decompiles to a
`CNmGraphDocument` naming `Scout` and 12 `models/heroes_wip/frank/clips/*.vnmclip` sources.

## What the graph does, and what was not seen

`deadlock.exe -tools …` (the flags in `game/bin/win64/deadlock with Tools.bat`, launched directly because
the batch name does not survive Git Bash argument quoting) **starts** here: Steam init and breakpad lines
in `artifacts/scout-update/tools-launch.log`, `deadlock.exe` resident at 2.9 GB. It writes nothing further
to that log, and the game's own `citadel/console.log` on disk is from 2026-11-18 — it shows tools mode
loading a previous WIP hero's clips and failing each with
`ERROR_COMPILEFAIL: Tools mode - tried to (re)compile an asset but failed`, which is the failure mode the
compiled set above removes, not evidence about this one. The process was stopped after inspection.

So: **the tools build launches, and no Scout motion was observed.** Seeing the hero move needs a map
session with the Frank model spawned, which this slice did not drive.

## The link that is not claimed

The 12 aim references are `.vnmclip` paths in the variation and resolve to compiled `_c` files that exist.
The locomotion graph is `format:animgraph19`: its 24 slots carry **names** (`PRIMARY_aimmatrix_idle`,
`AttackStand_PRIMARY`, …), not clip paths, and an AG1 graph binds a sequence through the model's own
sequence table. Those 24 names equal 24 generated clip names exactly, and the port's QC declares them —
but a model declaring a sequence is a model-side fact this slice did not rebuild, so the loco half is
"named and generated", not "shown playing".

## Not checked

- No in-game visual of Scout moving, in any graph.
- No mount inside the game process; the VPK was mounted by the reader and by Source 2 Viewer, not by
  `citadel_addons` at runtime.
- The 22 unmapped TF2 nodes stay unmapped (reported, not silently dropped).
