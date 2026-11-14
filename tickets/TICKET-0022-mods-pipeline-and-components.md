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

## 0.8.1 correction — the black page strip belongs to the Workbench's own view

0.8.0 put the page rail inside the Properties editor's Workbench tab and left it
in the Scene column when the build could not register the editor. On the owner's
screen the rail overlapped the native tabs, consumed the narrow column's height,
and pushed the page body below the fold: worse than the old Properties tab it
replaced.

0.8.1 removes that surface entirely:

- the Properties editor never registers a Workbench page again, and
  `dmf.open_workbench` no longer falls back to it;
- the Workbench editor opens with a narrow companion area split off to its left,
  `DMF_ST_workbench_pages`, whose only panel is the page strip: one small icon
  button per page, the current page depressed, `Cloth` highlighted in the probe
  screenshot. The strip gets its own real black column, the way the Properties
  editor's tab strip does, instead of being drawn inside the page body;
- the split aims at ~46 px (clamped 2–30% of the area) so it is neither a 15 px
  sliver in the Properties column nor a 130 px void in a maximised viewport;
- on builds without custom space types the operator opens the 3D viewport
  sidebar (N) and says so in the status line instead of degrading into Properties.

Verified: zip 0.8.1 installs 9/9 on PR 165087 with both `DMF_ST_workbench` and
`DMF_ST_workbench_pages` present after `dmf.open_workbench`, and 9/9 on the stock
daily with surface `sidebar`, area `VIEW_3D` and `show_region_ui` open. The pages
probe passes 20/20 page draws with 0 exceptions on the editor surface. Screenshot
`artifacts/receipts/pages-0.8.1.png`, strip crop
`artifacts/receipts/pages-0.8.1-strip-crop.png`.

Not checked: the strip's click behaviour was not driven by a real mouse click in
this pass (the icons are standard `prop_enum` buttons); the page mirrors still
have no scrolling in the narrow companion area.

## 0.8.2 — CI could not collect the new tests

`tests/test_components.py` and `tests/test_oldmods.py` imported `pytest`, which
is not in `requirements.txt`; the workflow runs `python -m unittest discover`,
so both modules failed at import and the 0.8.0/0.8.1 test jobs stopped before the
build (no release asset). Both files are `unittest.TestCase` classes with
`tempfile.TemporaryDirectory` now, `assertRaisesRegex` instead of
`pytest.raises`, so the workflow's own command collects them: 114 tests pass
under `unittest discover`, 191 under `pytest`.

## 0.8.3 — navigation-bar and reinstall collisions

**Owner request, verbatim:** *"dude the buttons are supposed to be in the navigation
bar? the black area next to the view that expands out? and now there are install
errors that you just missed??? these are collissions to be recorded"*.

- **Navigation bar: blocked by Blender, recorded.** `Space.draw_handler_add` on
  `DMF_ST_workbench` answers `TypeError: unknown space type 'DMF_ST_workbench'`.
  Python can draw into a `NAVIGATION_BAR` region only for native space types, so
  page buttons cannot be placed in the Workbench editor's nav bar from an
  add-on. A real nav-bar strip needs a Blender C change: registering custom
  space types in the draw-handler lookup and giving them a nav-bar region. The
  narrow `DMF_ST_workbench_pages` area from 0.8.1 remains the closest surface
  that exists without patching Blender. Probe:
  `artifacts/receipts/navbar-probe.json` (draws 0, the TypeError, no handler).
- **Reinstall: duplicate registration fixed.** Installing a zip while a copy is
  enabled re-enables the module in the same process and left the old classes
  registered, so `register()` died on `register_class(...): already registered as
  a subclass 'DMF_BoneEntry'`. `register()` now releases any `DMF_*` class still
  in `bpy.types` before registering the new module.
- **Windows file lock, recorded.** `addon_install` over an enabled copy cannot
  overwrite the loaded `_vendor/blake3/blake3.cp313-win_amd64.pyd`; Blender
  answers `CANCELLED` and leaves the old files. The add-on still enables and
  registers afterwards (41 panels, no errors). Replacing those bytes needs a
  Blender restart or disabling the add-on before Install; it is not a
  registration failure.
- Evidence: `tools/blender_reinstall_probe.py` on PR 165087, 4/4:
  first install `FINISHED`, second install `CANCELLED` but enable `FINISHED`,
  41 page panels, 0 register errors; receipt
  `artifacts/receipts/reinstall-0.8.3.json`.

## 0.8.4 — the editor registers first, and says why when it does not

**Owner report, verbatim:** *"ana again, now the 8.3 versionhas no fucking view on
the experimental blender branch that allows custom views, stop regressing the
code"*.

