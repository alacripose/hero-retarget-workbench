# TICKET-0028 — Custom cloth chains, tail blending, and automatic AG1/AG2 clips

**Status:** implemented in 0.9.0; gate, custom probe, clip export probe, and installed-zip probe pass.
**Owner:** ala
**Opened:** 2026-11-14

## Requirement

The owner's request, verbatim:

> yes in the modeldoc when someone wants to use custom skeleton bones for stuff they replace the normal skeleton (not the vnmskeleton which isn't needed in the output mod vpk) with the custom one. Read the modding pages docs that I keep giving you instead of skimming it

Earlier in the same request:

> https://deadlockmodding.pages.dev/modding-guides/Custom-animation-VmClip-guide how many times do i have to give you this page for you to read in full

The cloth ask was: custom cloth chains must be grabbed from the imported custom-model
armature at whatever viewport size/scale it has, joined to the hero rig, with a
section choosing the new parent bone. The animation ask was: a custom-tails section
choosing a specific tail armature for experimental clip blending, and an Animations
page that scans AG1/AG2 clips and bakes them for mods without requiring a clips
folder.

## Sources read

- `https://deadlockmodding.pages.dev/modding-guides/Custom-animation-VmClip-guide`
  (full page): scene FPS, IK Copy Location/Rotation, visual-key bake and clear,
  DMX Binary 9 / Model 22, `.vnmskel` decompile into ModelDoc's Clips folder,
  Simple Animations, clearing `NMSkeletonList`/`AnimGraph2List`, **Tools > Make
  Default Animgraph2**, clip preview filtering by skeleton, and packing
  `vnmclip_c` but never `vnmskel_c`.
- `https://wiki.divineskins.gg/en/docs/deadlock/models/cloth`: custom chain bones
  start at the parent hero bone, the new skeleton is loaded by replacing the
  Skeleton node from the DMX, then a ClothChain node is added, Twist Relax/goal
  strength are set, and the model is compiled.
- `https://wiki.divineskins.gg/en/docs/deadlock/models/jiggle-bones`: custom bones
  that skin nothing are discarded on export, so a chain must carry the cloth's
  weights.

## Contract

1. **The custom armature is the source, the hero armature is the output.** A custom
   chain is scanned from `settings.cloth_source` (an armature supplied by the user)
   or from the hero skeleton. Both are read through the same bone-chain rules.
2. **Join preserves the viewport transform.** Each source head/tail is converted
   with `custom.matrix_world` and then `hero.matrix_world.inverted()`; the new
   hero bones are never moved and existing hero bones are never overwritten. The
   probe's world-space difference is `0.0`.
3. **The new parent is explicit.** `DMF_ClothChain.parent` is chosen on the Cloth
   page and applied when the chain is joined. If it is empty, the nearest hero
   bone is suggested by `scan_chains` and shown before joining.
4. **The custom mesh is rebound only when that is provable.** A custom mesh is
   switched to the hero armature only when every weighted vertex group exists on
   the hero armature. Otherwise the build refuses and names the missing groups
   instead of silently dropping weights.
5. **Blender cloth is preview only; Source 2 gets a proxy.** The Cloth modifier
   stays for viewport preview. `dmf.mark_cloth_proxy` writes PulseSrcOps
   `CLOTHPROXY` and a `cloth_enable` group, and `dmf.build_chain_cloth` does that
   for the row's mesh.
6. **ModelDoc owns the skeleton replacement and ClothChain node.** The addon
   exports the joined hero rig; ModelDoc replaces the Skeleton node from that
   export, adds the ClothChain node, and compiles. The `.vnmskel` is a ModelDoc
   input and is not packed into the output mod VPK.
7. **Clip discovery needs no folder.** `forge.clips.clip_roots` searches the
   extraction, the body/staged model folder, and the vmdl's own folder for
   `clips`, `anims`, `animgraph`, `vnmclip`, and token-named folders.
   `dmf.scan_clips` finds the `.vnmskel` there when present and classifies every
   DMX.
8. **AG2 and AG1 write to different folders.** `AG2` writes
   `<folder>/clips/<clip>.dmx`; `AG1` and `UNKNOWN` write
   `<folder>/anims/<clip>.dmx`. The PulseSrcOps export subdir follows that same
   choice; a clip cannot be exported into the wrong graph folder.
9. **Baking is visual and frame-preserving.** `dmf.bake_clips` walks imported rows
   on a timer, bakes `only_selected=False` with visual keying over the action's
   own range, clears only the addon's IK constraints, then writes a Model 22 DMX.
   The original scene FPS and frame count are the inputs to that bake.
10. **Tail transfer is explicitly experimental.** The tail section selects an
    armature, scans its bones against the hero's source tail, and blends the
    hero action onto that armature in local space with an editable weight. It
    writes one action per tail rig; it is not a claim about engine tail physics.
11. **The compiled clip is still ModelDoc's job.** The addon writes DMX. It does
    not claim to compile `.vnmclip_c`, and the UI says to use ModelDoc's
    **Make Default Animgraph2** and pack the clip, never the `.vnmskel`.

## Out of scope

- Creating ModelDoc ClothChain or Skeleton node text, or editing the opaque vmdl.
- Compiling `.vnmclip`/`vnmclip_c` or running an animgraph compile.
- In-engine cloth behaviour, tail physics, or a real game compile.
- Changing the hero's existing bone transforms during a chain join.

## Evidence

- `tests/test_clips.py`, `tests/test_tails.py`, `tests/test_cloth_suite.py`,
  `tests/test_ik.py`: 33 passed.
- `tools/blender_custom_chain_tail_probe.py`: 5/5 custom-chain, join, custom-mesh
  cloth, bake and tail checks; join world-space difference `0.0`.
- `tools/blender_clip_export_probe.py`: 9/9, including an AG2 DMX under `clips`,
  an AG1 DMX under `anims`, and a reimport with matching 20-frame length.
- Real S2V Shivi extraction: auto scan found 276 rows (138 DMX + 138 vnmclip),
  138 paired, all AG2, without a clips folder being entered.
- PulseSrcOps proxy probe: `CLOTHPROXY`, `cloth_enable`, remap `0..1`.
- Installed 0.9.0 zip: 10/10 install/enable/surface/open checks.

## Not checked

- ModelDoc Skeleton/ClothChain nodes, `.vnmclip_c` conversion, and in-game cloth
  or tail behaviour.
- A real hero rig with a custom chain: the chain/join/cloth/tail probe is a
  synthetic custom rig with a two-bone chain and a two-bone tail.
- The GUI page draw probe did not execute its page draws in this headless run;
  the installed-zip probe confirmed registration and the sidebar, not every
  widget's pixels.
