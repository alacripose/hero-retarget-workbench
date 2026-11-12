# Hero Retarget Workbench

A Blender 5.4 addon and small Python core for porting a custom model onto a
live Deadlock hero.

The hero is always taken from the current live game with Source 2 Viewer. The
addon handles the custom model, fitting, retargeting, and materials. CSDK13 is
the compiler. The hero vmdl is not parsed, rebuilt, or edited: it is copied
byte-for-byte to the compiler handoff.

## Public landing page

The public page is [landing/index.html](landing/index.html). It is the family
web-dark dossier for the addon: the live-build workbench, the measured Haze
readings, the hard boundaries, and the install path. The native Blender panel
keeps Blender's own controls.

## What is here

| Path | Purpose |
|---|---|
| `blender/hero_retarget_workbench/` | Blender addon: hero picker, custom import, collection-scoped parts, per-slot materials, fit, retarget, stage, compile |
| `forge/` | Live path detection, S2V wrapper, axis transforms, name matching, staging, compiler invocation |
| `tools/project.py` | Command surface: `doctor`, `heroes`, `extract`, `stage`, `compile`, `gate`, `status`, `selftest` |
| `tools/build_addon.py` | Build the self-contained addon zip for Blender's Add-ons installer |
| `tickets/` | Work contracts and acceptance evidence |
| `ledger/` | Append-only command/evidence rows and gate state |
| `STATUS.md` | Generated capability and gate state; never hand-edited |

## Requirements

- Deadlock installed through Steam (currently observed build **6861**, version
  date **Nov 09 2026**).
- Source 2 Viewer CLI, selected in the addon's **Setup** panel.
- Blender 5.4 with **PulseSrcOps** enabled (DMX import/export) and SourceIO
  available (Source 2 assets). Observed: PulseSrcOps 2.1.2, SourceIO 5.5.2.
- A reduced CSDK13 install with `game/bin/win64/resourcecompiler.exe`, selected
  in the addon's **Setup** panel.
- BLAKE3 1.0.11 for proof identity and stage evidence. The built addon carries
  the vendored Windows extension; the checkout install is declared in
  `requirements.txt`. There is no SHA-256 fallback for new proof identity.

The addon stores the Deadlock install, Source 2 Viewer CLI, CSDK13 root, and
workspace on the scene. They are saved in the `.blend`; use **File → Defaults →
Save Startup File** to make them the default for new files. No machine-specific
folder is a built-in default. The headless `tools/project.py` command still
accepts `DEADLOCK_GAME`, `S2V_CLI`, `BLENDER`, and `CSDK13_ROOT` as explicit
overrides.

## Build and install the Blender addon

The addon can be installed without keeping this checkout. Build a self-contained
zip:

```bash
python tools/build_addon.py
```

The builder reads the version from `bl_info` and writes
`dist/hero_retarget_workbench-<version>.zip`. The archive carries the `forge/` core,
so the installed addon does not import from the checkout. Runtime files go to
Blender's user data directory.

In Blender 5.4, open Preferences → Add-ons, choose **Install from Disk**, and
select the zip. Enable **Hero Retarget Workbench**, then enable **PulseSrcOps**.
SourceIO is needed only for compiled Source 2 assets. The live DMX path does not
use it.

For development from this checkout, add `blender/` as a script directory instead;
the addon then uses the checkout's `forge/` package and writes under the checkout.

The sidebar is in **3D Viewport → Sidebar → Deadlock**.

### Set the tool paths once

1. Open the **Setup** subpanel.
2. Set **Deadlock install** to the Steam `Deadlock` folder, **Source 2 Viewer**
   to `Source2Viewer-CLI.exe`, and **CSDK13** to the folder containing
   `game/bin/win64/resourcecompiler.exe`.
3. Press **Detect installed** to fill any blank field from Steam, `PATH`, or the
   environment. A value you set is never replaced by another install.