0.8.3 registered the whole editor as one block: space, header, root, page
mirrors, and the companion pages space. One refused optional class (the pages
space or any single mirror) made `register()` unregister everything and fall
back to the sidebar — a view that worked on 0.7.2 disappeared when the strip was
added.

- `register()` now registers the required editor classes first and keeps them;
  page mirrors and the pages strip are registered one at a time and a refusal is
  recorded in `EDITOR_ERROR` without taking the view away.
- `custom_space_supported()` no longer trusts only the `Panel.bl_space_type`
  enum: if `CUSTOM` is absent it registers and unregisters a throwaway Space to
  ask the build directly, so a PR build that does not list the enum is not
  mistaken for stock.
- `dmf.open_workbench` only splits for the strip when `DMF_PT_space_pages`
  actually registered; otherwise it opens the single editor area.
- Every enable prints `DMF surface=... error=...` and writes
  `<user config>/dmf/surface.json` with surface, error, version, addon file,
  Blender version and whether each space registered. The sidebar no longer says
  "pages are in Properties > Scene" — that surface is gone — and it shows the
  editor error when there is one.
- Evidence: zip 0.8.4 on PR 165087, 9/9 with both spaces; reinstall probe 4/4;
  `surface.json` in the isolated profile reads `surface: editor, error: "",
  space_registered: true, pages_registered: true`. Receipts
  `artifacts/receipts/zip-install-0.8.4.json`,
  `artifacts/receipts/reinstall-0.8.4.json`.

Not checked: the owner's own profile. If it still reports `surface: sidebar`,
`<BLENDER_USER_CONFIG>/dmf/surface.json` now names the failing class instead of
silently dropping the view.

## 0.8.5 — the pages go in the Workbench's own expanding sidebar

**Owner report, verbatim:** *"he older 7.2 behavior works fine yeajh but here's the
thing in the custom view it literall has a fucking side panel that expands out
and for some reason you aren't putting anything in it????? now you've moved pages
into it's own thing?"*

The custom space has a real `UI` region — the sidebar that expands out — and it
accepts an add-on panel there. 0.8.1-0.8.4 ignored it and split a second area
beside the editor instead.

- `DMF_PT_space_pages` is now a `bl_region_type='UI'` panel in
  `DMF_ST_workbench`, `bl_category="Workbench"`, listing every page with its icon
  and label; the current page is depressed. That is the black expanding side
  panel in the owner's screenshot.
- The separate `DMF_ST_workbench_pages` area, its header and the area split are
  gone. `dmf.open_workbench` switches the area to the editor and sets
  `show_region_ui = True`, so the pages are visible on first open and collapse
  with the sidebar.
- Evidence: zip 0.8.5 on PR 165087, 9/9; the probe reports
  `ui_types: ['DMF_ST_workbench']`, `sidebar: True`, `pages_panel: True`.
  Screenshot `artifacts/receipts/pages-0.8.5.png` shows the page list in the
  Workbench sidebar with Cloth selected. Reinstall probe 4/4.
- Not checked: clicking a page in that panel was not driven by a real mouse click
  (the entries are standard `prop_enum` buttons); the sidebar is the UI region's
  normal collapse/expand, not a custom animation.

## 0.8.9 — the page panel comes back when the space is chosen from the editor menu

**Owner report, verbatim:** *"screenshot A: custom view works fine after pressing
open workspace button (0.8.5) but in the custom view that opens from the thing
that lets you choose what view it's on it only shows the fucking buttons to switch
the damn page … you broke the working custom view"*.

0.8.7 removed the `DMF_PT_space_main` root and made page mirrors top-level with an
empty `bl_parent_id`. A subclass inherits the sidebar panel's old parent id, and
an empty parent id draws nothing in a custom space, so the editor opened from the
editor-type menu showed only the Pages sidebar. That was a regression, not a
layout preference.

- The root container is registered again and page mirrors are parented to it;
  `dmf.open_workbench` and choosing the space from the editor-type menu now draw
  the same page panel.
- The page list stays in the space's `UI` region (the expandable sidebar), not in
  the WINDOW area: probe geometry is `UI x=1296 width=280`, `WINDOW x=2
  width=1294`, and `DMF_PT_space_pages.bl_region_type == 'UI'`.
- `show_region_ui` is now opened by a timer, not inside a panel draw; setting it
  during draw re-laid the area mid-frame.
