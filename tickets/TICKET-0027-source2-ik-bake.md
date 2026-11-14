# TICKET-0027 — Source 2 IK targets and baked animation clips

**Status:** implemented in 0.8.28; gate and installed-zip probe pass.
**Owner:** ala
**Opened:** 2026-11-14

## Requirement

The owner's request, verbatim:

> okay so latest s2v release/dev builds have functioning source 2 ik which has been a pain point for animations systems https://deadlockmodding.pages.dev/modding-guides/Custom-animation-VmClip-guide so part of the animation work alongside stuff like the putting tail animations and bones on heroes who don't have them needs to include that for baked animations

## Why this exists

Source 2 IK chains solve a hero's limbs from target bones outside the pelvis
hierarchy (`Ik_Hand_L`, `Ik_Foot_R`, `Ik_Elbow_L`). Blender imports the target
bones' local transforms; it does not import the engine's IK solve. A clip that is
exported without constraining and baking those targets therefore reaches
ModelDoc with the limbs following the wrong motion, or not following at all.

Source 2 Viewer 21.1 now keeps IK chains and the legacy IK control rig in a
decompiled model, and plays AnimGraph 2 IK in its viewer. That is the source-side
half. The community VmClip guides describe the Blender half: Copy Location and
Copy Rotation from each IK target to the real limb, bake with visual keying, and
clear the constraints before exporting DMX.

## Contract

1. **Targets come from the imported skeleton, never from the vmdl.** A bone is an
   IK target when its leading token is `ik` or `iktarget`; `thighbone_ik` is not.
   The vmdl remains opaque and is not parsed for chains or metadata.
2. **A suggestion is a suggestion.** `forge/ik.py` matches the target's limb word
   and side (`Ik_Hand_L` → `hand_L`, `Ik_Elbow_R` → `lower_arm_R`,
   `Ik_Foot_L` → `ankle_L`). Weapon/prop targets are listed but not given a bone:
   the guide uses Child Of on an object for those. Every row's target is editable.
3. **Apply is explicit and idempotent.** `dmf.apply_ik` adds exactly two
   constraints per row — `COPY_LOCATION` and `COPY_ROTATION`, named `DMF IK Loc`
   and `DMF IK Rot` — and replaces its own previous pair. It does not touch a
   user's constraints.
4. **Bake uses visual keying over the action's own frame range.** `dmf.bake_ik`
   bakes every pose bone (`only_selected=False`) with `use_current_action=True`,
   so constraints are evaluated into keys, then removes only the `DMF IK ` tagged
   constraints. The action keeps its name and the clip row still points at it.
5. **Extra bones are in the same bake.** Bones copied from a custom rig by the
   Weights page's `KEEP` policy (a tail, for example) are pose bones on the hero
   armature; the `only_selected=False` bake writes their channels too. No separate
   tail bake exists.
6. **An unbaked IK action cannot be written out.** `clipops.write_action` refuses
   with `clip-export-unbaked-ik` while any `DMF IK ` constraint remains, because a
   DMX cannot carry a Blender constraint.
7. **The clip workflow is unchanged.** Import, preview, write and the timer queue
   stay as they were; the new work is only the IK constraint/bake step before the
   write.

## Out of scope

- Creating ModelDoc `IKChain` nodes, compiling `.vnmclip`, or copying ID events.
  Those remain ModelDoc/CS2 Workshop Tools work.
- Child Of constraints for weapon/prop targets; the row is listed and left for the
  user.
- Parsing the decompiled vmdl or `vnmikrig` data. The source boundary still holds.
- A separate tail-bone builder: the existing `KEEP` extra-bone policy supplies
  the bones, and this ticket only makes sure the bake includes them.

## Evidence

- `tests/test_ik.py` 7 tests: leading-token recognition, same-side hand, elbow →
  lower arm, foot → ankle, weapon blank, scan order, and no cross-side match.
- Installed 0.8.28 zip probe: 17/17, including
  `ik-scan-suggests-limb` (`Ik_Hand_L` → `hand_L`),
  `ik-constraints-applied` (2 constraints), and
  `ik-bake-keeps-pose-and-clears` (bake FINISHED, 0 tagged constraints left,
  pose matrix difference 0.0).
- Screenshot `artifacts/receipts/ik-0.8.28.png` shows the Animations page section
  with the target row and the bake result.

## Not checked

- A real hero skeleton and a real clip. The probe uses a five-bone synthetic rig
  with one hand target and one tail bone; no game compile was run.
- ModelDoc's IKChain nodes or the in-game limb result.
- A custom tail model through the Weights `KEEP` path; its bones would be baked
  by the same operator, but that path was not exercised here.
