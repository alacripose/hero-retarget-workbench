# TICKET-0021 — the older downloaded mods, and ports of them onto today's game

Status: implemented
Authority: `logs/authority/2026-11-14-oldmod-corpus.jsonl`

## Owner report (verbatim)

> no not the mayu I mean actual files from 2024 and 2025, stuff in actual
> different drives that haven't been compiled in over months

Earlier in the same pass:

> Shiv isn't the only hero with cloths, cloths have many different types across
> the modeldoc and roster, and as well lots of much older vpks have vmdls that
> won't import their cloths cleanly

## What was missing

The workbench could migrate one package at a time when the owner named it, but
it had no way to find out what was already on the machine. A port therefore
started from whatever file the owner remembered, and the cloth work had only
ever been measured on Shiv. Nothing recorded which old packages carry cloth
nodes, which hero each one targets, or whether an old render mesh list still
compiles against a 2026 hero.

## What changed

- `forge/oldmods.py` walks given roots and produces a corpus. Unpacked
  `citadel_addons/<name>` trees are read as source; `*.vpk` files are read by
  their directory tree only (extension → directory → file name, CRC, archive
  index, offset, length). No entry is decompiled and no vmdl text is written.
- Hero attribution comes from the model path
  (`models/heroes_staging/<slug>/`, `heroes_wip`, `heroes`), with version and
  backup suffixes removed (`kelvin_v2/kelvin_july.vmdl` → `kelvin`).
- Cloth types are read from each source vmdl with the existing
  `modeldoc.cloth_physics_sections`, so a corpus reports the actual section
  classes rather than assuming `Softbody` and `PhysicsJointList`.
- Engine content is excluded: `pak0*`/`pak1*`, `shaders_*`,
  `*bakeresourcecache*`, and anything under `game/citadel`, `game/core`,
  `game/csgo_imported`. A VPK with no vmdl entry is not a mod and is skipped.
- `tools/project.py mods --root ... --since ... --until ...` prints the corpus
  and writes `artifacts/receipts/old-mods.json`.
- `update-addon --report` and `compile --report` append port evidence to one
  receipt (`artifacts/receipts/old-mod-ports.json`), including section action,
  old/output section hashes, cloth chain counts, and compile errors.

## Corpus found (2024-01-01 … 2026-01-01)

Roots: `D:/Users/alacrity/Documents`, `D:/Users/alacrity/Downloads`,
`D:/Games`, `D:/SteamLibrary`, `E:/SteamLibrary`, `F:/mods`,
`F:/Downloaded Files`, `F:/shploingus-mod-sources`.

- 223 packages: 58 unpacked addons, 165 VPKs; 1,920 engine paks excluded.
- 34 packages carry cloth/physics sections.
- Cloth types across those packages: `Softbody` 28, `PhysicsJointList` 31,
  `ClothShapeList` 5, `ClothProxyMeshList` 2. This is the roster-wide answer to
  "cloths have many different types", and three of the four types are not what
  Shiv's jacket uses.
- Hero-bearing 2025 packages include `the_janitor` (kelvin, wrecker, bebop),
  `haze_tac9` (haze), `mayu` (doorman), and downloaded VPKs for mirage, abrams,
  viscous, yamato, astro, chrono, warden and a low-poly haze.

## Ports performed

| package | hero | mode | sections | compile |
| --- | --- | --- | --- | --- |
| `haze_tac9` (2025-09) | haze | auto (old render list) | Softbody + PhysicsJointList inserted, RenderMeshList + MaterialGroupList replaced | **failed**, 11 errors: LODGroup names `body_lod1..3`, `haze_gun_l/r(_lod1..3)` that the old package does not ship |
| `haze_tac9` | haze | `--model live` | Softbody + PhysicsJointList inserted, live render list kept | **pass**, 1 file compiled by CSDK13 |
| `lowpolyhazev1withatail.vpk` (2025-05) | haze | auto | Softbody inserted, RenderMeshList replaced, 1 ClothChain, 14 materials, 12 textures | not compiled |
| `the_janitor/kelvin_july.vmdl` (2025-07) | kelvin | auto | no cloth sections in the old vmdl; 12 ClothChain in the merged model | **pass**, 1 file compiled by CSDK13 |

The old addon that "won't import its cloth cleanly" is not a parser problem: its
cloth sections transplant byte-identically (`old=` and `out=` hashes match) but
its render mesh list names LOD meshes that were never in the package, so the
compiler rejects the model. Keeping the live render list is the working port for
that family of addons, and that is the mode that compiled.

## Limits of this evidence

- The corpus lists VPK directories; it does not decompile them, so VPK rows have
  no cloth inventory until they are migrated.
- Section discovery covers top-level class names. A cloth node nested inside a
  section that is not named `Softbody`/`Cloth*`/`PhysicsJoint*` is only carried
  if that whole section is transplanted (RenderMeshList, MaterialGroupList), and
  the receipt reports the action rather than the contents.
- No ported cloth model was opened in Blender or in game; the evidence is the
  transplanted section hashes and a successful CSDK13 compile.
- `cloth_chains` is counted in the merged vmdl, so it includes chains the live
  model already had. It is not a count of chains added by the old package.