- Evidence: `artifacts/probes/probe_direct_view.py` opens the space by id with no
  operator (the editor-type path), reports `root_registered: true`,
  `pages_registered: true`, sidebar true, and the screenshot
  `artifacts/receipts/direct-view.png` shows the Cloth page panel beside the
  Pages sidebar. Zip 0.8.9 install probe 9/9; wide screenshot
  `artifacts/receipts/pages-0.8.9.png`.

Not checked: a click on a page button.

## 0.8.10 — the pages are the right-edge tab strip

**Owner report, verbatim:** *"in the custom view there is a single tab called
workbench not the fucking n sidepanel"*, *"why are pages their own view if
there's been a vertical tab available this whole fucking time like on the far
right where the buttons could be? and there's still a dedicated goddamn left
sidebar in the custom view with nothing in it"*.

- The single `Pages` panel is gone. Each page is now its own sidebar category
  (`DMF_PT_space_tab_setup` … `DMF_PT_space_tab_components`), so the vertical
  strip at the right edge of the custom view lists Setup, Source, Parts, Cloth,
  Skeleton, Rules, Animations, Compare, Weights, Handoff, Mods, Components as
  tabs.
- Selecting a tab switches the Workbench page. The signal is that tab's panel
  drawing; the switch runs from a timer with a scene lookup that works without
  `bpy.context.scene`. A direct assignment from inside draw did not stick.
- The header page dropdown is removed: it fought the selected tab.
- The empty TOOLS strip on the left of the custom view is closed with
  `show_region_toolbar = False` (and the footer), alongside opening the sidebar.
- Evidence: direct-view probe (no operator) reports `page: SETUP` after selecting
  the Setup tab, and `artifacts/receipts/direct-view.png` shows the Setup page
  (LIVE GAME, CSDK13, WORKSPACE, Update old addon, Tools & clients) with the
  page tabs on the right edge and no Pages panel. Zip 0.8.10 install probe 9/9.

Not checked: a real mouse click on a tab; the switch was observed by opening the
space with the Setup tab active.

## 0.8.11 — an install now actually replaces the add-on

**Owner report, verbatim:** *"in your tests and probes it worked but i installed
it and it's not the tabs"*.

Blender was installing over an enabled copy and answering `CANCELLED` with a
`PermissionError` on `_vendor/blake3/blake3.cp313-win_amd64.pyd`. The files stayed
old, so the running add-on was not 0.8.10 at all; the probes were testing the zip,
the owner's session was testing the previous version.

- `blake3` is imported on first hash, not at `forge.hashes` import.
- `forge.proof` no longer computes `PROOF_SCHEMA`/`WEIGHTS_SCHEMA` at import
  (hash-pinned contracts); they are computed on first use, with module
  `__getattr__` preserving the constant names.
- Reinstall probe now requires the second install to be `FINISHED`, not tolerated
  as locked: 4/4, 52 panels, 0 registration errors. Receipt
  `artifacts/receipts/reinstall-0.8.11.json`.
- The sidebar shows `Hero Retarget Workbench <version>` so the running build is
  visible without reading preferences.
- Zip 0.8.11 install probe 9/9; gate green; 114 unittest tests.

To cross from an older build once: fully quit Blender with the add-on disabled
(or delete its folder while Blender is closed), then install 0.8.11 and enable.
From 0.8.11 on, installing over an enabled copy replaces the files.

## 0.8.12 — a reloaded module repairs the registered UI

**Owner report, verbatim:** *"notice how 8.11 is installed fresh and the pages
are still not tabs nor is there a pinned version number?"*

Their screenshot shows Preferences at 0.8.11 but the custom view still has the
`Workbench | Cloth` header dropdown, which 0.8.10 removed. So Blender had the new
files (Preferences reads the module) while the registered panels were the old
ones: Install reloads the Python module without re-running `register()`.

- `register()` starts a persistent timer. If the editor surface is active, the
  space exists, and no page tab is registered, it re-registers once or twice and
  logs `DMF stale UI: re-registering the loaded version`.
- The custom view header prints `v<version>` beside `Workbench`, so the running
  build is visible in the view itself, not only in Preferences.
- Zip 0.8.12 install probe 9/9; `artifacts/receipts/pages-0.8.12.png` shows
  `Workbench v0.8.12` with Setup…Components as the right-edge tabs.

A restart is still the clean path; the self-heal covers the reload case that the
owner hit.

## 0.8.13 — tabs without a page box

**Owner report, verbatim:** *"the arrow doesn't appear when the left hand sidebar
is expanded with empty content"* and *"there's a literally empty right sidebar
next to the tab buttons that just says the name of the tab instead of it just
being tabs and the workbench"*.

