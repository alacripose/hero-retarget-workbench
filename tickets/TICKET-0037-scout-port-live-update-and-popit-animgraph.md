# TICKET-0037 — the Scout port: a live-build update, a Dota-tools animgraph, and a Popit surface

**Status:** re-aimed by the owner on 2026-11-24: Scout is the port's own hero, not a rig relabel. The Popit-shell application passes its probe (12/12) with `skeleton pass`, `clips pass`, `graph pass` and `mesh converted`. The animation half is closed by parse: all four compiled clip documents decompile to 156 tracks (78 joints × position+orientation), the graph's compiled bytes name all four clips, and the port compiles 21/21 documents with 0 failures — including the mesh model and its 15 materials.
**Owner:** ala
**Opened:** 2026-11-23

## Requirement

The owner's requests, verbatim:

> using the deadlock model forge and family evidence, I' like you to update the scout mod for deadlock on
> my p, and then bake his animations into a custom animgraph made from the dota 2 tool branch

> the csdk13 runs on the dota tools so you could see about using it for the animgraph editor, the scout mod
> is an existing model port with its own hero scripts that needs to be updated to main deadlock

> you will have to create popit uis for the tools that you make this is a new requiremnt for the probes that
> you use to work

## What exists on this machine, read not assumed

| Thing | Where | Reading |
|---|---|---|
| The port | `F:/Documents` | `scout.qc`, `scout.mdl`, `scout_ANIM.mdl`, `scout_anims/`, `scout_animations_anims/` (1,414 SMD), its own `heroes.vdata` (2,242,348 bytes, **63** hero entries) |
| The live game | `D:/SteamLibrary/steamapps/common/Deadlock` | build read from `game/citadel/steam.inf`; roster extracted from `pak01_dir.vpk` through Source 2 Viewer |
| The Dota 2 tools branch | `F:/Downloaded Files/dota-0423lite_ship.zip` | 1,019,266,484 bytes, 13,876 entries; `content/dota_addons/animgraph/animgraphs/*.vanmgrph`, `game/bin/win64/tools/animgraph_editor.dll`, `animationsystem.dll`, `resourcecompiler.exe` |
| The reduced CSDK13 | `Downloads/Reduced_CSDK_13` | `game/bin/win64` carries `-animationsystem.dll` **disabled**; its compiler answers `FS: Tried to FileExists NULL filename` for any animgraph |

## What this slice builds

1. `forge/scout.py` — the port's sources, its hero-table snapshot and the live roster joined into a drift,
   the Dota tools tree read by compiler + graph directory, and AnimGraph documents read in **both** schemas:
   a Deadlock hero *variation* (`m_variationID` + `m_skeleton` + persistent indices) and the Dota authored
   document (`format:animgraph19`, nodes are `key =` blocks, no variation field).
2. `tools/scout_update.py` — `report`, `extract-dota`, `bind`, `stage`, `animgraph`, `serve`, `probe`.
3. `tools/scout_ui/` — the tool's **Popit** surface in the family web-dark register, and `probe` reads it over
   loopback HTTP. This is the new standing requirement: a tool ships its surface, and a probe fails unless the
   page renders the same run's report.
4. `tests/test_scout.py` — 15 tests over the roster scan, drift, both graph schemas, retarget refusals, the
   sequence join, Dota tools discovery and the Popit contract.

## Measured

- **Drift:** the port's `heroes.vdata` snapshot is stale against the live build: **6 heroes added, 2 gone,
  13 moved**. The drift is the "update to main Deadlock" signal; the mod's scripts are the older table.
- **Dota graph:** `biped_standard.vanmgrph` reads as `animgraph19`, **164 nodes**, **24 sequence names**.
- **Sequence join:** **0 of 24** graph sequences have a source animation in the port's animation folders
  (1,414 SMD named `@…_corrective_animation`), and **0 of 24** match the live Frank clip set either
  (132 DMX named `weapon_run_n`, `aim_crouch`, `dash_air_back`, …). The Dota graph's names exist on neither
  side, so the bake is first an authoring task: name the clips the model declares, or give the model the
  sequences the graph asks for. The tool reports both sides and refuses `animgraph-sequence-unbound`.
