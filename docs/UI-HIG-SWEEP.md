# UI sweep: Apple HIG applied to every Workbench page

Owner request, verbatim: *"hero text outside of button, text below buttons is..
wrapped as if the buttons above share the same horizontal space? setup page is
mucho texto, info panes on all pages get wrapped as if content above shares the
same horizontal space, please obtain the apple human interface guidelines and
apply it in full to the addon's ui pages (full sweep) use write_todos"* and
*"the whole damn thing is ugly"*.

This is the todo record for the whole surface, not a one-page fix. `write_todos`
is not exposed in this session, so this file is the persistent todo list and is
updated as each item lands.

## Rules taken from the Apple HIG

- Layout: order by importance, align related content, use indentation only for
  hierarchy, group with space before containers, use progressive disclosure.
- Layout: adapt to actual available width; rows grow instead of cropping text.
- Labels: short, legible, editable values belong in fields; explanatory prose
  does not belong in a label row.
- Buttons: one or two prominent actions per view; same-height siblings; enough
  space to distinguish controls; familiar symbols.
- Sidebars: short group labels; no more than two visible levels where possible.
- Writing: plain, concise, action-oriented labels; no jargon in the main path.

## Shared surface

- [x] Create this todo file.
- [x] Read `impeccable`, `stop-slop`, `declauding`, and the Apple layout,
  buttons, labels, sidebars and writing guidance.
- [x] Replace fixed character wrapping with width-aware wrapping in one helper.
- [x] Remove the two-line silent truncation from hints; errors stay complete.
- [x] Make `ui_mods` use the same hint implementation as every other page.
- [x] Replace nested section cards with flat groups separated by whitespace.
- [x] Replace uppercase micro-headings with readable sentence-case group labels.
- [x] Establish one action hierarchy: primary, secondary, destructive, icon-only.
- [x] Give every page header one title, one state and one next step.
- [x] Make the page header and footer work at the 640 and 960 editor widths;
  no header item overlaps or disappears without an overflow path. The native
  sidebar's 120 px minimum is recorded as a limitation, not a final receiver.
- [x] Remove decorative retyping of state in labels and buttons.
- [x] Make empty states one action, not a paragraph.
- [x] Keep full values for paths and errors; use summaries only where a value is
  repeated in a field on the same page.
- [x] Verify against a real Blender draw pass at editor widths; the native
  sidebar's minimum width was used as a warning source, not as the final look.

## Page sweep

Each page gets: hierarchy, spacing, text fit, action order, empty state, and a
screenshot check.

- [x] SETUP: `DMF_PT_setup`, `DMF_PT_setup_tools`, `DMF_PT_setup_toolchains`
- [x] SOURCE: `DMF_PT_source`, `DMF_PT_source_files`
- [x] PARTS: `DMF_PT_parts`, `DMF_PT_parts_materials`
- [x] CLOTH: `DMF_PT_cloth`
- [x] SKELETON: `DMF_PT_skeleton`, `DMF_PT_skeleton_bones`
- [x] RULES: `DMF_PT_rules`
- [x] ANIMATIONS: `DMF_PT_animations`, `DMF_PT_animation_ik`,
  `DMF_PT_animation_tail`, `DMF_PT_animation_write`
- [x] COMPARE: `DMF_PT_compare`
- [x] WEIGHTS: `DMF_PT_weights`, `DMF_PT_weights_manual`
- [x] MODS: `DMF_PT_mods`, `DMF_PT_update`
- [x] COMPONENTS: `DMF_PT_components`
- [x] RELEASE: `DMF_PT_handoff`, `DMF_PT_handoff_paths`, `DMF_PT_release`,
  `DMF_PT_release_slot`

## Surface chrome

- [x] Custom editor header: page menu, version and build status; the duplicate
  page strip was removed.
- [x] Properties page grid: readable page names, no icon-only guessing.
- [x] Error and job cards: one clear state, one recovery action.
- [x] List headers: category labels aligned to rows, no truncation introduced.
- [ ] Dialog surfaces: VPK folder browser and path pickers; these are Blender's
  native file dialogs and were not restyled.

## Evidence

- [x] `202` tests pass.
- [x] `python tools/ui_parity.py --check` is zero.
- [x] `python tools/ui_prose.py --check` reports zero hits in 30 files under the two-second rule
  (18 words / 92 characters per UI string, 24 words per sentence).
- [x] Pages probe draws every registered page without an exception.
- [x] Editor screenshots at 960 px and 640 px; narrow panels re-wrapped and the
  header status moved into the page body below 650 px.
- [x] `git diff --check` is clean.

## Scope additions found during the sweep

Add here instead of dropping an item. Nothing in this section is optional until
the owner removes it.

- Page roots use the panel header as the one page title. The state/build line
  sits under it; the old page card was removed because it repeated the title and
  left a header-arrow artifact when `HIDE_HEADER` was used.
- Every action has a text label; the remaining icon-only buttons are the job
  dismiss, file/search pickers, list scroll controls, or the bone-map visibility
  toggle.
- Chips are real buttons, not enum labels sitting outside their value column.
- Advanced Setup/Mods children are nested under their page root, so a closed
  child no longer appears above the page it belongs to.
- Release opens with `Pack & install` already expanded; it is the page's work.
- The list height follows the number of hero models, so one model no longer
  leaves six empty rows and a paragraph below it.
