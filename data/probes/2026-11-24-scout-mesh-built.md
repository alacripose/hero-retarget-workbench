# 2026-11-24 — Scout's mesh, model and materials, built and parsed back

The port's geometry became a Deadlock mesh DMX, a model definition and 15 material definitions. Every
number below was read back out of the file that was written, not from the build log.

## Where the format came from

The mesh DMX is keyvalues2 `format model 22`, the same encoding as the port's skeleton and clip
documents. Its element shape was copied from two real mesh DMXs, not invented:

- `content/models/biped_standard/dmx/mesh/biped_standard_model.dmx` (246,198 B) and
  `models/heroes_wip/frank/frank_frank_lod36.dmx` (1,959,924 B) were converted from binary to text with
  `dmxconvert -oe keyvalues2`, which gave the exact attributes: `DmeModel` → `DmeDag` → `shape DmeMesh`
  with `currentState`/`baseStates`, `faceSets` of `DmeFaceSet` (`faces` as corner indices terminated by
  `-1`, `material` → `DmeMaterial.mtlName`), and `DmeVertexData` with `vertexFormat`, `jointCount`,
  `position$0`/`normal$0`/`texcoord$0` plus their `*Indices` arrays.
- The skinned reference is frank's bind state: streams `position$0`, `texcoord$0`, `normal$0`,
  `tangent$0`, `blendindices$0`, `blendweights$0`, `texcoord$1`, with `jointCount` 4. `blendindices$0` is
  an `int_array` and `blendweights$0` a `float_array`; both index the model's `jointList`.

## What was written

`forge/meshbuild.py` reads the OBJ and the skeleton DMX, solves weights, and writes the DMX, the `.vmdl`
and the materials. `tools/scout_mesh.py` runs it, re-parses the output, round-trips it through
`dmxconvert`, compiles it, and writes `artifacts/receipts/scout-mesh.json`.

| artifact | bytes | parse of what was written |
| --- | --- | --- |
| `artifacts/scout-mesh/models/heroes_wip/scout/dmx/mesh/scout_body.dmx` | 2,461,515 | **8,261** `position$0`, **7,814** faces in 4 face sets, **78** joints, `jointCount` 4 |
| `artifacts/scout-mesh/models/heroes_wip/scout/scout_body.vmdl` | 510 | `RenderMeshFile filename = "heroes_wip/scout/dmx/mesh/scout_body.dmx"` |
| materials | 45 files | 15 `.vmt`, 15 `.vmat`, 15 `.png` |

**Weights.** The OBJ carries none, so `solve_weights` assigns every vertex the four bone segments nearest
to it, inverse-square weighted and normalized. The parse sums each vertex's four weights: **minimum 1.0,
maximum 1.0** across all 8,261 rows. `blend_index_max` is 57, so 58 of the 78 joints drive this geometry;
the other 20 have no vertices near them (fingers, toes, weapon helpers).

**Faces.** The OBJ's polygons are kept as polygons: `position$0Indices` holds 23,442 corners and
`-1` terminates each face, which is 7,814 × 3 — every source face is a triangle. The four OBJ groups
(`scout_red`, `scout_head_red`, `eyeball_l`, `eyeball_r`) become four face sets with two materials
(`scout_red.vmat`, `scout_head.vmat`).

## Independent parse by a Valve tool

`dmxconvert` (Dota 2 tool branch) converted the written DMX to binary and back:

```
binary: 916,004 B
positions:      8,261
corners:       23,442
faces:          7,814
blend weights: 33,044   (= 8,261 × 4)
```

That is a second reader agreeing with the first, on the same file.

## Compile

CSDK 13's `resourcecompiler.exe` (`modeldoc_utils.dll` present) compiled the model and all 15 materials:

- 16/16 documents: 1 model + 15 `.vmat`, `0 failed`.
- `game/models/heroes_wip/scout/scout_body.vmdl_c` **107,209 B**, blocks `MVTX` 91,645 B, `MIDX` 8,932 B,
  `MDAT` 2,396 B, `CTRL` 825 B, `RERL` 143 B, `RED2` 1,430 B, `DATA` 1,673 B, and 2 material refs
  (`scout_head.vmat`, `scout_red.vmat`).
- 15 `.vmat_c` beside it.

The one warning-free compile matters: the first attempts warned
`Mesh 'unnamed_1' referencing missing material ...`. The cause was the path root, not the material:
ModelDoc and the DMX material name both resolve from `models/`, so a leading `models/` doubled the path
(`content/models/models/heroes_wip/...`). Removing the prefix, in the `.vmdl` reference and in `mtlName`,
cleared it.

## One deliberate deviation from the brief

The brief asked for `RenderMeshFile` at `models/heroes_wip/scout/dmx/mesh/scout_skel.dmx`. That file is
the **skeleton** `DmeModel`; a `RenderMeshFile` is loaded as mesh geometry, so naming the skeleton there
cannot compile a mesh. The model therefore references `heroes_wip/scout/dmx/mesh/scout_body.dmx`, and the
skeleton stays where the `.vnmskel` already names it — `scout_skel.dmx` — with the mesh DMX carrying a
`DmeModel` whose `jointList` is the same **78** joints, in the same order, so the mesh binds to that rig.

## Textures

The port ships 15 `.vtf` and only 5 usable PNGs (`scout_blue`, `scout_head`, `scout_hands`,
`scout_hands_normal`, `scout_normal`). Those 5 are the `.png` the materials sample; the other 10 are 8×8
mid-grey placeholders written by `_placeholder_png`, so the materials compile. They are placeholders, not
the port's art.

## App

`mesh_state` now reads the produced files: it parses the DMX for vertices/faces/joints/weights, reads the
`.vmdl` for its `RenderMeshFile` target, and counts `.vmt`/`.vmat`. The step is `converted` with no
refusal only when the DMX parses, the model names it, and all 15 `.vmt` and 15 `.vmat` exist; anything
partly present is `mesh-partial` with the missing pieces named.

Live: `mesh converted — 8,261 verts / 7,814 faces, 78 joints, weights 1.0–1.0, 2,461,515 B DMX, 15 .vmt /
15 .vmat`. Probe **12/12** (`mesh-converted`), suite **407 passed**, `heredoc_audit` pass,
`agents_audit --index` 7/7.

## Not done

- No pack (VPK), no hero registration, no launch: `pack-not-built`, `hero-not-registered`,
  `not-observed` still refuse.
- No in-game observation of the mesh deforming, and the skeleton's own `.vnmskel` bone list was not
  re-compiled against this model.
- 10 of the 15 textures are placeholders.
