# 2026-11-24 — Scout's frame counts read from the model's own sequence descriptors

The mission asked for the one link that was still on trust: the 21/20/1/1 frame counts behind
`Scout_Attack`, `Scout_Reload`, `Scout_AimIdle` and `Scout_AimRun` came from the decompiled SMDs and the
QC's `$sequence` declarations. This record reads them out of the model files themselves, beside the
variance already measured on the baked documents.

**Answer: the model declares the same numbers — 21, 20, 1, 1 — and declares the two aim sequences as
twelve one-frame blend cells each. No clip was rebaked; the extraction and bake were already faithful.**

## The layout, measured not assumed

`studio.h`'s `mstudioseqdesc_t` offsets returned zeros and string garbage, so the table was solved as a
layout problem against the file:

| element | measured | evidence |
| --- | --- | --- |
| sequence count / table | header **@ 188** (306 in `scout.mdl`, 377 in `scout_animations.mdl`), table **@ 192** | count agrees with the file's own name list |
| entry stride | **212** | entry 0's field at +28 equals `count × 212` (64,872 = 306 × 212 in `scout.mdl`; 79,924 = 377 × 212 in `scout_animations.mdl`), every label resolves inside its own entry, and the anim-index block at +60 decodes for the 1- and 12-blend entries |
| label | entry + `i32(entry + 4)` | **306/306** and **377/377** decode as printable, **unique** labels (`ref`, `ragdoll`, `user_ref`, …) |
| activity name | entry + `i32(entry + 8)` | `ragdoll` → `ACT_DIERAGDOLL`; `AttackStand_PRIMARY` → `ACT_MP_ATTACK_STAND_PRIMARY` |
| flags | entry + 12 | 22 / 21 for the motion clips, 1044 for the aim matrices |
| numblends | entry + 56 | 1 for the motion clips, 12 for the aim matrices |
| anim index block | entry + `i32(entry + 60)`, `short[numblends]` | each index lands in the anim description table |
| anim descriptions | header **@ 180** count, **@ 184** table, stride **100** | name @ +4, fps @ +8 (float 30.0), frames @ +16 |

Every field sits **4 bytes after** the published `mstudioseqdesc_t`; the published offsets are what failed
in the earlier probes. The anim description table is read at its published stride because its fps/frames
decoded directly.

Two fields that the published layout treats as indices do **not** hold indices here, and both were checked
across every entry in both files rather than on one:

- **Field 0** stores the negative of the entry's own offset — `i32(entry) == -entry` for **306/306** and
  **377/377** entries — not a label index; the label string offset at +4 is descriptor-relative, so there
  is no label-index base to add.
- **The published frame/range integers do not carry frames.** +28 varies with the entry (63,596 for the
  21-frame `AttackStand_PRIMARY`, 62,112 for the 20-frame reload, 64,232 for the 1-frame aim idle), and on
  entry 0 in both files it holds `count × 212` (64,872 / 79,924) — the table size, which is the stride
  datum used above, not a frame range. On other entries it follows no simple formula, so it is recorded
  as unresolved rather than called a frame field. The frame count decodes only at anim description +16,
  which is what the decoder reads.

## What the model declares

`F:/Documents/scout_animations.mdl`, 5,017,436 B, md5 `74950ba0453e9ef71fa1a32a840573ac`:

| clip | sequence | descriptor | activity | flags | blends / cells | anim names (frames @ fps) | declared frames |
| --- | --- | ---: | --- | ---: | --- | --- | ---: |
| `Scout_Attack` | `AttackStand_PRIMARY` | 4,843,032 | `ACT_MP_ATTACK_STAND_PRIMARY` | 22 | 1 / 1 | `@AttackStand_PRIMARY` **21** @ 30 | **21** |
| `Scout_Reload` | `PRIMARY_reload_loop` | 4,844,516 | `ACT_MP_RELOAD_STAND_PRIMARY_LOOP` | 21 | 1 / 1 | `@PRIMARY_reload_loop` **20** @ 30 | **20** |
| `Scout_AimIdle` | `PRIMARY_aimmatrix_idle` | 4,842,396 | — | 1044 | 12 / 12 | `a_PRIMARY_aimmatrix_idle_straight_up` ×3, `_up_right`, `_up_center`, `_up_left`, `_mid_right`, `_mid_center`, `_mid_left`, `_down_right`, `_down_center`, `_down_left` — **1** frame each @ 30 | **1** |
| `Scout_AimRun` | `PRIMARY_aimmatrix_run` | 4,842,608 | — | 1044 | 12 / 12 | `a_PRIMARY_aimmatrix_run_*`, same twelve cells — **1** frame each @ 30 | **1** |

So the aim clips are **single-pose by the model's own declaration** — twelve aim-matrix cells of one
frame each, not a truncated clip — and the motion clips are 21- and 20-frame sequences at 30 fps.

`F:/Documents/scout.mdl` (910,028 B, md5 `a1ad2511d8f6bab2baaa06263e4019e9`) declares the same four
names in its own 306-entry table (descriptors 24,624 / 24,836 / 25,260 / 26,744) but **names only**: each
entry has `numblends 0`, `flags 2048`, and its anim block points at the table end (88,856). The file has
2 anim descriptions in total. Its animation data and descriptors live in the companion model that sits
beside it — the same file the port's SMDs were decompiled from.

## The block that would not decode, named

Each anim description carries an offset at +56 to its animation payload. Read as the published
`mstudioanim_t` (`int offset; ushort numframes; ushort numproperties`), the first four bytes are not a
file offset in the 5,017,436-byte file:

| sequence | animdesc | +56 | payload address | first bytes |
| --- | ---: | ---: | ---: | --- |
| `AttackStand_PRIMARY` | 23,308 | 118,724 | 142,032 | `001c8e00 0c00 2a00 4600 5c00 0000 0000 0e15 …` |
| `PRIMARY_reload_loop` | 24,108 | 139,092 | 163,200 | `001cca00 0c00 3200 5600 7600 9c00 0000 1013 …` |
| `PRIMARY_aimmatrix_idle` | 21,008 | 111,360 | 132,368 | `00311200 c7ce 0da3 0562 263d ad3b 0000 0000 …` |

`0x008E1C00` (9,313,280) cannot be an offset into a 5 MB file, and the anim block table is empty
(header @ 352 = 0 entries, table @ 4,964,592), so there is no embedded block list to resolve it with.
Absolute (118,724) and anim-table-relative (17,508 + 118,724) reads produce float noise, not frame
headers. **The per-bone RLE payload therefore stays undecoded**, and this record makes no per-bone claim
from it: whether the bones move is measured on the decompiled SMD (below), whose frame count matches the
descriptor exactly.

## Provenance of the SMDs already in use

So the 21/20/1/1 can be traced from the file that produced them:

1. `F:/Documents/scout_animations.mdl` — the animation model. Its descriptors are the ones decoded above.
2. `F:/Documents/scout_animations.qc` — written by **Crowbar 0.74** (first line: `// Created by Crowbar
   0.74`), `$modelname "player/scout_animations.mdl"`, the same 78 `$definebone` lines the port skeleton
   uses. The QC's `$sequence` blocks are the decompiler's rendering of the same table:
   - `$sequence "PRIMARY_aimmatrix_idle"` (line 8420) lists the twelve cells **in the descriptor's order**
     (`straight_up` ×3 then `up_right` … `down_left`, `blendwidth 3`, `blend "body_yaw" 45 -45`,
     `blend "body_pitch" 90 -45`) — the same order and duplicates the MDL anim indices carry
     (`[35, 35, 35, 32, 33, 34, 29, 30, 31, 26, 27, 28]`).
   - `$sequence "PRIMARY_aimmatrix_run"` (line 8444) likewise.
   - `$sequence "AttackStand_PRIMARY"` (line 8492) names
     `scout_animations_anims\AttackStand_PRIMARY.smd`, `activity "ACT_MP_ATTACK_STAND_PRIMARY" 1`.
   - `$sequence "PRIMARY_reload_loop"` (line 8585) names
     `scout_animations_anims\PRIMARY_reload_loop.smd`, `activity "ACT_MP_RELOAD_STAND_PRIMARY_LOOP" 1`.
3. `F:/Documents/scout_animations_anims/` — 1,412 SMDs written by that same Crowbar decompile (folder
   mtimes 2026-05-12), including `AttackStand_PRIMARY.smd`, `PRIMARY_reload_loop.smd` and the twelve
   `a_PRIMARY_aimmatrix_*` cells per aim matrix.
4. `tools/scout_own_clips.py` bakes those SMDs onto the port's 78-joint skeleton (orientation and
   position channels), `forge/clipbake.py` writes the DMX.
5. `tools/scout_variance.py` now reads the model descriptor for each clip's `source_sequence` and puts its
   declared frame count beside the SMD's frame count, the document's samples and the per-channel variance.

The MDL anim name and the QC/SMD name agree at every step (`@AttackStand_PRIMARY` descriptor →
`$sequence "AttackStand_PRIMARY"` → `AttackStand_PRIMARY.smd`), so the SMD is the decompiler's decode of
the very anim description that declares the frame count.

## Source numbers beside measured numbers

| clip | MDL declared frames | SMD frames | document samples | moving orientation | moving position | flat where source moves |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Scout_Attack` | **21** (anim `@AttackStand_PRIMARY`) | 21 | 21 | 22/78 | 2/78 | 0 |
| `Scout_Reload` | **20** (`@PRIMARY_reload_loop`) | 20 | 20 | 28/78 | 2/78 | 0 |
| `Scout_AimIdle` | **1** (12 cells × 1 frame) | 1 | 2 (same pose twice) | 0/78 | 0/78 | 0 |
| `Scout_AimRun` | **1** (12 cells × 1 frame) | 1 | 2 (same pose twice) | 0/78 | 0/78 | 0 |

`tools/scout_variance.py` fails a clip whose declared frame count disagrees with its SMD, or whose
single-pose declaration disagrees with the measured one; all four are `ok=True`.

## Checks run

- `python tools/scout_variance.py --write` — mdl 21/20/1/1 vs smd 21/20/1/1, `ok=True` ×4; merged into
  `artifacts/scout-anim/variance/*.json`, `artifacts/scout-anim/parsed/*.json` and
  `artifacts/receipts/scout-anim.json` (`variance.source_model` names the model, its bytes and md5).
- `python tools/scout_anim.py` — **21/21 documents, 0 failed**, model 107,209 B, 15 `.vmat_c`, graph
  2,512 B with 25 nodes and 4 clip refs.
- `python tools/scout_graph.py verify --csdk …` — `RESULT: PASS`, each of `Scout_Attack`,
  `Scout_Reload`, `Scout_AimIdle`, `Scout_AimRun` in the compiled graph with **78 channels**, skeleton
  **78 joints**, `frank refs: False`.
- `python -m pytest -q` — **415 passed** (2 new in `tests/test_mdlseq.py`: descriptor frames/single-pose;
  a name-only descriptor declaring no frames).
- `python popit_apps/scout_port/probe.py` — **12/12**, `clips pass` 4/4 parsed, frames 21/20/2/2.

## Not done

- The per-bone RLE payload is not decoded (bytes and offsets above); the motion claim rests on the
  descriptor's frame count plus the decompiled SMD, not on re-decoding the compressed tracks.
- No VPK, no hero registration, no in-game playback — unchanged refusals.
