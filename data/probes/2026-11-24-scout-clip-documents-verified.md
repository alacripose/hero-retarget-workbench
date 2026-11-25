# 2026-11-24 — Scout's four clips, read back from the compiled Deadlock documents

The animation half is finished as evidence, not as a build report: every clip is decompiled from its
compiled `vnmclip_c`, its DMX is converted with `dmxconvert`, and the counts below come from parsing
that file.

## The format, established the way the mesh format was

A shipped Dota 2 tool-branch animation document was converted to keyvalues2:

```
artifacts/dota-tools/content/dota_addons/animgraph/models/biped_standard/dmx/animation/idle.dmx
1,013,864 B → keyvalues2 4,310,919 B
308 channels: 154 `_p` (position) + 154 `_o` (orientation), 89 joints
classes: DmeChannelsClip, DmeChannel, DmeQuaternionLog/Layer, DmeVectorLog/Layer, DmeTimeFrame
```

So a Deadlock/Dota clip is **two channels per joint**, `_p` and `_o`, inside a `DmeChannelsClip` with a
`DmeTimeFrame`. Scout's clip template has the same element shape (`DmeChannelsClip` → `DmeChannel` →
`DmeQuaternionLog` → `DmeQuaternionLogLayer` with `times`/`values`), written by
`forge/portskel.write_clip_template` and filled by `forge/clipbake.bake_kv2`.

## The source sequences

`F:/Documents/scout.qc` declares the four: `PRIMARY_aimmatrix_idle` (line 832), `PRIMARY_aimmatrix_run`
(834), `AttackStand_PRIMARY` (838), `PRIMARY_reload_loop` (852). The SMDs those declarations name are
the extracted animation data of the port's `scout.mdl`; `tools/scout_own_clips.py` baked them into four
keyvalues2 animation DMXs (67,200 / 65,640 / 37,560 / 37,560 B), which `dmxconvert` turned into the binary
DMX each `CNmClipDocument` names.

## What the compiled documents parse to

| clip | compiled `vnmclip_c` | document | channels | joints | frames | duration |
| --- | --- | --- | --- | --- | --- | --- |
| `Scout_Attack` | 4,096 B | 381 B | **156** (78 `_p` + 78 `_o`) | 78/78 | **21** | 0.6667 s |
| `Scout_Reload` | 4,099 B | 381 B | 156 (78/78) | 78/78 | **20** | 0.6332 s |
| `Scout_AimIdle` | 4,096 B | 384 B | 156 (78/78) | 78/78 | **2** | 0.0332 s |
| `Scout_AimRun` | 4,096 B | 383 B | 156 (78/78) | 78/78 | **2** | 0.0332 s |

The joint names on the tracks are exactly the skeleton's 78 (`bip_pelvis` … in the port's order), and the
documents name `models/heroes_wip/scout/dmx/<sequence>.dmx` and
`models/heroes_wip/scout/scout.vnmskel`.

**What the authored documents hold.** The port's clip DMXs carry one orientation channel per joint (78
`_o`); the compiler samples them into the shipped two-track layout, so the compiled documents have 156.
Scout's clips are skeletal rotations, and the source sequences carry translation on two bones, which is
now baked (see the motion section below).

## The graph reaches all four

`scout.vnmgraph_c` 2,512 B, decompiled to 30,255 B of text: **25 nodes**, **4 clip references** —
`models/heroes_wip/scout/clips/scout_attack.vnmclip`, `…/scout_reload.vnmclip`, `…/scout_aimidle.vnmclip`,
`…/scout_aimrun.vnmclip` — inside the named states `state_Scout_Attack`, `state_Scout_Reload` and
`aim_state_Scout_AimIdle`, `aim_state_Scout_AimRun`, with skeleton
`models/heroes_wip/scout/scout.vnmskel` and **0** `frank` references.

## End-to-end compile

`tools/scout_anim.py` runs the port's graph compiler (skeleton, 4 clips, graph) and then the mesh model
and all 15 materials with CSDK 13's `resourcecompiler`:

- **21/21 documents, 0 failed**: `scout.vnmskel_c`, four `*.vnmclip_c`, `scout.vnmgraph_c`,
  `scout_body.vmdl_c` (**107,209 B**), 15 `*.vmat_c`.
- The mesh path decision is untouched: the model still names `heroes_wip/scout/dmx/mesh/scout_body.dmx`
  and compiles without warnings.

## App, probe, tests

`clips_state` no longer reads the bake's own receipt: it reads `artifacts/scout-anim/parsed/<clip>.json`,
the counts `tools/scout_anim.py` parsed out of each compiled document, and reports `pass` only when all
four parse with 156 tracks and 78 joints; a partly-parsed set is `clips-partial` with the missing clip
named, and nothing parsed is `clips-not-converted`. `graph_state` prefers the clip references parsed from
the decompiled graph.

Live: `clips pass — 4/4 clips parsed, 156 channel tracks (78 joints x position+orientation), frames
21/20/2/2`; `graph pass — 2512 B compiled graph, 4 clip references from sequence/pose nodes, 2 motion
states, 2 aim states, 78 joints`; `mesh converted` unchanged. Probe **12/12**, suite **411 passed**,
`heredoc_audit` pass.

## Motion measured, per channel, from both ends (2026-11-24, later)

`tools/scout_variance.py` converts each **animation document the clip names** back with `dmxconvert`,
parses every channel's times/values, and measures samples, distinct values (1e-4 tolerance) and spread;
the same is measured on the sequence's own SMD (orientation angle in degrees, translation distance in
units). Writes `artifacts/scout-anim/variance/<clip>.json` and merges a summary into
`artifacts/scout-anim/parsed/<clip>.json`.

| clip | source frames | document samples | moving orientation | moving position | flat where source moves |
| --- | --- | --- | --- | --- | --- |
| `Scout_Attack` | 21 | 21 | **22/78** | **2/78** | **0** |
| `Scout_Reload` | 20 | 20 | **28/78** | **2/78** | **0** |
| `Scout_AimIdle` | **1** | 2 | 0/78 | 0/78 | 0 |
| `Scout_AimRun` | **1** | 2 | 0/78 | 0/78 | 0 |

- **The aim clips are genuinely single-pose.** Their source SMDs contain **one skeleton frame**, zero
  moving joints and zero translating joints (`PRIMARY_aimmatrix_idle`, `PRIMARY_aimmatrix_run`); the two
  samples in the document are that pose duplicated, so the flat channels agree with the source rather
  than proving truncation. They are kept as-is.
- **The two motion clips move where their source moves, and only there.** Every joint that moves in the
  source SMD has a moving orientation channel in the document (22 and 28), and no joint is flat where
  the source moves.
