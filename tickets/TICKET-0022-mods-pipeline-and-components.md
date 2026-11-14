# TICKET-0022 — page rail, mods pipeline, tool setup, and components as body groups

Status: implemented in 0.8.0
Authority: `logs/authority/2026-11-14-mods-pipeline-components.jsonl`

## Owner requests (verbatim)

> if you could tweak the ui a little bit to be a little closer to the properties
> panel where the pages buttons are the small buttons in the black area on the
> left of the view that would be fantastic, making sure to add a dedicated
> section for the mods, allowing for the user to quickly pipeline any
> mods/models/files that need to be staged in the workbench that might show up.
> Being able to update mods or old game paks to the latest version or even
> potentially backporting mods into older versions of the game as an experimental
> feature. you might want to add a ui for adding directories for scanning for
> compatible files. i deleted the openlock modern s2v cli because the setup page
> should also contain options to download and install the things automatically,
> like for example getting the csdk13 from https://deadlockmodding.pages.dev/
> (but i have csdk13 in downloads so for us we could use this as a way for
> managing custom client installs like other csdk versions as well like in the
> old openlock repo). Also the deadlock game is getting it's own cosmetics
> system, so it supports some features of it already, it'd be nice if the addon
> could stage hero components from the files/live game as well, so if someone
> wants to change a mod's gun for example or add a hat to a hero non-destructively
> without breaking the mod, it could handle that

> the modeldoc can support multiple rendermesh files as seperate dmx files just
> like the game already does, but it needs to be able to gracefull handle the
> bodygroups features, please continue

## What changed

- **The page strip is small icon buttons on the left.** `ui_props.draw_page_rail`
  draws one icon-only `prop_enum` per page, stacked against the left edge of the
  page area. It replaces the 2x6 text grid on both surfaces (the add-on's editor
  and the Properties tab); the header keeps the page dropdown for discoverability.
  Blender does not let an add-on register a region in its own space
  (`Panel` with `bl_region_type='NAVIGATION_BAR'` answers "Region not found in space
  type"), so the rail is inside the window, which is the closest the API allows.
- **Mods is a page, not a dialog.** `forge/oldmods.py` inventory backs a new page
  with: a scan-folder list (add/remove, per-root package and cloth counts, date
  window), a scan that runs in the background and writes
  `<workspace>/mods/old-mods.json`, a package list with hero/date/cloth columns,
  **Update to latest** (same transplant as `update-addon`), and **Backport to
  client (experimental)** gated behind an explicit toggle and a chosen client.
- **Backport is the transplant pointed at an older client.**
  `forge/backport.py` reads the mod's own vmdl path out of that client's
  `pak01_dir.vpk` with Source 2 Viewer (`-f <path> -d`), then runs the same
  section transplant against it. It refuses anything that is not a game build and
  records the client paths and `experimental: true` in `stage.json`.
- **Setup installs and manages the tools.** `forge/provision.py` resolves the
  latest Source 2 Viewer CLI release asset from the GitHub API, downloads it and
  returns the extracted `Source2Viewer-CLI.exe`; it installs a downloaded
  Reduced CSDK zip, verifies `game/bin/win64/resourcecompiler.exe`, and finds
  CSDK-style clients. The page offers **Download & install** for S2V,
  **Get CSDK 13** (opens `https://deadlockmodding.pages.dev/modding-tools/csdk-13`,
  because its Google Drive/Mega links are not direct file URLs), **Install zip**,
  **Find clients**, **Add folder** and **Use this client**. Clients can be older
  CSDKs, like the openlock copies.
- **Components are render meshes with body groups, not a second model.**
  `forge/modeldoc.py` now reads and writes `RenderMeshFile` entries and
  `BodyGroup`/`BodyGroupChoice` blocks:
  `render_mesh_files`, `body_groups`, `add_render_mesh_file`, `ensure_bodygroup`.
  A component DMX becomes one more `RenderMeshFile` (the game's own heroes do
  exactly this: a body DMX and a gun DMX) and a choice in the chosen body group,
  so it can be switched instead of always drawn. A duplicate mesh name is
  refused unless replacement is explicit; an existing group gets the next
  numbered choice; a missing group or a missing `BodyGroupList` is created.
  `forge/migrate.add_component_mesh` is the only writer of the edited vmdl.
- **Components page.** Lists gun/hat/head/hair/attachment assets from the current
  hero extraction, stages the ticked files at their original relative paths into
  `<workspace>/components/content/citadel_addons/<addon>`, and registers each
  staged DMX in a target vmdl when **Register in vmdl** is on. The manifest
  (`components.json`) records every source, the body group, the merge result and
  whether the vmdl was written.

## Evidence

- Unit suite 191 passing, including 6 new render-mesh/body-group tests and 5
  component tests; `python tools/project.py gate` green (tests, compileall, no
  KV3 parser, no vmdl writes outside `migrate.py`, blake3).
- Zip `dist/hero_retarget_workbench-0.8.0.zip`, 54 files, 373,292 bytes,
  sha256 `d1f3c300...8691e`.
- `blender_installed_zip_probe.py` against that zip: 9/9 on PR 165087
  (`area.ui_type=DMF_ST_workbench`) and 9/9 on the stock daily
  (`PROPERTIES`/`SCENE`), 40 page panels registered.
- `blender_pages_gui_probe.py` on a real window: 20/20 page draws, 0 exceptions,
  Cloth page with 19 chains and the rail visible; screenshot
  `artifacts/receipts/workbench-surface.png`.
- Real component run: the three live Kelvin gun DMXs staged into
  `artifacts/components-kelvin` as `kelvin_components`, the vmdl gained
  `kelvin_gun1`, `kelvin_gun_lod13`, `kelvin_gun_lod25` as RenderMeshFiles and
  body group `weapon` with choices `0_#&kelvin_gun1`, `1_#&kelvin_gun_lod13`,
  `2_#&kelvin_gun_lod25`; the original body and gun meshes are still there.
  CSDK13 `resourcecompiler` returned 0 with 1 compiled file and produced
  `kelvin.vmdl_c` (3,824,366 bytes). Log `logs/component-compile.log`.

## Not checked

- No real backport has been run against an older client yet: the path exists and
  is gated, but no old CSDK was targeted in this pass.
- The S2V download was not exercised end to end (the CLI already existed on this
  machine); the GitHub resolution and zip extraction are unit-shaped code without
  a live download receipt.
- The CSDK page opens and the zip installer extracts, but the Google Drive/Mega
  links are not direct downloads, so there is no one-click CSDK install.
- The Mods and Components pages were drawn in a real window (no exceptions) but
  not clicked through: no scan or port was driven from the panel in this pass.
- The component body group was compiled, not observed switching in game.