- The page tab panels drew an empty panel body headed with the page name beside
  the tab strip. They now set `bl_options = {'HIDE_HEADER'}`; the tab is the only
  visible control.
- Switching no longer depends on that panel's draw (which may not run at all for
  a headerless panel). The timer reads `region.active_panel_category` from the
  UI region, maps the label to a page, and writes `props_page`.
- **The strip left of the tabs cannot be shrunk.** The UI region is 280 px wide
  and `Region.width` is read-only (`AttributeError ... is read-only`). The space
  between the page and the tab strip is that region, not a panel.
- **The toolbar handle cannot be removed.** `show_region_toolbar = False` closes
  the TOOLS region (measured 1 px), but the collapsed handle remains, because a
  custom space's region set is created in C and Python cannot delete a region.
- The earlier probe hung because it never quit Blender; it is deleted. The
  installed-zip probe now drives the category directly, checks Cloth→CLOTH and
  Setup→SETUP, screenshots, and exits.
- Evidence: `artifacts/receipts/pages-0.8.13.png` (tabs, no page box, Cloth page,
  `Workbench v0.8.13`), `zip-install-0.8.13.json` 10/10.
- **Correction (0.8.14):** the fixed-280 claim was withdrawn. 280 is the default
  width of a fresh area; the sidebar is draggable, and our timer reset it.

Not checked: a real mouse click on a tab; the category was set through the API.

## 0.8.14 — the sidebar keeps the width the owner gave it

**Owner correction, verbatim:** *"I resize the workbench to fit the width of the
window up to the tabs, but when I switch tabs it resets … the limitation is your
own to note as a collision, not a missing blender feature"*.

0.8.13 said the UI region was a fixed 280 px. That was wrong. The sidebar width is
per-area layout state the owner can drag, and it is smaller on a smaller view; the
default is 280 on a fresh area. The reset was ours: `_ensure_sidebar` ran every
second and set `show_region_ui = True` whenever it read false, which reopened a
collapsed or narrowed sidebar at the default width — including right after a tab
switch redraw.

- The timer now handles each area exactly once (`_SEEN_AREAS` by
  `area.as_pointer()`); it opens the sidebar and closes the empty TOOLS/FOOTER
  regions on first sight, then only reads `active_panel_category`.
- A deliberate collapse or drag is left alone. `dmf.open_workbench` forgets the
  area so opening it again still opens the sidebar.
- Evidence: gate green; `artifacts/receipts/zip-install-0.8.14.json` 10/10 with
  Cloth→CLOTH and Setup→SETUP; `pages-0.8.14.png` shows the fresh-open default
  width, which is what a just-created area has before a drag.

Not checked: an actual mouse drag of the sidebar edge — `Region.width` is
read-only to Python, so the persistence is proven by the timer no longer writing
the flag, not by simulating a drag.

## 0.8.15 — one writer for the page

**Owner report, verbatim:** *"fresh open on 8.14 I fucking click a tab and it
starts flickering back and forth and goes back to having the wide empty space on
the right"*.

There were two writers. 0.8.14 read the sidebar's active category in the timer
*and* kept the old tab-panel `draw` path that requested a page change. Clicking a
tab made the draw answer the page it was showing while the category answered the
new one; the two alternated, each redraw re-laid the area, and the sidebar came
back at its default width.

- `_tab_draw` no longer writes anything; its docstring says why. The active
  category in `_ensure_sidebar` is the only page writer.
- Like 0.8.14, the timer touches `show_region_ui`, the toolbar and the footer
  once per area, so a dragged width is never re-asserted.