- **Translation is now carried.** The source translates `bip_pelvis` (0.456 units in AttackStand, 0.165
  in reload) and `weapon_bone` (0.361 / 4.680); the bake wrote orientation only, so those were held.
  `forge.portskel.write_clip_template` now emits a `_p` position channel per joint (rest from the
  skeleton's local positions) and `forge.clipbake.bake_kv2` writes the source translation delta onto it.
  Both clips now show 2/78 moving position channels, at the bones the source moves. DMX sizes rose from
  67,200 / 65,640 / 37,560 / 37,560 B to **114,814 / 112,006 / 61,462 / 61,462 B**.
- **The compiled `vnmclip_c` is a reference, not the samples.** It is 4,096–4,099 B. Changing one
  quaternion in the source DMX and recompiling moves exactly **4 bytes (offset 905–908)** of the compiled
  clip — a checksum. Source2Viewer's own DMX re-export of a compiled clip is a 117,366 B rest-pose
  reconstruction (all 156 channels, identity/rest values, no dependence on the authored samples), so it
  is not evidence of what a clip plays. The animation document the clip names, with the checksum, is.

After the fix: the clips, skeleton and graph recompiled **21/21, 0 failed**; graph 2,512 B with **4 clip
references** across its sequence/pose states and 78 joints; `scout_body.vmdl_c` 107,209 B from
`heroes_wip/scout/dmx/mesh/scout_body.dmx`; **413 tests**, probe **12/12**.

## The source numbers beside the measured ones (2026-11-24, later)

Frame counts are now read from the model's own sequence descriptors, not only from the decompiled SMDs.
`forge/mdlseq.py` decodes `F:/Documents/scout_animations.mdl` (5,017,436 B, md5
`74950ba0453e9ef71fa1a32a840573ac`): 377-entry sequence table at 4,841,760, stride **212** (validated by
the first entry's `count × 212` field and the table's exact end), label at entry + `i32(+4)`, activity at
entry + `i32(+8)`, flags +12, numblends +56, anim-index block at entry + `i32(+60)`; anim descriptions at
17,508 × 1,012, stride 100, name +4, fps +8, frames +16. Every field sits 4 bytes after the published
`mstudioseqdesc_t` — the published offsets are why the earlier probes read zeros.

| clip | sequence | descriptor | activity | blends/cells | declared frames | SMD frames | document samples | moving orientation | moving position |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `Scout_Attack` | `AttackStand_PRIMARY` | 4,843,032 | `ACT_MP_ATTACK_STAND_PRIMARY` | 1 / 1 | **21** | 21 | 21 | 22/78 | 2/78 |
| `Scout_Reload` | `PRIMARY_reload_loop` | 4,844,516 | `ACT_MP_RELOAD_STAND_PRIMARY_LOOP` | 1 / 1 | **20** | 20 | 20 | 28/78 | 2/78 |
| `Scout_AimIdle` | `PRIMARY_aimmatrix_idle` | 4,842,396 | — | 12 / 12 | **1** | 1 | 2 | 0/78 | 0/78 |
| `Scout_AimRun` | `PRIMARY_aimmatrix_run` | 4,842,608 | — | 12 / 12 | **1** | 1 | 2 | 0/78 | 0/78 |

- **The aim clips are single-pose in the model, not truncated here.** Each is twelve aim-matrix cells of
  **one frame at 30 fps** (flags 1044), named `a_PRIMARY_aimmatrix_{idle,run}_straight_up` ×3 then
  `_up_right` … `_down_left` in exactly the order the QC's `$sequence` lists them. The two document
  samples are that pose duplicated.
- **`scout.mdl` names the sequences but carries no frames for them** (306-entry table, `numblends 0`,
  flags 2048, 2 anim descriptions). The data is in the animations companion — the file Crowbar 0.74
  decompiled into `scout_animations.qc` (line 1: `// Created by Crowbar 0.74`) and 1,412 SMDs in
  `scout_animations_anims/`; the QC's `$sequence "AttackStand_PRIMARY"` names
  `scout_animations_anims\AttackStand_PRIMARY.smd` and the same activity the descriptor declares. The MDL
  anim name `@AttackStand_PRIMARY`, the QC sequence and the SMD filename agree at every step.
- **The per-bone RLE payload did not decode.** Each anim description's +56 points into data that is not
  the published `mstudioanim_t` (first int 9,313,280 for AttackStand, past the 5 MB file; the anim block
  table is empty), so this note makes no per-bone claim from it — that block, its offsets and bytes, and
  the full provenance chain are recorded in `data/probes/2026-11-24-scout-mdl-source-frames.md`.
- **Effect on the artifacts:** `artifacts/scout-anim/variance/*.json`, `parsed/*.json` and
  `artifacts/receipts/scout-anim.json` now carry `mdl`/`mdl_declared_frames`/`mdl_activity` beside
  `source_frames` and the per-channel variance; the model, its bytes and md5 are in
  `variance.source_model`. All four still `ok=True` (declared frames and single-pose declaration agree
  with the SMD).

## Not done

- No VPK pack, no hero registration, no launch: `pack-not-built`, `hero-not-registered`, `not-observed`.
- No in-game playback; the clips are validated as compiled documents, not as motion seen on screen.
- Position tracks are compiler-synthesised holds, not authored translation.