- **Stage:** `--hero frank` declared (the only hero model in the port workspace), the port's `heroes.vdata`
  copied verbatim with its BLAKE3 checked after the copy (`bf6147c3328a84af…`), and the manifest records that
  the port carries `frank.vmdl_c` and no source `.vmdl` (`"source": false`).
- **Graph compile, Dota toolchain:** the Dota tree carries the full animation system, so its compiler built
  `biped_standard.vanmgrph` → `biped_standard.vanmgrph_c` (**62,191 bytes**, 1 compiled, 0 failed) once the
  graph's own model sat under the addon root. The reduced CSDK13 cannot do this: its `animationsystem.dll` is
  disabled and its compiler fails every graph with `Tried to FileExists NULL filename`.
- **Popit probe:** 7/7 UI checks, receipt `artifacts/receipts/scout-update-popit.json`.

## Refused, by name

- `hero-not-declared` — the port's hero binding is not in its hero table (no entry names a Scout model), so
  `stage` will not pick one. The owner declares the live hero; nothing is guessed.
- `graph-schema-not-retargetable` — the Dota authored document has no `m_variationID`; pointing it at Scout's
  skeleton is an editor job in `animgraph_editor.dll`, not a two-field replacement.
- `animgraph-sequence-unbound` — 24 of 24 on both sides, above.
- `graph-skeleton-unverified` — no DMX skeleton for Frank appeared in the S2V model dump (150 clips, no
  skeleton), so no variation was retargeted at a path that does not exist.

## Not done

- The bake itself (SMD → DMX on the port's skeleton, then the graph's sequences re-pointed). The join is
  measured; the conversion is the next unit.
- The base `hero.vnmgraph` document behind a Deadlock `hero.vnmgraph+<hero>.vnmgraph` variation is not in the
  workspace, so the variation cannot be compiled alone by the Dota compiler.
- In-game launch of the port or the compiled graph.

## Done in the third pass