4. Save the `.blend`. To apply the same paths to every new file, use
   **File → Defaults → Save Startup File** after setting them.

The Setup fields are scene properties, not a launcher script. A teammate with a
newer Deadlock build or a different drive updates the fields in their own file.

## Continuous integration and releases

`.github/workflows/ci.yml` runs on every push to `main`, every pull request,
and every version tag. It runs the unit tests, builds the addon zip, and uploads
the zip as a workflow artifact on Windows with Python 3.13.

A tag such as `v0.2.5` also runs the release job after the test job. The job
checks that the zip version matches the tag, then creates or updates the release
with `hero_retarget_workbench-<version>.zip` attached. A rerun replaces the asset
rather than leaving the release without a zip.

```bash
git tag v0.2.5
git push origin v0.2.5
```

The tag must match `bl_info["version"]`. The workflow rejects a mismatch before
it publishes anything.

## Workflow

1. **Detect Live Build** — uses the paths from Setup and lists every hero
   declared by the live build through S2V. On build 6861 this is 67 entries
   across `heroes_staging` and `heroes_wip`; 63 have body models. Four
   in-development entries declare a model path that is not in the build. S2V
   runs in a background thread.
2. **Extract Hero** — runs S2V on the selected hero and inventories the
   extraction. S2V's `-d` output includes the source `haze.vmdl` and the model
   clips. If a particular extraction has no vmdl, select the one from your S2V
   extraction with **Choose vmdl**; it is copied untouched, never synthesized.
3. **Import Hero Skeleton** — imports the live body DMX with PulseSrcOps.
4. **Import Custom Model** — glTF, GLB, FBX, OBJ, or DMX.
5. **Fit to Hero** — optional axis transform and uniform/height scale. Weights
   are never multiplied by the axis matrix.
6. **Scan Bone Map** — exact names, declared aliases and normalized names are
   matched. Every unmatched weighted group is a row: choose a target, mark it
   extra, or ignore it. The addon does not guess a nearest bone.
7. **Skeleton** — rename a custom bone and its matching vertex group, align a
   rest bone to the hero bone, align all mapped bones, copy the hero pose, or
   nudge the active pose bone. Renames refuse an occupied name before changing
   either the rig or the group.
8. **Compare** — splits the viewport and creates local views: hero body on the
   left, custom mesh on the right, both driven by the target rig when bound. A
   preview action can be applied to both rigs.
9. **Solve & Bind** — `HYBRID` uses mapped custom weights as a prior, samples
   the hero surface near the mesh, and uses mapped bone envelopes for tails,
   wings, hair and other geometry outside the body. `CUSTOM` and `ENVELOPE` are
   separate methods. Extra bones can be folded, kept as new hero-rig bones, or
   dropped. The solve is chunked on a timer, not one blocking `DATA_TRANSFER`.
10. **Mint Axis Proof** — records the weight artifact with BLAKE3, the claim,
    origin, evidence, tick span, world digest, presenter, ticket and named checks
    (coverage, normalization, influence limit, bone map, binding, extra bones,
    deformation). Export refuses a stale, unchecked or refused proof.
11. **Parts & Materials**: a custom import creates a collection for its
    objects. Choose that collection (or the active collection), press **Scan
    parts**, select a row and press **Use part**. Choose the **Source** object
    (usually the hero body), press **Scan slots**, then select one source slot
    and one part slot. **Assign selected material** replaces that part slot;
    **Append as new slot** adds one; **Clear selected slot** removes one and
    remaps face indices. There is no all-slot material copy. Fit, weights,
    materials, and export read the active part; the panel never substitutes the
    largest imported mesh.
    The material root is a content root: it must contain the
    `models/**/materials/*.vmat` tree and the texture images those materials
    reference. Staging preserves relative paths and copies only material
    assets, not notes, JSON, model clips, or arbitrary files.
