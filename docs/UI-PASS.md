# UI pass 0.16.4

The Workbench pages were built one at a time, and the check that every action has one home did not
exist. This pass adds the check, moves staging and compiling onto the Release page, replaces the hero
dropdown with a filtered list, and runs the family writing rules over every user-facing string.

The HIG sweep then rebuilt the shared page grammar: the panel header is the one page title, the body
starts with state and build, groups are separated by space, actions are worded buttons in rows of
two, chips are real buttons, and advanced panels stay folded. The full checklist and evidence live in
`docs/UI-HIG-SWEEP.md`.

## References

- Popit surface grammar: one named page header, one state/build line, flat labeled groups, text
  actions in rows of two, folded advanced groups, one message per page. Implemented in
  `ui_popit.py`.
- Landing family design: the alacripose landing page supplies the density and the label voice, not a
  palette. Blender's theme owns color.
- `impeccable` (Operate mode): scanability, native expectations, no wizard.
- `stop-slop` (github.com/hardikpandya/stop-slop) and `declauding`
  (github.com/oaustegard/claude-skills): no em dashes, no filler openers, no intensifier adverbs, no
  "not just" staging, no stock marketing words. `tools/ui_prose.py` enforces the shared set.

## Page parity

| Page | Panels | Actions |
|---|---|---|
| SETUP | DMF_PT_setup, DMF_PT_setup_tools, DMF_PT_setup_toolchains | `dmf.add_client`, `dmf.detect_paths`, `dmf.install_csdk`, `dmf.install_s2v`, `dmf.open_csdk_page`, `dmf.open_project_folder`, `dmf.refresh_clients`, `dmf.use_backport_client`, `dmf.use_client`, `dmf.use_toolchain` |
| SOURCE | DMF_PT_source, DMF_PT_source_files | `dmf.apply_model_name`, `dmf.browse_folders`, `dmf.choose_hero`, `dmf.detect`, `dmf.extract`, `dmf.fit`, `dmf.import_custom`, `dmf.import_hero`, `dmf.pick_vmdl`, `dmf.refresh_heroes` |
| PARTS | DMF_PT_parts, DMF_PT_parts_materials | `dmf.append_material`, `dmf.assign_material`, `dmf.clear_part_material`, `dmf.scan_materials`, `dmf.scan_parts`, `dmf.use_active_collection`, `dmf.use_part` |
| CLOTH | DMF_PT_cloth | `dmf.build_all_cloth`, `dmf.build_chain_cloth`, `dmf.import_hero_parts`, `dmf.join_cloth_chain`, `dmf.mark_cloth_proxy`, `dmf.scan_cloth` |
| SKELETON | DMF_PT_skeleton, DMF_PT_skeleton_bones | `dmf.add_bone_entry`, `dmf.align_all_bones`, `dmf.align_bone`, `dmf.clear_target`, `dmf.copy_pose`, `dmf.ignore_entry`, `dmf.mark_extra`, `dmf.nudge_bone`, `dmf.pick_bone_map`, `dmf.pose_clear`, `dmf.pose_preview`, `dmf.refresh_hierarchy`, `dmf.remove_bone_entry`, `dmf.rename_bones`, `dmf.scan_bones`, `dmf.select_hierarchy_bone`, `dmf.stop_rules` |
| RULES | DMF_PT_rules | `dmf.add_rule`, `dmf.apply_ik`, `dmf.apply_rules`, `dmf.bake_ik`, `dmf.blend_tail`, `dmf.blend_tail_all`, `dmf.build_tail_animation`, `dmf.clear_ik`, `dmf.clear_rules`, `dmf.learn_rules`, `dmf.load_tail_option`, `dmf.preview_tail`, `dmf.publish_tail_anims`, `dmf.remove_rule`, `dmf.rule_from_row`, `dmf.scan_ik`, `dmf.scan_tail`, `dmf.scan_tails` |
| ANIMATIONS | DMF_PT_animations, DMF_PT_animation_ik, DMF_PT_animation_tail, DMF_PT_animation_write | `dmf.apply_ik`, `dmf.bake_clip`, `dmf.bake_clips`, `dmf.bake_ik`, `dmf.blend_tail`, `dmf.blend_tail_all`, `dmf.build_tail_animation`, `dmf.cancel_clips`, `dmf.clear_clips`, `dmf.clear_ik`, `dmf.export_clip`, `dmf.export_clips`, `dmf.import_clip`, `dmf.import_clips`, `dmf.load_tail_option`, `dmf.prefix_clips`, `dmf.preview_clip`, `dmf.preview_tail`, `dmf.publish_tail_anims`, `dmf.scan_clips`, `dmf.scan_ik`, `dmf.scan_tail`, `dmf.scan_tails` |
| COMPARE | DMF_PT_compare | `dmf.apply_compare_action`, `dmf.compare_clear`, `dmf.compare_split` |
| WEIGHTS | DMF_PT_weights, DMF_PT_weights_manual | `dmf.assign_active_bone`, `dmf.limit_influences`, `dmf.mint_proof`, `dmf.mirror_weights`, `dmf.normalize_weights`, `dmf.remove_zero_weights`, `dmf.retarget`, `dmf.select_unweighted`, `dmf.smooth_active_group`, `dmf.verify_proof` |
| MODS | DMF_PT_mods, DMF_PT_update | `dmf.add_scan_root`, `dmf.backport_mod`, `dmf.create_mod_project`, `dmf.pick_old_vmdl`, `dmf.pick_old_vpk`, `dmf.port_mod`, `dmf.remove_scan_root`, `dmf.scan_mods`, `dmf.update_old_addon` |
| COMPONENTS | DMF_PT_components | `dmf.pick_component_vmdl`, `dmf.scan_components`, `dmf.stage_components` |
| RELEASE | DMF_PT_handoff, DMF_PT_handoff_paths, DMF_PT_release, DMF_PT_release_slot | `dmf.build_lods`, `dmf.clear_lods`, `dmf.compile`, `dmf.export_stage`, `dmf.install_pak`, `dmf.launch_game`, `dmf.pack_vpk`, `dmf.write_model` |

