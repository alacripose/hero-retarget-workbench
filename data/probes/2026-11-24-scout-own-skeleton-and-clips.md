# 2026-11-24 — Scout's own skeleton, and his first clips on it

The two steps the Scout Port application refused — `skeleton-not-built` and then the clip bake behind
it — are now built with the forge, on the port's own rig. This note records what was built, what was
measured, and what is still refused.

## Why the skeleton was the block

`F:/Documents/scout_anims/ref.smd` carries the port's rig as Source 1 data: a `nodes` table of 78 names
and parent indices, then one `skeleton` block of local position and Euler rotation per bone. A Deadlock
hero needs a skeleton DMX and a `.vnmskel` over it, and neither existed. Every downstream step — clip
bake, animgraph, pack, hero registration — was refused behind that one missing file rather than by its
own work.

The values in that block are **local**: composing them parent-to-child with `R = Rz·Ry·Rx` puts the
pelvis at y≈47.3 and the head at y≈73.5 with the hips below the pelvis, which is the port's own
anatomy. That composition is what `forge.portskel` writes, so the DMX is a transcription of the rig,
not a retarget of it.

## What was built

- `forge/portskel.py` — `read_reference` (SMD → joints with parent and child indices), `write_skeleton_dmx`
  (a `DmeModel` with one `DmeJoint` per bone, joint order and names intact, axis system `3/1/0` as the
  live skeletons carry), `write_vnmskel` (a `CNmSkeletonDocument` over that DMX, every bone in LOD 0 plus
  a `FullBody` and `UpperBody` mask), and `write_clip_template` (one `DmeQuaternionLog` channel per joint,
  named `<joint>_o`, so a bake writes into a rig that is Scout's).
- `tools/scout_skeleton.py` — `build`, `compile`, `verify` for the skeleton.
- `tools/scout_own_clips.py` — `template`, `bake`, `compile`, `verify` for clips. The port's SMD node
  names *are* the joint names, so the binding is by identity: no bone map, no hand-written table.
- `popit_apps/scout_port/server.py` — the clips step now reads the bake and compile receipts instead of
  reporting a generic `ready`.

## Measured

| step | reading | evidence |
| --- | --- | --- |
| skeleton build | 78 joints, root `bip_pelvis`, 43,236 B DMX, 5,559 B `.vnmskel` | `artifacts/scout-port-skel/models/heroes_wip/scout/` |
| skeleton compile | `OK: 1 compiled, 0 failed, 0 skipped` — 7,187 B `scout.vnmskel_c` | `artifacts/receipts/scout-skeleton.json` |
| skeleton verify | **78/78 bones** present in the decompiled resource, `m_sourceFilename = models/heroes_wip/scout/dmx/mesh/scout_skel.dmx` | `artifacts/scout-port-skel/verify/` |
| clip template | 78 orientation channels, `dmxconvert` accepts it | `artifacts/scout-own-clips/template.kv2.dmx` |
| clip bake | 4 clips, 76/76 nodes resolved, 207,960 B of DMX | `artifacts/receipts/scout-own-clips.json` |
| clip compile | **5/5** documents: skeleton + 4 clips, each 4,080–4,099 B compiled | same receipt |
| clip verify | 4 clips × **78 channels**, every joint present, all 4 compiled | `RESULT: PASS` |

The two aim-matrix clips report `0 moving channels` at 2 frames — their SMDs are poses, not motion, and
the receipt says so instead of counting them as animation. `AttackStand_PRIMARY` (21 frames, 22 moving
channels) and `PRIMARY_reload_loop` (20 frames, 28 moving) are the motion witness.

## What is still refused

- **The animgraph** — `scout_loco.vanmgrph` and the aim graph exist from the earlier slice and reference
  the frank-bound clips; they have not been re-pointed at these clips, and the live build reads
  AnimGraph 2, so the graph step stays `ready`, not `pass`.
- **The pack and the hero** — no VPK of this rig has been built, and no model names the graph, so
  `hero-not-registered` stands.
- **The model** — the port has no mesh SMD (`ref.smd` has no `triangles` block); a Deadlock model needs
  mesh DMX, which the port's compiled `.mdl` has not been decomposed into yet.
- **In-game** — nothing here was observed in a match. No client was launched for this slice; the earlier
  addon that did launch crashed the client and is disabled in `addons/` as `scout_animgraph_dir.vpk.disabled`.

## Reproduce

```
python tools/scout_skeleton.py build
python tools/scout_skeleton.py compile --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
python tools/scout_skeleton.py verify  --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
python tools/scout_own_clips.py template
python tools/scout_own_clips.py bake --clips PRIMARY_aimmatrix_idle PRIMARY_aimmatrix_run AttackStand_PRIMARY PRIMARY_reload_loop
python tools/scout_own_clips.py compile --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
python tools/scout_own_clips.py verify  --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
```

One trap worth keeping: `dmxconvert` rejects a **trailing comma** after the last element of an
`element_array` and reports it as `Expecting element type, didn't find it!` at the array's close, one
element type down the stack. `write_clip_template` therefore writes commas between channels only;
`tests/test_port_skeleton.py` fails if that comma comes back.
