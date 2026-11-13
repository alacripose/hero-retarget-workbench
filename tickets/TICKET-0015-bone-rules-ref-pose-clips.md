# TICKET-0015 — Rule-based bone mapping, live ref pose, clip import

**Owner request, verbatim:** *"the next step for the bone remapping work is the
regex style bone mappings auto rules, so when I map something like elbow_L to map
to say arm_lower_L it knows that elbow_r for example would map to arm_lower_r and
provide a smart auto rules panel so mapping can be done faster instead of one
bone at a damn time. as well, oftentimes models will import in a t-pose instead
of a ref pose so there needs to be a way to see as the bones get mapped you can
see where they move into the ref pose in real time or the animation in the
animation split view. Also it needs to be able to import the ag1/ag2 clips and
animations automatically so if someone wants to bulk edit animations separately
… like with hero models that have custom tails but no tail animations on the
heroes normally"*

Also in the same message: *"do not dishonestly frame missing functions as 'the
next step' do not invent ephemeral scratch files that dissapear making the
projects unable to progress or debug your work and additionally … when I import
my own custom mesh the mesh gets named from stuff from the mayu when none of what
this one is is the mayu"*.

Authority record: `logs/authority/2026-11-13-bone-rules-ref-pose-clips.jsonl`.

## Contract

1. **One row teaches the rest.** A typed target on a side-suffixed row learns a
   side rule and immediately answers the opposite-side row. Rules only suggest:
   an existing mapped row is never overwritten, and a suggested target must
   already exist on the hero skeleton.
2. **A regex rule** covers names that share no side token; the panel lists every
   stored rule with an on/off switch, and a learned rule is edited or removed
   like any other.
3. **The ref pose is visible while mapping.** The preview writes the hero's rest
   orientation onto every mapped custom bone without editing the rest pose or
   adding keys, so split compare shows both models in the hero's stance. The
   panel reports the source stance (T, A or arms-down) and can clear the pose.
4. **Clips import in bulk.** Scan a clip folder, import its animation DMX onto
   the hero rig as actions one file per timer step, then rename, preview or
   remove those actions in bulk. `vnmclip` files are listed and paired, never
   opened: this tree decodes no compiled game data.
5. **A port does not inherit the previous port's names.** Imported parts are
   named from their own file; a stale hero/addon/vmdl prefix is dropped and the
   part word (body, head, hair) survives.

## What this build does not do

- **Clip export is not implemented.** Importing, renaming, previewing and
  deleting clip actions is built; writing those actions back out as DMX is not
  wired into this panel, and nothing here claims otherwise. The panel says so in
  the same words.
- `vnmclip`/`vnmskel`/`vnmgraph` are classified by filename only. No compiled
  game data is parsed.
- The ref pose is a pose, not a retarget: it does not move the hero rig, and it
  does not bake anything.

## Evidence

- `tests/test_bonerules.py`, `tests/test_posematch.py`, `tests/test_clips.py`,
  `tests/test_naming.py` — 44 tests.
- `tools/blender_bone_rules_pose_probe.py` — builds a T-posed source rig and an
  A-posed hero rig; proves the mirror fill, the rule fill, T/A stance, an exact
  ref-pose rotation match (0.0 error across every mapped bone), heads kept in
  place, a clean clear, and the import rename.
  Receipt: `artifacts/receipts/bone-rules-pose.json`.
- `tools/blender_zip_probe.py` — 0.4.0 installs from the zip: 15 panels, 65
  operators, icons valid, GUI-pick resolution and rejection unchanged.
- `tools/blender_sidebar_gui_probe.py` with `--enable-event-simulate` — the
  real sidebar, scrolled to Skeleton, showing the AUTO RULES section with a
  learned `elbow* -> arm_lower*` row and the REF POSE section with its Show
  toggle. Render: `artifacts/ui-pass/sidebar.png`, crop
  `artifacts/ui-pass/skeleton-new.png`.