- **The mod is on main.** `update --write` replaced the port's stale `heroes.vdata` (63 entries) with the
  live roster (**67**), keeping `heroes.vdata.pre-update` beside it (BLAKE3 recorded, digest in
  `artifacts/receipts/scout-update-hero-table.json`). The report's drift row went from `6 new, 2 gone,
  13 moved` to `0 new, 0 gone, 0 moved`, and every other row passes: `result pass`.
- **A Scout variation in the live build's own graph, compiled.** `hero_aim.vnmgraph` decompiled from
  `hero_aim.vnmgraph_c` (20,234 → 932,528 bytes) holds 140 heroes as 18 pose nodes × `m_overrides`.
  `variation --to Scout --skeleton models/heroes_wip/frank/frank.vnmskel` added 18 overrides and one
  hierarchy entry; the compiler built **143, 0 failed**, producing
  `hero_aim_scout.vnmgraph+scout.vnmgraph_c` (5,475 bytes).
- **A graph from the Dota branch proper.** `scout_loco.vanmgrph`: the Dota template's 24 sequence slots
  renamed to the port's own QC sequences (379 declared, 24/24 bound), bound to the hero's model, compiled
  **28,482 bytes**, with the template rig's `Foot_Left`/`Foot_Right` foot-lock warning recorded.
- **The tool grew `update`, `variation`, `graph`, and a `--variation` reading on the Popit page**; the
  probe still gates the page (7/7) and the tests are 21 in this file, 384 across the repo.

## The line not crossed

Every one of the 18 Scout clips is **named and absent**: the graph points at
`models/heroes_wip/frank/clips/<name>.vnmclip`, which does not exist. Making them is SMD → DMX on
`frank.vnmskel` (rebased to the shipped joint order) plus a `.vnmclip` per clip — the SMD conversion does
not exist in the repo yet, and the compiler does not check clip existence, so the compile above is a
proof of structure, not of playback.

## Done in the fourth pass

- **The gap is closed end to end.** `plan` reads both graphs and finds **36 references** (24 locomotion
  slots + 12 aim clip paths), **36 distinct** names from **24** Scout sequences, `missing 0`. `bake` writes
  36 animation DMX (7,368,484 B) and 36 `.vnmclip` documents; `verify` reads every DMX back and counts
  **520 animated quaternion channels over 39,962 samples**.
- **Bound by name, not index.** 54 of 76 SMD nodes land on 54 Frank joints through an explicit `BONE_MAP`;
  the 22 TF2-only nodes are named in the receipt (`weapon_bone_*`, `medal_bone`, `mvm`, `effect_hand_L/R`,
  dogtag, pack, prop chains) and never guessed.
- **Compiled, and proved compiled.** The compiler needs an absolute `-i` path from the content root (a
  relative one answers `0 compiled, 0 failed, 0 skipped`), the decompiled `frank.vnmskel` plus its
  `frank_skel.dmx` beside the clips, and reads its output from the `<addon>/game` mirror in lower case.
  With those: skeleton `OK: 1 compiled`, **36/36 clips**, 36 distinct md5s, `hero_aim_scout.vnmgraph`
  **143 compiled 0 failed** (142 variation outputs), `scout_loco.vanmgrph` 28,481 B.
- **Packed and mounted.** `scout_animgraph_dir.vpk` — VPK v2, 76 entries, 7,597,467 B: compiled graph, the
  Scout variation, compiled skeleton, 36 compiled clips and the 36 DMX they sample. `forge.oldmods.read_vpk`
  reads back 76/76 and Source 2 Viewer extracts the variation, which decompiles naming `Scout` and 12 clips.
- **Tools mode launches, observed nothing.** `deadlock.exe` with the tools flags starts and stays resident;
  no Scout motion was seen, because that needs a map session with the model spawned.
- **Not claimed.** The locomotion graph is `animgraph19`, so its 24 slots are names bound through the
  model's sequence table; the names match the generated clips exactly, but the model was not rebuilt to
  declare them.

## Re-aimed 2026-11-24, verbatim

> I never said it had anything to do with mapping onto frank I said it had to use the deadlock model forge
> and create popit-shell applications for working with it

What changes:

- **The frank binding is not the plan.** The four earlier slices baked onto
  `models/heroes_wip/frank/frank.vnmskel` and put a `hero_scout` entry on top of that rig; that was my
  inference. Scout keeps his own skeleton and animations, and the deliverables are forge tooling plus
  Popit-shell applications.
- **What survives.** `forge/clipbake.py` and `tools/scout_clip_bake.py` are rig-agnostic: the SMD/QC
  reader, the joint-by-name binding, the kv2 writer, the clip compile and the VPK writer are reused
  against Scout's own skeleton.
- **What is superseded, and kept.** `artifacts/scout-update/clips`, the frank-bound
  `scout_animgraph_dir.vpk`, `scout_loco.vanmgrph` and the hero table entry built on it. They stay on disk
  and are named as superseded by the application; none is counted as progress.
- **What is new.** `popit_apps/scout_port/` — a Popit-shell application (loopback server, one JSON API,
  family register UI, probe) that reads the port through `forge.scout`, registered as a **Scout Port** row
  in `popit-shell/server.py`'s launcher. It reports `inventory pass`, then `skeleton blocked
  (skeleton-not-built)` and `hero blocked (hero-not-registered)`.

## Cleared on 2026-11-24

- **Skeleton.** `forge/portskel.py` + `tools/scout_skeleton.py` transcribe `scout_anims/ref.smd` into a 78-joint
  skeleton DMX and a `.vnmskel`; compiled `OK: 1 compiled`, decompiled back 78/78 bones.
- **Clips.** `tools/scout_own_clips.py` bakes port sequences onto that skeleton by identity: 4 clips baked,
  **5/5 documents compiled**, 4 × 78 channels verified.
- Evidence: `data/probes/2026-11-24-scout-own-skeleton-and-clips.md`, `artifacts/receipts/scout-skeleton.json`,
  `artifacts/receipts/scout-own-clips.json`.

## Graph cleared on 2026-11-24

- **Authored, not patched.** `forge/scoutgraph.py` + `tools/scout_graph.py` write a standalone
  `CNmGraphDocument` from the shapes the live documents carry: motion states `state_Scout_Attack`
  (21 frames) and `state_Scout_Reload` (20 frames), aim states `aim_state_Scout_AimIdle`/`aim_state_Scout_AimRun`
  whose pose nodes `aim_*` are the 2-frame poses. 4 clip references, 0 frank references.
- **Compiled 5/5 documents, 0 failures**; `scout.vnmgraph_c` 2,512 B.
- **Verified from the compiled artifact**: decompiled back to 30,255 B, all four clips at 78 channels,
  skeleton `models/heroes_wip/scout/scout.vnmskel` named, 78 joints, 78 bones in the compiled skeleton,
  no frank references. `RESULT: PASS`.
- **Traps kept** in `artifacts/scout-graph/bisect.py` and `tests/test_scout_graph.py`: root variation must
  be `Default`; a machine needs the global transition conduit; a state's secondary graph holds its layer
  data; a pose node's four extra fields; pruned unreachable pose nodes.
- Evidence: `data/probes/2026-11-24-scout-animgraph-authored.md`, `artifacts/receipts/scout-graph.json`.

## Corrected 2026-11-24 — the mesh exists

The owner, verbatim: *"the mesh for scouts model exists on disk"*. The `mesh-not-built` line was read
from `scout_anims/ref.smd` having no `triangles` block, which is true of that reference SMD and false
about the port: `F:/Documents` carries `scout.mdl` (910,028 B), `scout.vvd` (529,152 B, `IDSV` v4),
`scout.dx90.vtx` (311,996 B), `scout.obj` (1,055,705 B — 8,261 vertices, 7,814 faces), `scout.phy` and
15 `.vtf` textures. There is no `.vmt` and no mesh DMX, so the step is `ready` with `mesh-not-converted`.
Evidence: `data/probes/2026-11-24-scout-mesh-present-on-disk.md`, `tests/test_scout_port_app.py`.

## 2026-11-24 — the mesh is converted, and here is the proof

`forge/meshbuild.py` emits the mesh DMX in the keyvalues2 `format model 22` encoding the port's skeleton
and clips already use, with the element shape read out of two real mesh DMXs (`biped_standard_model.dmx`,
`frank_frank_lod36.dmx`) converted with `dmxconvert -oe keyvalues2`. The written file re-parses to
**8,261** `position$0`, **7,814** faces, **78** joints, `jointCount` 4 and weight sums of exactly **1.0**
for every row; `dmxconvert` independently reads 8,261 positions / 23,442 corners / 7,814 faces / 33,044
weights out of a binary round trip. The model compiles with CSDK 13: 16/16 documents, `scout_body.vmdl_c`
**107,209 B** (`MVTX` 91,645 B, `MIDX` 8,932 B), 15 `.vmat_c`.

`RenderMeshFile` names `heroes_wip/scout/dmx/mesh/scout_body.dmx`, not the skeleton `scout_skel.dmx`: a
`RenderMeshFile` is loaded as mesh geometry, and the skeleton path stays the one the `.vnmskel` names.
The mesh DMX carries the same 78-joint `DmeModel` so the geometry binds to that rig. Materials: 15 `.vmt`,
15 `.vmat`, 15 `.png` (5 real, 10 placeholders). Evidence: `data/probes/2026-11-24-scout-mesh-built.md`,
`artifacts/receipts/scout-mesh.json`.

## 2026-11-24 — the clips are Deadlock animation documents, parsed back

Format by evidence: the Dota 2 tool-branch `biped_standard/dmx/animation/idle.dmx` (1,013,864 B)
converts to 308 channels — 154 `_p` + 154 `_o` over 89 joints — in `DmeChannelsClip`/`DmeChannel`/
`DmeQuaternionLog`/`DmeTimeFrame`. Scout's four compiled clips parse to **156 channels (78 `_p` + 78
`_o`)** each, with joint names identical to the 78-joint skeleton:

| clip | compiled | channels | frames | duration |
| --- | --- | --- | --- | --- |
| `Scout_Attack` | 4,096 B | 156 | 21 | 0.6667 s |
| `Scout_Reload` | 4,099 B | 156 | 20 | 0.6332 s |
| `Scout_AimIdle` | 4,096 B | 156 | 2 | 0.0332 s |
| `Scout_AimRun` | 4,096 B | 156 | 2 | 0.0332 s |

The authored documents carry the 78 orientation channels baked from the QC's sequences
(`PRIMARY_aimmatrix_idle` 832, `PRIMARY_aimmatrix_run` 834, `AttackStand_PRIMARY` 838,
`PRIMARY_reload_loop` 852); the compiler samples them into the shipped two-track layout, and the added
position tracks are holds — `bip_pelvis_p` in `Scout_Attack` has 23 samples with 3 unique values all
within 0.0001 of zero. `scout.vnmgraph_c` (2,512 B) decompiles to 25 nodes with **4 clip references** under
`state_Scout_Attack`, `state_Scout_Reload`, `aim_state_Scout_AimIdle` and `aim_state_Scout_AimRun`, the
skeleton `models/heroes_wip/scout/scout.vnmskel`, and 0 `frank` references. End-to-end compile by
`tools/scout_anim.py`: **21/21 documents, 0 failed** (`scout.vnmskel_c`, 4 `*.vnmclip_c`,
`scout.vnmgraph_c`, `scout_body.vmdl_c` 107,209 B, 15 `*.vmat_c`). The app reads
`artifacts/scout-anim/parsed/<clip>.json`, so a clip without a parse is `clips-partial` or
`clips-not-converted`, never assumed. Evidence: `data/probes/2026-11-24-scout-clip-documents-verified.md`,
`artifacts/receipts/scout-anim.json`.

## 2026-11-24 (later) — motion measured per channel, and the bake now carries translation

`tools/scout_variance.py` parses each clip's animation document back through `dmxconvert` and measures
per channel: samples, distinct values (1e-4 tolerance), and spread; the same measurement on the
sequence's own SMD gives the source frame count, joint angles and translations.

| clip | source frames | samples | moving orientation | moving position | flat where source moves |
| --- | --- | --- | --- | --- | --- |
| `Scout_Attack` | 21 | 21 | 22/78 | 2/78 | 0 |
| `Scout_Reload` | 20 | 20 | 28/78 | 2/78 | 0 |
| `Scout_AimIdle` | **1** | 2 | 0/78 | 0/78 | 0 |
| `Scout_AimRun` | **1** | 2 | 0/78 | 0/78 | 0 |

The aim clips are not truncated: their source SMDs are **one frame**, with no moving and no translating
joint. The two motion clips move exactly where their sources move.

The real defect was translation: `bip_pelvis` moves 0.456 units (0.165 in reload) and `weapon_bone`
0.361 (4.680) in the sources, but the template had orientation channels only, so the bake dropped those.
`forge.portskel.write_clip_template` now writes a `_p` channel per joint (rest local position from the
skeleton) and `forge.clipbake.bake_kv2` writes the source delta; `tools/scout_graph.py compile` stages
the baked DMX where the compiler resolves it. Both clips now report 2 moving position channels.

Also established by measurement: `vnmclip_c` is a 4 KB reference document, not the samples — one changed
quaternion in the source DMX moves exactly 4 bytes (offset 905–908) of the compiled clip, and
Source2Viewer's re-export is a 117,366 B rest-pose reconstruction, not the animation. The measured
document is the DMX the clip names.

Recompiled **21/21, 0 failed**; graph 2,512 B with 4 clip references and 78 joints; `scout_body.vmdl_c`
107,209 B from the fixed mesh path; **413 tests**, probe **12/12**. Evidence:
`artifacts/scout-anim/variance/*.json`, `artifacts/receipts/scout-anim.json` (`variance`),
`data/probes/2026-11-24-scout-clip-documents-verified.md`.

## Still refused, and why

| step | state | reason |
| --- | --- | --- |
| pack | ready | no VPK of this rig exists yet — `pack-not-built` |
| hero | blocked | no model names this graph, so `hero-not-registered` |
| mesh | converted | `scout_body.dmx` 2,461,515 B parses to 8,261 verts / 7,814 faces / 78 joints, weights 1.0; model compiles to 107,209 B; 15 `.vmt` + 15 `.vmat` — no refusal |
| in-game | blocked | no client launched for this slice — `not-observed` |

## Source-anchored frame counts, read from the model's own descriptors (2026-11-24)

`forge/mdlseq.py` decodes `F:/Documents/scout_animations.mdl` directly (5,017,436 B, md5
`74950ba0453e9ef71fa1a32a840573ac`): 377 sequence descriptors at 4,841,760 on a **212-byte** stride (the
first entry's +28 field carries `377 × 212`, and the last entry ends on it), every field **4 bytes after**
the published `mstudioseqdesc_t` — label at +4, activity name at +8, flags +12, numblends +56, anim-index
block at +60; anim descriptions at 17,508 × 1,012, stride 100, name +4, fps +8, frames +16. 377/377 labels
decode printable and unique; the activities decode as `ACT_MP_ATTACK_STAND_PRIMARY` and
`ACT_MP_RELOAD_STAND_PRIMARY_LOOP`, which is what the QC declares.

| clip | sequence (descriptor) | activity | blends/cells | **MDL frames** | SMD frames | samples | moving `_o` | moving `_p` | flat where source moves |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Scout_Attack` | `AttackStand_PRIMARY` (4,843,032) | `ACT_MP_ATTACK_STAND_PRIMARY` | 1 / 1 | **21** | 21 | 21 | 22/78 | 2/78 | 0 |
| `Scout_Reload` | `PRIMARY_reload_loop` (4,844,516) | `ACT_MP_RELOAD_STAND_PRIMARY_LOOP` | 1 / 1 | **20** | 20 | 20 | 28/78 | 2/78 | 0 |
| `Scout_AimIdle` | `PRIMARY_aimmatrix_idle` (4,842,396) | — | 12 / 12 | **1** | 1 | 2 | 0/78 | 0/78 | 0 |
| `Scout_AimRun` | `PRIMARY_aimmatrix_run` (4,842,608) | — | 12 / 12 | **1** | 1 | 2 | 0/78 | 0/78 | 0 |

- The declared numbers agree with the SMDs (21/20/1/1) and with the measured variance, so no clip was
  rebaked; the extraction and bake were already faithful. `tools/scout_variance.py` now fails a clip
  whose declared frame count or single-pose declaration disagrees with its source.
- The aim clips are single-pose **in the model**: twelve cells of one frame at 30 fps each (flags 1044),
  the same twelve names in the same order as the QC's `$sequence` — not a truncated clip.
- `scout.mdl` (306 descriptors, 910,028 B) names the four sequences but declares `numblends 0` and
  flags 2048 for them; it carries 2 anim descriptions. The data and frame counts are in the animations
  companion, which is also the file Crowbar 0.74 decompiled into `scout_animations.qc` +
  `scout_animations_anims/` (1,412 SMDs). The descriptor's anim name (`@AttackStand_PRIMARY`), the QC's
  `$sequence "AttackStand_PRIMARY"` naming `scout_animations_anims\AttackStand_PRIMARY.smd`, and the SMD
  itself agree, so the 21/20/1/1 trace back to the real source file.
- The per-bone RLE payload behind each anim description did not decode (its +56 target is not a
  published `mstudioanim_t` header: first int 9,313,280, past the file; anim block table empty). The
  block, the offsets and the dumped bytes are named in
  `data/probes/2026-11-24-scout-mdl-source-frames.md` rather than assumed.
- Re-verified unchanged: `tools/scout_anim.py` **21/21 documents, 0 failed**, model 107,209 B from
  `heroes_wip/scout/dmx/mesh/scout_body.dmx`, 15 `.vmat_c`; `tools/scout_graph.py verify` **PASS**, all
  four clips in the compiled graph with 78 channels, skeleton **78 joints**, no `frank` refs. **415
  tests**, probe **12/12**.

## Installed into the live game (2026-11-24)

`tools/scout_install.py install` writes the port's compiled set to
`D:\SteamLibrary\steamapps\common\Deadlock\game\citadel_addons\scout_port\` and packs the same bytes to
`artifacts/scout-update/vpk/scout_port_dir.vpk`:

| group | files | bytes |
| --- | ---: | ---: |
| `scout.vnmskel_c` | 1 | 7,187 |
| `scout.vnmgraph_c` | 1 | 2,512 |
| `clips/scout_{attack,reload,aimidle,aimrun}.vnmclip_c` | 4 | 16,387 |
| the four animation DMX the clips name | 4 | 349,744 |
| `scout_body.vmdl_c` | 1 | 107,209 |
| materials `.vmat_c` + `.vtex_c` | 30 | 15,467,968 |
| **total** | **41** | **15,951,007** (VPK 15,952,866 B, 41/41 entries read back) |

- Every installed file is md5-compared with its staged source in `artifacts/receipts/scout-install.json`
  (`matches_staged` 41/41). The animation DMX ship because a compiled `vnmclip_c` is a reference plus a
  checksum, not samples.
- **Verified from the installed copy**, not the CSDK mirror:
  `tools/scout_graph.py verify --csdk D:/SteamLibrary/steamapps/common/Deadlock` decompiles the installed
  `scout.vnmgraph_c` (30,255 B) and finds all four clips at **78 channels**, the motion and aim states, the
  skeleton named, **78 bones**, and **no frank references** — `RESULT: PASS`.
- **The app reports the install**: `pack_state()` reads the receipt and re-checks each named file, so
  `pack` is `pass` (41 files / 4 clips / 4 DMX / 30 materials / VPK 41 entries) or `pack-not-built` when
  the install is absent. The probe's downstream check now requires `pack pass` and still refuses `hero`
  and `in_game` by name; still **12/12**. `tools/scout_install.py probe` reads the same surface (4/4).
- The superseded frank-bound `game/citadel_addons/scout_animgraph/` and its VPK stay on disk, named under
  `superseded`; nothing in the install reads them.

## Hero registered (2026-11-24)

`hero_scout` is in the port's hero table as a selectable hero entry, compiled into the installed addon:

| field | value |
| --- | --- |
| table | `F:/Documents/heroes.vdata`, backup `F:/Documents/heroes.pre-scout`, 68 → 69 blocks |
| entry | `hero_scout`, `m_HeroID = 89` (free; ids ran to 88) |
| body | `resource_name:"models/heroes_wip/scout/scout_body.vmdl"` |
| hero graph | `m_sAG2VariationName = resource_name:"models/heroes_wip/scout/scout.vnmgraph"` (the field released heroes use) |
| cloned from | `hero_frank` — abilities, item slots, level info, stats, shop/portrait/icon maps kept, because the engine resolves them by name |
| compiled | `scripts/heroes.vdata_c` **89,695 B**, md5 `7e7814…`, `OK: 1 compiled, 0 failed` (the unmodified table compiled to 89,448 B first, so the compiler was exercised before the entry) |

- **The entry resolves in the installed copy.** `tools/scout_install.py` installs **42 files /
  16,040,702 B** and checks `scout_body.vmdl` → installed `scout_body.vmdl_c` (107,209 B) and
  `scout.vnmgraph` → installed `scout.vnmgraph_c` (2,512 B, md5 equal to the compiled graph); installed
  table md5 equals the compiled table. VPK 42 entries, 16,042,604 B, read back 42/42.
- **Read back from the installed bytes.** Source 2 Viewer decompiles the installed `heroes.vdata_c` and
  the `hero_scout` block is there with id 89 and both Scout paths
  (`artifacts/scout-hero/installed-readback/heroes.vdata`). The installed graph still verifies: **PASS**,
  four clips at 78 channels, 78 bones, 0 frank refs.
- **The app reads it.** `hero_state()` checks the receipt and each named file; the hero step is `pass`,
  the app probe is **13/13** with a `hero-registered` check and `downstream-refused` now only `in_game`,
  and `tools/scout_install.py probe` is **6/6**. **415 tests**, both audits pass.
- **Not observed.** No game session was launched; in-game roster selection and clip playback are
  **unobserved**, and the app still reports `not-observed` for that step.

## Next, in order

1. ~~Build Scout's own skeleton~~ done: 78 joints, `.vnmskel` compiled, 7,187 B.
2. ~~Bake the port's sequences~~ done for the four the graph uses; the remaining 375 sequences are not
   baked, and are not claimed.
3. ~~Author the port's own animgraph~~ done: 4 clip references, 2 states, 2 aim states, compiled 2,512 B.
4. ~~Pack the addon VPK and install it~~ done: 41 files in the live addon folder, verified from there.
5. ~~Register Scout as a selectable hero against the installed model~~ done: `hero_scout`, id 89,
   compiled table installed, paths resolved and read back from the installed bytes.
6. Observe him in a local match: launch a session, pick Scout, and watch the four clips play
   (`not-observed` — nothing was launched, so nothing is claimed).

## Evidence

- `data/probes/2026-11-24-scout-port-popit-app.md`, `artifacts/receipts/scout-port-app-probe.json`
- `popit_apps/scout_port/`, `F:/Documents/popit-shell/server.py`
- `artifacts/scout-update/report.json`, `artifacts/scout-update/sequence-map.json`
- `artifacts/receipts/scout-clip-bake.json`, `artifacts/receipts/scout-clip-verify.json`, `artifacts/receipts/scout-vpk.json`
- `artifacts/scout-update/vpk/scout_animgraph_dir.vpk`, `data/probes/2026-11-24-scout-clip-bake.md`
- `artifacts/receipts/scout-update-popit.json`
- `logs/scout-compile-vanmgrph-addonroot.log` (`OK: 1 compiled`), `logs/scout-compile-deadlock-schema2.log`
- `data/probes/2026-11-23-scout-port-popit.md`

## 2026-11-24 — Scout UI assets, and the graph field's observed contract

Scout's icon, card, minimap, vertical and the three UI maps no longer name Frank's assets. The entry now
names three Scout images built by `tools/scout_ui.py` and the game's `default_shop` / `default_team_reveal`
/ `default_postgame_portrait` maps; Frank's portrait prefab and name logos are dropped (14 and 23 shipped
heroes carry no such fields). The addon is 45 files / 20,238,273 B, VPK 45 entries, all read back.

`m_sAG2VariationName` is answered from evidence, not assumption: only `hero_vampirebat` and `hero_necro`
set it among 69 blocks, both as `hero.vnmgraph+<hero>.vnmgraph`; the branch ships 51 such variations and 26
standalone auxiliary graphs that no entry names; both forms decompile as complete graphs, and the binaries
carry no literal to settle loader behaviour. A standalone graph is therefore recorded as unverified
(`ag2-hero-variation-required`), not claimed to load; a real `hero.vnmgraph+scout` would need the shipped
37-node locomotion/ability contract that the port's four clips do not cover.

- Evidence: `data/probes/2026-11-24-scout-ui-and-ag2-binding.md`, `artifacts/receipts/scout-ui.json`,
  `artifacts/receipts/scout-install.json`, `artifacts/receipts/scout-install-probe.json`,
  `artifacts/receipts/scout-port-app-probe.json`, `artifacts/scout-hero/ui-verify/`
- Checks: install probe 7/7, app probe 14/14, `pytest -q` 415 passed, both audits pass.
- Not observed: no session launched; in-game icon rendering, maps, selection and playback remain unobserved.