- Evidence: gate green; `zip-install-0.8.15.json` 13/13. The probe now keeps the
  regressions that made 0.8.14 flicker as named checks: `tab-draw-is-read-only`
  (each tab panel's `draw` leaves the page alone), `page-and-width-stable`
  (re-reading a category three times changes neither page nor region width), and
  `respects-collapse` (a collapsed sidebar is not reopened).
- The two ad-hoc probes written while chasing this (`probe_regions.py`,
  `probe_ui_width.py`) are deleted; their measurements live in this probe and the
  ticket, so the next change starts from a durable tool instead of a new script.

Not checked: a real mouse click on a tab in a resized window — the probe sets the
category through the API because it cannot drag a region edge, and that gap is
why the flicker reached the owner.

## 0.8.16 — the pages are the custom view's own N sidebar, like the UV editor

**Owner direction, verbatim:** *"oh my god each custom view can have it's own n
panel sidebar from the tabslike the uv editor window does why don't you fucking do
that instead of wasting my time"*.

Until 0.8.15 the page panels were WINDOW-region mirrors and the sidebar held one
empty tab panel per page. That is why a wide strip sat between the content and the
tab strip: the content was outside the sidebar, so the sidebar was only tabs.

- Every page panel now registers in the custom space's `UI` region with the page
  name as its `bl_category`. The tab is the page: selecting it shows that page's
  panels inside the sidebar, exactly as an N sidebar category works. No page
  property, no tab draw, no category timer, no second writer.
- The WINDOW-region root `DMF_PT_space_main` is no longer registered in the
  custom space; it would leave an empty panel box in the main region. It stays
  defined for the Properties surface.
- The sidebar opens once per area and keeps whatever width the owner drags.
- Evidence: gate green; `zip-install-0.8.16.json` 12/12 — all twelve page panels
  report `region: UI` with the matching category, the root is absent, categories
  are selectable, and a collapsed sidebar stays collapsed;
  `pages-0.8.16.png` shows the Cloth page inside the sidebar beside its tabs.

Not checked: a real mouse click on a tab — the probe selects the category through
`active_panel_category`; the panels are registered per category, so the click and
the API take the same path.

## 0.8.17 — the self-heal no longer mistakes a current build for a stale one

**Owner report, verbatim:** *"how is it that I click the blender.exe in the
blender pr branch and it tells me that the blender version doesn't support custom
views"*.

- The PR build does support it. Run with the owner's own config, the binary at
  `Downloads/blender-PR165087/.../blender.exe` loads 0.8.16 from AppData and
  reports `SURFACE editor`, empty `EDITOR_ERROR`, and `DMF_ST_workbench`
  registered. The message comes from a session whose `SURFACE` was `sidebar`, not
  from the binary.
- The cause was ours: 0.8.16's stale-UI guard still tested for
  `DMF_PT_space_tab_setup`, a class 0.8.16 removed. A correct session therefore
  looked stale, and the guard unregistered and re-registered the editor up to
  twice per session — during which the open area can read as unavailable and the
  fallback answers the sidebar message.
- The guard now accepts either shape (a page panel in the sidebar, or the older
  tab panel). `stale-guard-quiet` is a probe check: calling the guard on a current
  build leaves `_STALE_ATTEMPTS` at 0.
- Evidence: gate green; `zip-install-0.8.17.json` 13/13 on the installed zip.

## 0.8.18 — the pages fill the view; the sidebar is not opened

**Owner direction, verbatim:** *"okay I know the n panel sidebars can take up as
much space as they want so the n panel sidebar in the custom view needs to take up
that space I know this is possible because older versions did it"*. The layout
choice that followed was a label I wrote in a question; the answer was a
selection, not a sentence the owner wrote.

A region's width cannot be set from Python (`Region.width` is read-only), and two
measured attempts to reclaim it changed nothing: `SCREEN_OT_region_toggle(
region_type='WINDOW')` returns `{'FINISHED'}` and leaves `WINDOW 1294 / UI 280`
identical, and `SCREEN_OT_region_scale('EXEC_DEFAULT')` returns `PASS_THROUGH`
(`artifacts/receipts/sidebar-fill.json`, `tools/blender_sidebar_fill_probe.py`).
So the page content moved back to the WINDOW region, which is the only region that
can fill the area, and the page buttons moved to the header.

- Page panels register in `WINDOW` with the page poll; the page buttons are a row
  of icon buttons in the header (`prop_enum` on `props_page`), next to
  `Workbench` and the version.
- The sidebar is closed when the editor opens (and `_ensure_sidebar` keeps it
  closed), so nothing sits between the page and its buttons.
- Evidence: gate green; `zip-install-0.8.18.json` 12/12 — every page panel is in
  `WINDOW`, `show_region_ui` is false, the sidebar stays closed;
  `pages-0.8.18.png` shows the Cloth page filling the area with header buttons.

Not checked: a real click on a header page button — the probe sets `props_page`
through the same enum property the buttons write.

## 0.8.20 — the page menu is the title, the icon buttons stay

**Owner request, verbatim:** *"okay fine this is acceptable but could you add a
dropdown menu in place of the workbench title for the different pages"*. The
follow-up, also verbatim: *"no don't remove the icons they're fine just replace
the title with the droppdown"*.

- The header's first control is now `prop(settings, "props_page")`: the current
  page's name as a dropdown, where the static `Workbench` label used to be.
- The row of page icon buttons is unchanged beside it, followed by the version
  and the status line.
- Evidence: gate green; `zip-install-0.8.20.json` 12/12; `pages-0.8.20.png`
  shows `Cloth` as the dropdown, the icon row, and `v0.8.20`.

Not checked: opening the dropdown with a real mouse click.

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