12. **Export & Stage** — exports a Source 2 DMX and copies the selected vmdl,
    every extracted model clip, the replacement DMX, and the selected material
    tree into a CSDK13 handoff. The vmdl hash is recorded and checked after
    staging. `stage.json` records material and texture counts separately.
13. **Compile with CSDK13** — runs `resourcecompiler` in a background thread.
    The stage is copied into a unique temporary
    `content/citadel_addons/dmf_build_<addon>_<random>` folder, compiled with
    `resourcecompiler.exe -nop4 -f -game <CSDK game/citadel> -i
    citadel_addons/<build>/<vmdl>`, and both the temporary content folder and
    its `game` counterpart are deleted in `finally`. Only compiled `_c` files
    (`.vmdl_c`, `.vmat_c`, `.vtex_c`, ...) are copied back under
    `<stage>/compiled/<addon>/`. A failed compile keeps the prior compiled
    output and leaves no source mirror behind.

## Commands

```bash
python tools/build_addon.py
blender -b --factory-startup --python tools/blender_workbench_probe.py -- --report artifacts/receipts/hero-retarget-workbench-workbench.json
blender -b --factory-startup --python tools/blender_zip_probe.py -- --zip dist/hero_retarget_workbench-0.2.5.zip --report artifacts/receipts/hero-retarget-workbench-zip.json
python tools/project.py doctor
python tools/project.py heroes
python tools/project.py extract --hero haze --out artifacts/extractions/haze
python tools/project.py stage --help
python tools/project.py compile --help
python tools/project.py gate
python tools/project.py status
python tools/project.py selftest
```

`stage` needs the real S2V vmdl, the target DMX, and the replacement DMX:

```bash
python tools/project.py stage \
  --extraction artifacts/extractions/haze \
  --vmdl artifacts/extractions/haze/haze.vmdl \
  --target-dmx artifacts/extractions/haze/haze_body.dmx \
  --custom-dmx artifacts/custom/haze_body.dmx \
  --target-dmx-relative models/heroes_staging/haze/haze_body.dmx \
  --vmdl-relative models/heroes_staging/haze/haze.vmdl \
  --materials-root artifacts/haze-materials \
  --addon haze_port \
  --out artifacts/staged/haze_port
```

The output is `artifacts/staged/<addon>/content/citadel_addons/<addon>/`. The
vmdl there is byte-identical to the input. `stage.json` records both hashes and
`vmdl_modified: false`. Stage copies the rest of the S2V extraction (clips,
skin, and any assets the material roots do not cover) because the vmdl
references those files; the target DMX is the only model file replaced.

`--materials-root` and `--custom-materials-root` take a **content root**, not a
loose folder of vmat files: the relative path below that root is preserved. A
hero root typically looks like
`models/heroes_staging/haze/materials/*.vmat` plus its `.png`/`.tga` textures.
Only `.vmat`/`.vmat_c`, texture images, and `.vtex` assets are staged from that
root; unrelated files are ignored. Leave `--materials-root` empty to use the
hero extraction's material tree. Custom roots are overlaid after the hero
materials, so their paths win.

## Hard boundaries

