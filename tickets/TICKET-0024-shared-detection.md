# TICKET-0024 — one detection result for every page

**Status:** implemented in 0.8.23; gate and installed-zip probe pass.
**Owner:** ala
**Opened:** 2026-11-15

## Requirement

The owner's message, verbatim:

> you know the opnelock repo with the install.ps1 and install.cmd have examples that allow for detecting intall paths also now even in 8.22 other pages aren't seeing that the s2v and game installs are detected which shouldn't be possible when we're supposed to be gating features and using tests

## What was wrong

Three separate faults made a detected install look missing on other pages.

1. **A finished failure outlived its cause.** 0.8.21 added the shared job
   card and 0.8.22 drew it on every page. `job_state=FAILED` and `job_log`
   were never cleared, so a failed detection from before the paths were set
   kept rendering on Source, Mods, Setup and the rest. The header status line
   carried the same stale sentence.
2. **The live detection read RNA from a worker thread.** `dmf.detect`'s
   `work(progress)` called `core.detect_environment(settings, module)` inside
   the daemon thread. Blender data is not thread-safe; a saved path can arrive
   empty there even though Setup's main-thread detection just read it. Extract
   and compile did the same.
3. **`detect_paths` threw away partial results.** It required the game before
   saving anything, so finding the viewer and CSDK but not the install reported
   failure and persisted nothing. Scene paths were also used raw: a Blender
   relative path (`//tools/...`) was handed to `Path()` without `bpy.path.abspath`.

## Contract

- Detection runs on the main thread. The immutable `Environment` dataclass is
  captured before a job starts; worker functions receive it and never read
  `settings`.
- Editing `deadlock_root`, `s2v_cli` or `csdk_root` clears a failed job card and
  a "not found / not detected" status. All three properties share that callback.
- `dmf.detect_paths` saves each tool it finds independently and reports the
  missing ones by name. Finding the game clears the last job's card, because it
  proves the current state; a partial result is a WARN, not a lost detection.
- `dmf.clear_job` dismisses a finished card from its own X button.
- Steam detection reads `appmanifest_1422450.acf` so a library whose folder was
  renamed is found, and scans one bounded level of `steamapps/common` when the
  manifest is absent. No personal folder or drive letter is a candidate; the
  existing source scan still enforces that.
- A Source 2 Viewer installed by **Download & install** is found from the
  configured tools folder, the workspace `tools` folder, and `tools/s2v`;
  Steam's `common/Source2Viewer` folders are also checked. A scene path is
  resolved with `bpy.path.abspath` before it reaches `paths.find_s2v`.
- **0.8.25 moved-tool fallback.** A saved CLI path whose file no longer exists
  falls back to a bounded search of the standard `Downloads` and `Desktop`
  folders (depth 3, pruned) and Steam common. A saved CSDK folder whose name
  contains `csdk` and no longer exists falls back to one level of the same
  folders, accepting only a tree with `resourcecompiler.exe`. A path that exists
  but is the wrong kind (a GUI-only folder, a deliberately different pick) is
  still refused, not overruled. The detection status says "CLI found elsewhere"
  when the saved path was replaced.

## Non-goals

- Searching arbitrary user folders. Only `Downloads` and `Desktop` are read,
  only at depth 3 for the viewer and one level for a CSDK folder, and only when
  a saved path has gone missing. No vendor folder name or absolute user path is
  in the source; `test_source_has_no_personal_or_drive_letter_defaults` keeps it
  that way.
- Picking a CSDK for the user when several exist. The Setup field remains the
  authority; env `CSDK13_ROOT` is the headless fallback. The fallback only runs
  for a saved CSDK path that is gone.
- Changing which page owns the detection buttons.

## Evidence

- `tests/test_paths.py` 14 tests: appmanifest rename, common-folder scan without
  a manifest, tools-root viewer discovery, moved-CLI fallback, unpacked CSDK
  discovery, explicit path precedence, GUI-only refusal, and the source scan that
  forbids baked personal paths.
- Installed-zip probe 13/13, including `path-edit-clears-stale-failure`
  (failed job fields set, a path edited, state/log/progress empty).
- `artifacts/receipts/source-0.8.23.png` shows the Source page with no stale
  failure card after the fix.
- Gate green.

## Not checked

- A real click of `Detect live heroes` against the live game in a Blender
  session with the new zip. The saved scene was read to confirm the stale path:
  its `s2v_cli` pointed at `openlock_modern/tools/s2v/Source2Viewer-CLI.exe`,
  which no longer exists. `forge.paths.detect` on this machine now resolves
  `Downloads/cli-windows-x64/Source2Viewer-CLI.exe` and `Downloads/Reduced_CSDK_13`
  with no problems; that is the detection layer, not a live hero-table run.
- The Downloads/Desktop search on a machine where both folders are enormous;
  the walk is bounded and pruned, but no timing was recorded.