`python tools/ui_parity.py --check` fails on an action drawn on two pages, a page with no panel, or an
action drawn that no operator declares. `tests/test_ui_parity.py` pins the same result.

## 0.16.4 — filter chips keep their labels inside

- The Skeleton, Cloth, Animations and Mods filters now share `ui_popit.chips`.
  Each value is an enum button in a plain row; the old `grid_flow` inherited
  the panel's property split and moved the first chip's text into a label
  column, leaving an empty button beside it.
- Four choices draw as 2 by 2, five as 3 plus 2, and two as one even row. The
  labels stay inside their buttons at the narrow 782 px Workbench surface.
- Measured: `208` tests pass, `ui_parity --check` and `ui_prose --check` are
  zero; `artifacts/visual/ui-pass/{skeleton,cloth,animations}.png` show the
  labels inside their buttons at 782 px, and `artifacts/ui-pass/mods-collection.png`
  shows the same for `All 5`, `Folders 3`, `VPKs 1`, `Blends 1`.
- Zip probe: `0.16.4`, 68 files, 476,950 bytes, sha256
  `5ed33bdf15d304f4404dede4571636239319a94116752e1f62c9f781993ec396`.

## 0.16.3 — mods collections, last updated, and tool-release prediction

- **A mods root is a collection.** The scan now inventories immediate top-level package folders as
  well as unpacked `citadel_addons`. A folder is kept when it has a game content root, a game file
  suffix, a `.vpk`, or a model/script/sound/particle payload; empty `New Folder` shapes stay out.
  The live game's `pak01_dir.vpk` supplies the folder names and suffixes, with a bounded built-in
  fallback when the game is not installed.
- **Both Documents roots stay separate.** Scan-root rows show the last three path components, so
  `Documents/mods` and `Documents/Documents/mods` are distinguishable. The real two-root run found
  325 packages: 78 folders in the first root and 247 packages (229 folders, 18 VPKs) in the second.
  The 85 and 238 top-level directories include 7 and 9 empty or non-content folders.
