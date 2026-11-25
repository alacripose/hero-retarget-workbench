# 2026-11-24 — Scout's mesh was never missing; the DMX was

Owner correction, verbatim: *"the mesh for scouts model exists on disk"*.

A prior note and the app said the port had no mesh because `scout_anims/ref.smd` carries no `triangles`
block. That was true of the reference SMD and false as a statement about the port: the mesh exists three
ways beside it under `F:/Documents`, and the app's `mesh-not-built` refusal was wrong. It is now
`mesh-not-converted`.

## Measured on disk

| file | bytes | what it is |
| --- | --- | --- |
| `scout.mdl` | 910,028 | compiled Source 1 model |
| `scout.vvd` | 529,152 | vertex data, `IDSV` version 4 |
| `scout.dx90.vtx` | 311,996 | index/draw data |
| `scout.dx80.vtx` | 316,585 | the DX8 variant of the same |
| `scout.obj` | 1,055,705 | plain geometry: **8,261 vertices, 7,814 faces** |
| `scout.phy` | 19,162 | collision hull |
| `scout.qc` | 124,513 | the QC that built the model |
| `scout/*.vtf` | 15 files | textures (blue/red/invun/zombie variants, head, hands, normal maps) |

The OBJ's groups name the parts directly — `scout_red`, `scout_head_red`, `eyeball_l`, `eyeball_r`, and
repeated `scout_red` body groups — so the geometry is present per part, not collapsed into one blob.

## What is still true about the gap

There is **no Deadlock mesh**: no mesh DMX, no `.vmdl` naming one, and no `.vmt` beside the 15 `.vtf`
files (a Deadlock model needs material definitions, and the port ships textures without them). So the
conversion is the open work, not the geometry: Source 1 MDL/VVD/VTX and OBJ → mesh DMX → `RenderMeshFile`
in a `.vmdl` bound to `models/heroes_wip/scout/dmx/mesh/scout_skel.dmx`.

## Why the old reading was wrong

`forge.scout.scan_sources` counts SMDs under `scout_anims/` and `_anims/` and the `.mdl` at the root; the
app's mesh step was written from `ref.smd`'s missing `triangles` block alone. One file's structure is not
evidence about the model. The app now reads the port's own mesh files (`MESH_FILES` in
`popit_apps/scout_port/server.py`) and reports what it finds.

## The app now says

Step `mesh`, state `ready`, refusal `mesh-not-converted`, detail:

> scout.mdl 910,028 B, OBJ 8,261 verts / 7,814 faces, 15 VTF textures; Source 1 model present, mesh DMX not built

Probe **12/12**, including a new `mesh-sources` check that the refusal is `mesh-not-converted` and the
counts are non-zero. `tests/test_scout_port_app.py` covers both branches: a synthetic workspace with
`scout.mdl` + OBJ + textures reports `ready`/`mesh-not-converted` with its vertex and face counts, and an
empty workspace still reports `blocked`/`mesh-not-built`.