- **No KV3 parser.** The live vmdl carries its own source data and attachments.
- **No vmdl reconstruction or metadata extraction.** A vmdl emitted by S2V (or
  supplied from the user's S2V extraction) is opaque input.
- **No CSDK13 hero files as source.** The CSDK is a compiler install, not the
  hero model source.
- **No custom interchange format.** The handoff is the real S2V vmdl, a
  replacement DMX, and copied `.vmat` files.
- **No `DATA_TRANSFER` retarget path.** The solver uses mapped custom weights,
  a hero-body KD-tree sample and mapped bone envelopes; the old modifier path is
  gone.
- **No legacy digest fallback.** New proof and stage identities are BLAKE3;
  SHA-256 is retained only where it is evidence from an older stage manifest.

## Observed evidence

- Live build 6861; 67 hero entries read from S2V's decompiled `heroes.vdata`;
  63 resolve to a body model. The list is not a staging-only or hand-maintained
  roster.
- WIP `heroes_wip` extraction: Abrams/Atlas emitted a 476,026-byte vmdl and 534
  DMX files.
- S2V extracted Haze into 458 DMX clips, 197 `.vnmclip` files, and a 269,939-byte
  source `haze.vmdl`.
- Real Haze body DMX imported headlessly: 120 bones, 33,366 vertices, 4
  materials.
- Addon registered and unregistered headlessly in Blender 5.4.0 Alpha; the
  export/stage probe copied the byte-marker vmdl unchanged and wrote a 30,553-byte
  replacement DMX.
- Staged Haze with 84 live material files and the full extraction; the vmdl
  SHA-256 was unchanged: `c54a0f0bede66c8a06eaa75eb5a4abde1ba4dadb80c7e6112bfc5d7b63d237a3`.
- CSDK13 compiled the staged vmdl: return code 0, 1 compiled, 0 failed, 3
  missing-material warnings; output 3,385,281-byte `.vmdl_c` at
  `artifacts/stage-final/compiled/haze_final/models/heroes_staging/haze/haze.vmdl_c`.
  The warnings are the same external dependency: `hazev2_headsmoke.vmat`
  references `models/npc/ghosts_passive/materials/gradient_trans.png`, which is
  not in the Haze extraction. The compiler still produced the model.
- 25 tests pass; `gate` passes all four structural checks (unit tests,
  compileall, no parser, no vmdl writes).

The compile was a pipeline probe using a cube as the replacement body. It proves
CSDK13 accepts the staged live vmdl and emits a compiled model; it is not a
finished custom character.

## 2026-11-12 — real-skinned-mesh supersession

**This supersedes the cube-only compile above for the end-to-end claim.** No
separate custom character mesh was present in the environment, so the probe used
the extracted Haze body DMX itself as the replacement mesh: a real skinned,
multi-material body, not a generated placeholder.

`tools/blender_real_probe.py` drove the addon through the active pipeline and
re-imported the exported DMX to measure what actually left Blender:

| Measurement | Source body | Exported DMX |
|---|---:|---:|
| Vertices | 33,366 | 33,366 |
| Bones | 120 | 120 |
| Vertex groups | 67 | 67 |
| Weighted vertices | 33,366 | 33,366 |
| Weight links | 53,834 | 53,834 |
| Material slots | 4 | 4 |
| Polygons | 59,203 | 59,203 |

All 67 vertex groups mapped by name; `unmatched` was empty. The four material
slots and their polygon assignment survived: slot 0 10,988, slot 1 8,136, slot
2 37,425, slot 3 2,654. Fit was identity. The source and exported weight sums
agree within 1e-5, and every vertex is weighted.

The exported replacement DMX is 10,430,338 bytes
(`8409a69154f4273cc899f544589fa45c94d184bd95cbfa6ff546fd76c6180a73`).
The staged vmdl remained byte-identical to the S2V extraction at
`c54a0f0bede66c8a06eaa75eb5a4abde1ba4dadb80c7e6112bfc5d7b63d237a3`,
with 654 extraction files and 84 material files. `resourcecompiler` returned
**0**: **1 compiled, 0 failed**, **5 warnings** (the real body adds the `body`
LOD to the four `body_lod1`..`body_lod3` warnings; all five are the same external
smoke-material texture). The output is
`artifacts/stage-real/compiled/haze_real/models/heroes_staging/haze/haze.vmdl_c`,
4,320,714 bytes,
`098b576fd382c6dccbb00d81f7f3327e3f0060cdc7fc1866b97c3958fbe07d60`.
The receipt is `artifacts/receipts/hero-retarget-workbench-real-parts.json`.

What this proves: the replacement mesh path preserves geometry, skeleton, vertex
groups, weights, material slots and polygon material assignment through a real
Source 2 DMX export and a real CSDK13 compile. What it does not prove: a
different custom character's bind-pose retarget. That remains the next real-mesh
unit.

## 2026-11-12 — manual workbench and Axis proof

The one-click queue was replaced by seven native subpanels: Setup, Source, Parts
& Materials, Compare, Skeleton, Weights & Proof, and Compiler Handoff. The proof
gate is BLAKE3 and the built addon carries the vendored `blake3` extension;
there is no SHA-256 fallback for new proof identity.

- 58 unit tests pass. `gate` passes all five checks; `selftest` rejects the
  planted KV3 parser.
- `blender_workbench_probe.py` passes: bone scan/rename/alignment, `FOLD` and
  `KEEP` extras, chunked weight solve, background job value, BLAKE3 proof
  `current`, changed bytes refused, export refused with `axis-proof-refused`.
  Report: `artifacts/receipts/hero-retarget-workbench-workbench.json`.
- The real Haze body probe passes with `CUSTOM` weights: 33,366 vertices, 120
  bones, 67 groups, 53,834 links and 4 materials survive the export; all seven
  comparisons match; vmdl unchanged. Proof digest
  `blake3:56ab5000287956d82687b0a0301f3402a2dcb580431b3a95fdaec6a26c5cfba8`.
  This run skipped compilation; the earlier real compile receipt remains
  separately recorded.
- The LOD/material probe passes: 3 LODs at 36,429 / 24,286 / 12,142 polygons,
  the custom `pbr.vfx` material survives on every LOD, and the vmdl is
  unchanged. Proof digest
  `blake3:d2bb9808ed071e4389f2c82fcdd31f3665f7e2f84b5724c7f7bd498863a78f81`.
- The real Haze stage now reports 84 material assets (70 textures) and 651
  extraction files; the material root is a closed `.vmat`/texture inventory,
  so notes and JSON are not staged.
- The real CSDK13 compile copied 36 compiled files back under
  `artifacts/stage-real/compiled/haze_real`: 1 `.vmdl_c`, 6 `.vmat_c`, 29
  `.vtex_c`. Both `dmf_build_*` temporary folders were removed from CSDK
  `content` and `game`; a failed compile leaves the previous output alone.
- The extracted-zip probe passes: 30 files, 8 panels, 41 operator classes,
  50 UI icons validated; `blake3` loads from the zip, not the checkout. The probe
  saves a `.blend` with the three Setup paths, reopens it, and reads the same
  values. Build: 273,624 bytes, SHA-256
  `360e1849bb682b3e81d2d6c1346f735be7fcfb256d46056e4c7e15fccf3bb686`,
  BLAKE3 `df6a347a8f2c2a1d4ec4021d00d54b67b737c459117a10c4da0e7e41ea93382d`.
- `blender_probe.py` scans a two-part collection, selects each active part,
  appends every hero slot, replaces one selected slot, clears one slot and
  appends it back, then stages the DMX. The exported active part retains the
  expected material slots.
- `blender_panel_gui_probe.py` opened a real Blender window, invoked
  `dmf.compare_split`, called all seven subpanels, and saved
  `artifacts/receipts/compare-panel.png`. `blender_parts_gui_probe.py` opened
  the Parts & Materials panel with three parts and three source slots at sidebar
  width and saved `artifacts/receipts/parts-panel.png`.
  The Compare panel was blank because `SPLITSCREEN` was not a Blender 5.4
  icon; `SMOOTH` and `NORMALIZE` had the same
  defect in Weights & Proof. All three now use valid icons.
- `impeccable detect` returned `[]` for the UI source.

Not yet witnessed by the owner: the split viewport and panel layout in the
installed build. The agent recorded a real-window probe and screenshot, but the
owner still needs to inspect it. A real custom furry/huge-asset fixture and
timer chunks under a live event loop are also open. PulseSrcOps warns that a few
decimated LOD vertices exceed four weight links; the base solve is capped at four
and this warning is in the LOD decimation/export path.
