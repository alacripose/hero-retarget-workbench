# UI pass 0.15.1

The Workbench pages were built one at a time, and the check that every action has one home did not
exist. This pass adds the check, moves staging and compiling onto the Release page, replaces the hero
dropdown with a filtered list, and runs the family writing rules over every user-facing string.

## References

- Popit surface grammar: one soft card naming the edited thing and its state, uppercase micro-labels,
  glyph rows, folded advanced groups, one message per page. Implemented in `ui_popit.py`.
- Landing family design: the alacripose landing page supplies the density and the label voice, not a
  palette. Blender's theme owns color.
- `impeccable` (Operate mode): scanability, native expectations, no wizard.
- `stop-slop` (github.com/hardikpandya/stop-slop) and `declauding`
  (github.com/oaustegard/claude-skills): no em dashes, no filler openers, no intensifier adverbs, no
  "not just" staging, no stock marketing words. `tools/ui_prose.py` enforces the shared set.

## Page parity

| Page | Panels | Actions |
|---|---|---|
| SETUP | DMF_PT_setup, DMF_PT_setup_tools, DMF_PT_setup_toolchains | `dmf.add_client`, `dmf.detect_paths`, `dmf.install_csdk`, `dmf.install_s2v`, `dmf.open_csdk_page`, `dmf.refresh_clients`, `dmf.use_backport_client`, `dmf.use_client`, `dmf.use_toolchain` |
| SOURCE | DMF_PT_source, DMF_PT_source_files | `dmf.apply_model_name`, `dmf.browse_folders`, `dmf.choose_hero`, `dmf.detect`, `dmf.extract`, `dmf.fit`, `dmf.import_custom`, `dmf.import_hero`, `dmf.pick_vmdl`, `dmf.refresh_heroes` |
| PARTS | DMF_PT_parts, DMF_PT_parts_materials | `dmf.append_material`, `dmf.assign_material`, `dmf.clear_part_material`, `dmf.scan_materials`, `dmf.scan_parts`, `dmf.use_active_collection`, `dmf.use_part` |
| CLOTH | DMF_PT_cloth | `dmf.build_all_cloth`, `dmf.build_chain_cloth`, `dmf.import_hero_parts`, `dmf.join_cloth_chain`, `dmf.mark_cloth_proxy`, `dmf.scan_cloth` |
| SKELETON | DMF_PT_skeleton, DMF_PT_skeleton_bones | `dmf.add_bone_entry`, `dmf.align_all_bones`, `dmf.align_bone`, `dmf.clear_target`, `dmf.copy_pose`, `dmf.ignore_entry`, `dmf.mark_extra`, `dmf.nudge_bone`, `dmf.pick_bone_map`, `dmf.pose_clear`, `dmf.pose_preview`, `dmf.refresh_hierarchy`, `dmf.remove_bone_entry`, `dmf.rename_bones`, `dmf.scan_bones`, `dmf.select_hierarchy_bone`, `dmf.stop_rules` |
| RULES | DMF_PT_rules | `dmf.add_rule`, `dmf.apply_ik`, `dmf.apply_rules`, `dmf.bake_ik`, `dmf.blend_tail`, `dmf.blend_tail_all`, `dmf.build_tail_animation`, `dmf.clear_ik`, `dmf.clear_rules`, `dmf.learn_rules`, `dmf.load_tail_option`, `dmf.preview_tail`, `dmf.publish_tail_anims`, `dmf.remove_rule`, `dmf.rule_from_row`, `dmf.scan_ik`, `dmf.scan_tail`, `dmf.scan_tails` |
| ANIMATIONS | DMF_PT_animations, DMF_PT_animation_ik, DMF_PT_animation_tail, DMF_PT_animation_write | `dmf.apply_ik`, `dmf.bake_clip`, `dmf.bake_clips`, `dmf.bake_ik`, `dmf.blend_tail`, `dmf.blend_tail_all`, `dmf.build_tail_animation`, `dmf.cancel_clips`, `dmf.clear_clips`, `dmf.clear_ik`, `dmf.export_clip`, `dmf.export_clips`, `dmf.import_clip`, `dmf.import_clips`, `dmf.load_tail_option`, `dmf.prefix_clips`, `dmf.preview_clip`, `dmf.preview_tail`, `dmf.publish_tail_anims`, `dmf.scan_clips`, `dmf.scan_ik`, `dmf.scan_tail`, `dmf.scan_tails` |
| COMPARE | DMF_PT_compare | `dmf.apply_compare_action`, `dmf.compare_clear`, `dmf.compare_split` |
| WEIGHTS | DMF_PT_weights, DMF_PT_weights_manual | `dmf.assign_active_bone`, `dmf.limit_influences`, `dmf.mint_proof`, `dmf.mirror_weights`, `dmf.normalize_weights`, `dmf.remove_zero_weights`, `dmf.retarget`, `dmf.select_unweighted`, `dmf.smooth_active_group`, `dmf.verify_proof` |
| MODS | DMF_PT_mods, DMF_PT_update | `dmf.add_scan_root`, `dmf.backport_mod`, `dmf.pick_old_vmdl`, `dmf.pick_old_vpk`, `dmf.port_mod`, `dmf.remove_scan_root`, `dmf.scan_mods`, `dmf.update_old_addon` |
| COMPONENTS | DMF_PT_components | `dmf.pick_component_vmdl`, `dmf.scan_components`, `dmf.stage_components` |
| RELEASE | DMF_PT_handoff, DMF_PT_handoff_paths, DMF_PT_release, DMF_PT_release_slot | `dmf.build_lods`, `dmf.clear_lods`, `dmf.compile`, `dmf.export_stage`, `dmf.install_pak`, `dmf.launch_game`, `dmf.pack_vpk`, `dmf.write_model` |

`python tools/ui_parity.py --check` fails on an action drawn on two pages, a page with no panel, or an
action drawn that no operator declares. `tests/test_ui_parity.py` pins the same result.

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
