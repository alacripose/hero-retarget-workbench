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

## Non-goals

- Searching the user's Documents/Downloads for a viewer. There is no installer
  location for Source 2 Viewer that can be assumed, and the project rule against
  personal path defaults stands.
- Picking a CSDK for the user when several exist. The Setup field remains the
  authority; env `CSDK13_ROOT` is the headless fallback.
- Changing which page owns the detection buttons.

## Evidence

- `tests/test_paths.py` 12 tests: appmanifest rename, common-folder scan without
  a manifest, tools-root viewer discovery, explicit path precedence, GUI-only
  refusal, and the source scan that forbids personal defaults.
- Installed-zip probe 13/13, including `path-edit-clears-stale-failure`
  (failed job fields set, a path edited, state/log/progress empty).
- `artifacts/receipts/source-0.8.23.png` shows the Source page with no stale
  failure card after the fix.
- Gate green.

## Not checked

- A real click of `Detect live heroes` against a live S2V path in this session;
  the machine's previously documented `openlock_modern/tools/s2v` folder is now
  empty and the CLI lives elsewhere, so the probe uses a fresh profile.
- CSDK auto-detection; it remains an explicit path.
