# TICKET-0020 — the installed zip's editor surface is reachable

Status: implemented in 0.7.2
Authority: `logs/authority/2026-11-14-editor-surface-reachable.jsonl`

## Owner report (verbatim)

> also every time I install the ci zip the custom editor isn't there or if it is
> there it's not the real one like you have when you launch it

> Dude I'm using the fucking branhcht that allowd for the editor and it's not
> showing up what the fuck can i say

## What was checked, and what was true

The published asset is not stale: `hero_retarget_workbench-0.7.1.zip` carries
`ui_space.py` (6,536 bytes) and `__init__.py` imports it. Installing that asset
through Blender's add-on installer into an isolated profile registers
`DMF_ST_workbench`, sets `SURFACE = "editor"`, and switches an area to it on the
PR 165087 build; on the stock daily it registers no space and falls back to
Properties, as designed.

The reachability problem is in the UI, not the artifact:

1. **Nothing in the add-on took you to the editor.** `dmf.open_workbench` existed
   and the Properties page root called it, but the sidebar — the place the add-on
   is opened from — had no such control, and the editor-type menu did not list the
   space in the owner's session even though it was registered.
2. **The fallback looked like nothing.** On a build without editor types, the
   Properties page root draws after Blender's built-in Scene panels; `bl_order`
   cannot reorder those, so the page could look absent.
3. **A declined editor was silent.** `ui_space.register()` printed the exception
   and fell back; the panel never said why.

## What changed

- `ui.py`: the Workbench sidebar panel now draws the surface control —
  **Open the Workbench editor** when the build registered the editor, otherwise
  **Open the Workbench page** plus the line "This Blender build cannot register
  editor types; the pages are in Properties > Scene".
- `ui_props.py`: the page root draws the same control with the same wording, and
  shows `EDITOR_ERROR` when the build could have had an editor and registration
  failed.
- `ui_space.py` / `__init__.py`: the decline reason is kept in
  `ui_space.EDITOR_ERROR` and `EDITOR_ERROR` on the add-on module instead of only
  being printed; the editor header now labels itself **Workbench**.
- `tools/blender_installed_zip_probe.py`: installs the built zip into an isolated
  profile, enables it, and checks surface, space/header registration, pages, and
  that `dmf.open_workbench` switches an area to the editor (or to
  Properties/Scene on a build without editor types). This is the check that was
  missing: every earlier probe loaded the add-on from this checkout.

## Evidence (0.7.2)

- `blender_installed_zip_probe.py` against `dist/hero_retarget_workbench-0.7.2.zip`:
  9/9 on PR 165087 (`area.type=CUSTOM`, `area.ui_type=DMF_ST_workbench`) and 9/9
  on the stock daily (`area.type=PROPERTIES`, context `SCENE`). Receipts
  `artifacts/receipts/zip-install-pr.json` and `zip-install-stock.json`,
  screenshots `zip-install-editor.png` and `zip-install-stock.png`.
- `blender_pages_gui_probe.py`: 17/17 page draws, 0 exceptions on both surfaces;
  the new check `surface-open-control` proves the operator and the page root exist.
- Not checked: the editor-type menu's own listing on the owner's machine — that
  menu is C-side and cannot be opened from Python here, so the fix routes around
  it with the add-on's button. The stock build still cannot host an editor type at
  all.
