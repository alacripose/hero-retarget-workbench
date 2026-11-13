# TICKET-0013 — sidebar follows the Popit instead of a settings wall

**Status:** implemented; the restyled sidebar was screenshot-checked in a GUI
Blender session.
**Owner:** ala
**Authority:** `logs/authority/2026-11-13-popit-surface-pass.jsonl`
**Opened:** 2026-11-13

## Requirement

The owner added `C:\Users\ala\Documents\popit_base\references\` and said the
addon's visuals should be closer to the Popit so people are not overloaded, while
the addon keeps following the dark theme.

## What the references actually show

The ten captures (`me.png`, `create_mode_menu.png`, `pod_mode_menu.png`,
`bouncepad_settings_example.png`, `winch_settings_example_half_scroll.png`,
`mats_page1_half_scroll.png`, `gameplay_page3_half_scroll.png`,
`level_info_editor.png`, `create_mode_tooltip_example.png`,
`page_and_extra_content_below_visible_content_arrow.png`) and
`openlock/docs/UI-PASS.md` + `openlock/docs/popit-elements.json` agree on one
grammar:

1. A single soft translucent card holds everything for the thing being edited.
2. The card opens with its **name** and immediately an uppercase **micro-label**
   for the group under it (`PROPERTIES`, `MOVEMENT`, `STONE`).
3. Actions are **glyphs**. A value is a number beside one glyph, not a sentence.
4. Groups **fold away** behind their own chevron; only the group in use is open.
5. Exactly one **accent bubble** (a lime speech bubble with a tail) carries the
   message about the current control. There is no prose under every row.
6. The page is five tools around one hub, not a list of every setting.

## Translation to a Blender sidebar

Blender's `UILayout` has no font sizes, colours, borders or dashed rules, and the
Popit's lime-on-blue is a game surface, not a dark editor. What survives:

- `ui_popit.title()` — the page card: one name, one state, one icon.
- `ui_popit.micro()` — the uppercase group label.
- `ui_popit.glyphs()` — icon actions; three or more are bare glyphs, one or two
  carry their word because a lone stretched icon reads as a missing label.
- `ui_popit.bubble()` — the single message a page may show, at most two lines.
- Blender's own `DEFAULT_CLOSED` sub-panels — the folding groups and chevrons.
- Blender's dark theme — the colour. Nothing here invents a palette.

## What changed

- **Main panel** is now `Workbench`: the hero card, one next-step line
  (`forge/stageflow.next_step`, with an answered/total count and the panel that
  owns the step), one status bubble, and the job bar. The old block of
  build + hero + status prose is gone.
- **Every page** opens with a `ui_popit.title` card and uses `_section` titles as
  uppercase micro-labels.
- **Explanation moved out of the panel.** Roughly forty `_hint` paragraphs were
  removed or cut to the one line that states a refusal or a blocking state;
  ordinary help stays in the operators' and properties' own tooltips.
- **Deep controls fold away** into new closed sub-panels: Source → Files, Parts →
  Material slots, Skeleton → Bone list & alignment, Weights → Solver detail &
  weight tools, CSDK Addon → Content paths & LOD build.
- **Compare, Setup, Weights, CSDK Addon** now lead with glyph rows; the handoff
  page shows addon name, state, LOD currency and three actions, and nothing else
  until the paths group is opened.
- **Path rows in Setup** are unchanged in behaviour; the CSDK hint no longer
  prints a path fragment that the sidebar clips.

## Evidence

- `python tools/project.py gate` passes; `tests/test_stageflow.py` (6 tests) covers
  the next-step order, the first-gap rule, progress counting and that every step
  names a panel.
- `tools/blender_sidebar_gui_probe.py` registers the same panel classes under the
  already-selected Item tab — Blender exposes no way to select a sidebar tab from
  a script, and this is probe-only; the shipped addon stays on Deadlock — then
  screenshots the window. `artifacts/ui-pass/sidebar.png` and its crop show the
  Workbench card, the next-step line, the single bubble, the uppercase SETUP and
  LIVE GAME headers and the one labelled Detect action.
- `tools/blender_zip_probe.py` reasserts panel registration at 14 panels.

## Not claimed

The folded sub-panels were not opened in the screenshot, so their contents are
verified by code and registration, not by eye. The owner's own look at the
installed addon is still the acceptance.
