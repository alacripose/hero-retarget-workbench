# TICKET-0033 — Add any source tail, with its clip motion, to a hero that has none

**Status:** implemented in 0.13.2; automatic Shiv + Werewolf probe, 138/138 gameplay compile on the 147-bone animation skeleton, full skeleton tail audit, and pytest pass.
**Owner:** ala
**Opened:** 2026-11-14

## Requirement

The owner's correction, verbatim:

> the whole point of the tails features is to add tails to models who don't have them with the tails animations, not pinned to these two

The earlier scope required a one-action process:

> tails can't ask users to do everything one step at a time, this is the one exception ... Especially considering tail animations are on a lot of clips it's not reasonable to ask users to do it one clip at a time, it needs to be an automatic process that adds the tail animations to the heroe's animations. I'd really like to see you get it working using werewolf's tail on shiv

## Contract

1. **A hero does not need an existing tail channel.** Selecting a source tile and
   pressing **Add tail to N clips** copies that source's tail rest bones into the
   hero skeleton first. Existing hero bones are never moved or renamed, so the
   operation is idempotent.
2. **The source is any discovered chain.** The operator uses the selected
   `DMF_TailOption`, not a hard-coded Werewolf/Shiv pair. Werewolf, Familiar,
   Drifter, a live-roster skeleton or the imported hero can supply the chain.
3. **Source clips come from the source's own extraction.** Matching is by clip
   label and never by a same-named file from another hero's extraction. A source
   extraction without clips refuses the pass with `tail-source-clips-empty`.
4. **Every imported hero clip is processed in one pass.** The queue is built from
   rows whose state is `IMPORTED`/`WRITTEN`; each target action receives the
   source tail bones' location, rotation and scale keys over its own frame range.
5. **One clip per timer step.** The pass keeps the viewport responsive and reports
   `updated`, `no matching source clip`, and `failed` counts in the tail note.
6. **No guessing.** A target clip with no same-named source clip is skipped and
   counted. A source clip with no tail curves is rejected rather than flattening
   the target tail to rest.
7. **Old tail curves are replaced, body curves are not.** `_clear_tail_curves`
   removes only curves whose path starts with the target tail bone names.
8. **Manual pairing stays as a fallback.** The old per-bone map and single-clip
   writes are behind **Manual channel map**; they are not the required flow.
9. **The pass writes the DMX and invokes CSDK13's vnmclip compile.** It keeps the
   compiled `shiv.vnmskel_c` in the CSDK game addon so ModelDoc's clip preview
   can resolve the appended tail tracks, but never packs it into the VPK. Before
   writing, it exports the body armature **with its skinned mesh** (the
   armature-only export rotated the new tail sideways) and preserves the
   authored 90 degree `root_motion`; the body curves are relative to it, and
   removing it lays the model on its side.

## Blocker fixed on the way

PulseSrcOps under Blender 5.4 appends an animation as a **slot on the active
action**. `clipops._import_one` left the previous action active, so importing a
second target clip created no action and failed with `clip-no-action`. It now
detaches the active action before import. The same detach is applied to
tail-source clips, so each source clip gets its own action.

## Evidence

- `python -m pytest tests -q`: 253 passed.
- The owner confirmed `weapon_stand_idle.vnmclip_c` at **03:50:07** animates
  with an upright body and a visible, moving tail. That exact file is the gate:
  39802 bytes, sha256
  `3451df8946908d91dee22fa8792feee227a2c64bdd7a1ac30d1daf3d6654352d`;
  its `shiv.vnmskel_c` is 15731 bytes, sha256
  `c2f1e2439d773a350bf224c7069890c50479f381cab2e6b4a792c349670ac847`,
  decompiles to 168 bones with `tail_0..tail_5, tail_end`, and the clip is 168
  tracks. `tools/tail_vnmclip_gate.py` pins both files and runs from
  `python tools/project.py gate`.
- The exported tail rest matches the known-good fixed body
  (`shiv_body_tailbones.dmx`): `tail_0` head `(-6.36, 0, 61.236)`, `tail_end`
  `(-31.588, 0, 34.44)`, same parent and same roll.
- `python -m compileall -q forge blender/hero_retarget_workbench tools tests`: clean.
- `tools/blender_tail_auto_probe.py` on the real Shiv extraction:
  - Shiv imported; four clips imported (`aim_weapon_idle`, `cast_start`,
    `flinch_back`, `in_air_loop_apex`).
  - Tail discovery chose `werewolf / tail` (7 bones).
  - The automatic pass appended `tail_0..tail_5, tail_end` to Shiv and updated
    4/4 actions, 0 skipped, 0 failed.
  - Every target action has tail fcurves; `in_air_loop_apex` changes between its
    first, middle and last frame.
  - Receipt: `artifacts/receipts/probe-tail-auto.json`.
- `forge.tails.dmx_bone_names` reads binary DMX 9 NUL-separated names; real
  Werewolf returns 7 bones, Familiar 17, Shiv/Drifter none. The old quoted-token
  parser returned none for all four.

## 0.13.2 — gameplay skeleton correction

- **Import target.** Gameplay clips are authored on the 140-bone animation
  skeleton plus the appended seven tail bones (147 bones), not on the 168-bone
  body armature. The body armature interleaves extra joints, so its tracks do
  not match the source clip order and the body ends up horizontal.
- **Compiled evidence.** `weapon_stand_idle.vnmclip_c` in the separate
  `shiv_tail_full147` addon is 147 tracks; its decompiled pelvis
  `(58.747, 0.977, -2.04)`, spine `(59.827, 0.978, -2.047)` and head
  `(86.312, -0.505, -0.435)` match `primary_idle.dmx` exactly. The full
  `shiv.vnmskel_c` is 14586 bytes and contains `tail_0..tail_5, tail_end`.
- **Full pass.** 138 gameplay clips are present; 107 have a matching Werewolf
  source clip, 31 are skipped (30 have no source clip and `ui_hero_select` has
  no keyed frame range), 0 failed. The installed VPK has 138 clips, the model,
  and no `vnmskel_c` (sha256 `ba6dbf52948a10bce835dab729b45faa16a305a0a41e5a5d82df358784109b1f`).
- **Gate.** The 03:50 CSDK preview files remain untouched and pinned by
  `tools/tail_vnmclip_gate.py`; they are the preview acceptance witness, while
  the 147-track files are the gameplay compile.

## Not checked

- A real click on every tile in a live Blender UI; the automatic pass is driven
  directly in the headless probe.
- A full 100+ clip Shiv pass through the timer in a visible window. The queue and
  per-clip write are proven; the timer cadence is not timed visually.
- The owner's 03:50 ModelDoc preview is the acceptance witness; the gate pins
  those bytes rather than re-rendering them.
- The owner's in-game visual for the installed 147-track VPK; the decompiled
  147-track/pose evidence is available, but the game window is not observable
  through the tools in this session.
- The installed VPK must continue to exclude `vnmskel_c`; it carries the clips
  and model.