- **Last updated and toolchain are visible.** Each package records its newest file timestamp and a
  predicted CSDK toolchain. The detail card shows both `Updated` and `Toolchain`; the Mods filter
  searches the toolchain value. Prediction uses releases of installed tools, not daily game builds.
- **A game is not a compiler.** `forge.installs.classify` no longer marks a full game with a shipping
  pak as a compiler host even when `resourcecompiler.exe` files were copied into it; a stale saved
  client row is cleared on scan. The newer game build `6861` is therefore not a toolchain, while
  CSDK `4192` and `6836` are.
- **Measured.** `208` tests pass; `ui_parity --check` and `ui_prose --check` are zero. The synthetic
  Mods probe passes `scan-count 5`, typed records, `toolchain-predicted {CSDK 6836}`, all filters and
  project creation. A real Blender scan completed with `325 packages: 307 folders, 18 VPKs, 0 blends,
  3 blend files, 1 cloth`; a 4.4 GB folder package required widening the row byte field from a
  32-bit integer.
- Zip probe: `0.16.3`, 68 files, 476,952 bytes, sha256
  `81a89ac9f98bcf2f3fecd6b19d8017e6e83068b7db029741e8ad798561601e53`.
- **Not checked:** the real scan was verified by receipt and log, not by a readable sidebar
  screenshot. The copied compiler files in the game install were not deleted.

## 0.16.2 — HIG sweep of the whole Workbench surface

- Page roots are the single title. The old page card repeated the header and, when hidden with
  `HIDE_HEADER`, left a pair of header arrows; it is gone. State and the compact Live/CSDK build line
  sit directly under the title.
- Sections are flat columns separated by space, not boxes inside boxes. Advanced Setup/Mods panels
  are nested under their page root, so `Update old addon` no longer appears above the Mods page.
- Actions are text buttons, one or two per row. Source's `Use model` no longer shares its row with a
  count; the skeleton ref-pose controls are two full buttons; odd counts leave a blank cell instead
  of stretching the last action across the page. `Pack & install` opens on Release.
- Filters are buttons, not enum labels left outside their value column. They wrap at the measured
  page width, and Hero/Custom rig are readable at both surfaces.
- Long lists size to their rows. The Source model list uses the model count instead of seven empty
  rows. Mods with no scan roots shows one Add folder action and hides date/scan controls.
- The narrow layout moves a long global status out of the header and into the page body below 650 px;
  errors stay complete. The toolbar keeps the page menu and version.
- **Measured.** `202` tests pass; `ui_parity --check` and `ui_prose --check` are zero. The pages
  probe draws all `26/26` page and child panels with no exceptions and imports a real hero (19 cloth
  chains, jacket/hair rows). Screenshots: `artifacts/ui-pass/pages/*.png` (960 px) and
  `artifacts/ui-pass/narrow/*.png` (640 px). Zip probe: `0.16.2`, 68 files, 473,535 bytes,
  sha256 `139edca2fe66fe42fd63fbf3c06d984a96d24fa46e97f491cac41d2962ad41bc`.
- **Not checked:** Blender's native file dialogs were not restyled; the native sidebar's minimum
  width was used for warnings only, not as the final wide review; no in-game client check.

## 0.16.1 — every list has named category columns and its own width

- Every UIList now draws the same kind of row: a name cell followed by the
  category cells that belong to that list. Headers name those categories above
  the list, and each list has its own saved **Name width** slider instead of the
  old shared `list_name_width` value. Source, Mods, Scan folders, Contents,
  Parts, source and part material slots, Cloth, Rules, Targets, Tail, Clips,
  Skeleton, bone map, Clients and Components are covered.
- The Source model list and the VPK folder browser now show **Model / Folder**
  and **Folder / Models** headers with their own sliders. Names are no longer cut
  by `_short()` in list rows; Blender clips them to the cell width, so widening
  the slider or the panel reveals more.
- The Source draw no longer writes `folder_signature` from `sync_folders`; that
  write happens from the operator or picker refresh, not from a panel draw. An
  empty roster keeps the synthetic **All folders** choice instead of leaving the
  enum at an invalid zero.
- Blender has no draggable column separators in its UIList API, so the controls
  are per-list factors. A category table is a native header plus aligned rows.
