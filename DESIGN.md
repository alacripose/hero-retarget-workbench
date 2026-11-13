# DESIGN

## Mode

Operate. The user is inside Blender completing a technical task. Familiar native
affordances, dense information, and reliable state reporting outrank expression.

## Surface

Blender 5.4 native sidebar: `3D Viewport → Sidebar → Deadlock`. A single panel,
not a modal wizard and not a separate window.

## Direction

Quiet industrial. The panel should read like a well-organized Blender tool:
grouped boxes, native labels, native icons, one accent reserved for the primary
handoff action. No custom fonts, colors, chrome, or decorative motion. The
workflow stages are the hierarchy:

1. Hero source
2. Your model
3. Bind
4. Compiler handoff

Each stage uses the same control vocabulary and spacing. Object and file fields
show real paths. The status line is never a generic "Done": it names the build,
the bone/vertex count, the mapped group count, the stage hash, or the failing
path.

## States

- Empty: hero detection begins with one clear action; no fake hero entries.
- Loading: the operator's status moves to `BUSY` while S2V runs.
- Error: the status row uses Blender's alert treatment and names the missing
  input or failed command.
- Partial: unmatched groups and a missing S2V vmdl are warnings, not success.
- Ready: a compile is reported only when `resourcecompiler` returned zero.

## Visual checks

Use only native Blender widgets. Keep labels sentence case except buttons. Keep
the panel narrow enough for the default sidebar. Do not add cards inside cards,
custom progress rings, or decorative icons. Verify contrast through the active
Blender theme rather than hard-coding colors.

## 2026-11-12 — workbench supersession

The earlier "single panel, not a modal wizard" sentence stands as the record.
The owner rejected the single button queue, and the surface is now one parent
panel with native subpanels: Source, Compare, Skeleton, Weights & Proof, and
Compiler Handoff. This is still one sidebar surface, not a window or wizard.

- Skeleton uses a native `UIList` with mapped, unmatched, extra and ignored
  rows, plus a selected-row editor. Rename and alignment are compact rows, not
  dialogs.
- Compare is two native 3D areas with local views, not a custom renderer or a
  second window.
- Weights & Proof uses a native progress bar for the chunked solve and named
  token rows for the Axis checks. A failed check is shown where it is, not hidden
  behind a generic status.
- The status header still names the live build, hero and exact last result. The
  panel does not claim a proof or a viewport witness it did not produce.
- Labels remain short enough for the default sidebar; the bone list is the only
  dense table and rows truncate by native width.

## 2026-11-12 — public landing page

`landing/index.html` is a separate Persuade surface. It does not replace or
restyle the native Blender panel. It projects the family web-dark register from
`openlock_modern/docs/design/`: near-black ground, gold attention, Archivo and
IBM Plex Mono, the 20×20 square-in-square mark, the 8dp rhythm, and the radius
ladder.

The page is a technical dossier: the live-build workbench readout, the measured
Haze export and compile readings, the hard boundaries, the install commands, and
the family register. It uses the real test and evidence counts from README and
STATUS. It does not add a marketing claim or a second design authority.

## 2026-11-12: parts and material slots

The Parts & Materials panel is the sixth native subpanel. It has two explicit
lists: collection parts and material slots. The part list is collection-scoped
and includes child collections. Selecting a row is not the same as using a part;
the `Use part` action names the active object and the status line reports it.
The material panel shows a source list and an active-part slot list. Actions are
one source slot to one part slot: replace, append, or clear. The panel does not
offer a replace-all button, and it does not choose a nearest material or part.

At the default sidebar width the two material lists are stacked, not placed
side by side, so a material name and its slot index remain readable. Hints are
short enough not to clip at that width. The primary actions are stacked full
width; the check is the real-window screenshot at
`artifacts/receipts/parts-panel.png`.

## 2026-11-13 — Skeleton rules, ref pose and the Animations page

Skeleton now opens with the map-wide controls before the per-row editor: Auto
rules (three glyphs — Learn, Fill, Regex — and a native rule list showing
`elbow* -> arm_lower*` with an on/off checkbox) and Ref pose (a Show toggle, a
play glyph that applies it now, and a loop-back glyph that clears it, with the
source stance as the section's detail). The rule list is two rows so the ref-pose
controls stay inside one sidebar scroll at the default window height; the row
editor, bone map and bone list follow in the same order as before.

Animations is a folded page like Compare: a Clips card (`imported/total`), Scan /
Import all / Stop glyphs, the folder field, a six-row native clip list with the
kind on the right (`dmx`, `dmx_c`, `vnmclip`, `vnmskel`), the selected file's
size and action, Import / Preview, a Prefix field with a rename glyph, Clear
imported actions, and the state notes: compiled clips are listed and never
opened, and DMX export is not wired into this page.

Status wording follows the same rule as the rest of the surface: one short
sentence naming what happened and what is left, and an ellipsis rather than a cut
word when the bubble runs past its lines.