- `tests/test_ui_parity.py` now refuses a list that shares another list's width
  property or has no category split. `202` tests pass, `ui_parity --check` and
  `ui_prose --check` are zero.
- GUI evidence: `artifacts/ui-pass/mods-collection.png`,
  `artifacts/ui-pass/mods-scan-folders.png` and
  `artifacts/ui-pass/source-columns.png`. The full pages probe fails its own
  `surface-open-control` check (0/26 draws), so it is not evidence for this pass.

## 0.16.0 — Mods is a typed collection, and a mod becomes a Blender project

- The scan records folders, VPKs and standalone `*.blend` files as separate kinds. A VPK without a
  compiled model is still a package (`no-compiled-model`), rather than disappearing from the list.
- `ModRecord` carries every listed entry plus counts for models, clips, materials, blends and other
  files. The scan roots list reports the per-root split, and the page note names both package kinds
  and blend files inside them.
- The Mods page has All / Folders / VPKs / Blends chips over a visible `mod_rows` list, a searchable
  contents list with its own content-type chips, and a selected-package card with path, kind, hero,
  date, size and the full content summary.
- `dmf.create_mod_project` opens a blend carried by a folder or a blend record, with an unsaved-file
  confirm. A VPK or a folder without a blend saves the current scene as
  `<workspace>/projects/<slug>/<slug>.blend` with `copy=True`, so the current file is not replaced.
  `project_root` and `project_file` are written before the save, so reopening the project keeps its
  active-project card. Setup shows that card instead of a raw workspace folder field.
- Update and backport move under the selected package; blends do not show an update action that does
  not apply. `tools/blender_mods_gui_probe.py` builds a folder, a VPK and a blend, runs the real scan,
  checks all four filter states and the content filter, creates a VPK project under a temp workspace,
  and captures `artifacts/ui-pass/mods-collection.png`.

## 0.15.1 — build markers follow the selected clients

- Every page card names the extraction client, compile toolchain and, when it differs, the backport
  target, each with its own build. The values follow the selected installs and read their
  `steam.inf`; a backport row appears only when it targets another install.
- The VPK folder control is a searchable list of real pak directories with a model count per folder,
  backed by `DMF_UL_model_folders` and `dmf.browse_folders`. The 6,537-model roster reports 76
  folders; a file that sits directly in `models/` groups under `models` instead of becoming a
  folder named after the file.
- Setup separates the compile toolchain from the game client. `dmf.use_client` selects the extraction
  client; `dmf.use_backport_client` selects the backport target; `dmf.use_toolchain` selects the
  compiler and build. The Tools & clients panel lists every compiler host with its own version, and
  a compiler-only install is not treated as a game client.
- The default page is Setup.
- Animations folds Clips, IK, Tail and Write back into child panels; Release folds the addon slot.
  Each has its own collapse control, so a long page is navigable without one flat scroll.
- Filters are visible chips: the VPK folder browser, the clip graph filter, the bone-map state filter
  and the cloth source. No filter is a native dropdown that hides its current value.
- `artifacts/probes/ui_visual_probe.py` opens the Workbench editor in a real Blender window, captures
  every page to `artifacts/visual/ui-pass/`, and the pages were inspected for clipping. `ui_parity`
  and `ui_prose` remain at zero.

## What moved

- **Release owns the whole chain.** Stage and compile is the `DMF_PT_handoff` panel, mapped to RELEASE.
  The compile button exists once, there. Release adds write model, pack, install, launch, the slot
  number and the pak ceiling from the selected game. A saved `HANDOFF` page opens RELEASE.
- **Heroes are a filtered list, not a dropdown.** `heropick.py` builds rows from the roster with a
  search field, an all/heroes/hideout/other filter, a `DMF_UL_heroes` list, and one confirm button.
  The old enum held every hideout NPC in a single native popup.
- **Setup no longer duplicates scanning.** The Mods page owns scan, update and backport; Setup links to it.

## Copy

`python tools/ui_prose.py --check` runs the writing rules and `tests/test_ui_parity.py` fails on a hit.
The pass removed every em dash and every "actually", "really" and "literally" from the addon's strings.
