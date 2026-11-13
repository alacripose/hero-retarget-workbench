# TICKET-0014 — the S2V detector resolves the CLI instead of refusing the pick

**Status:** implemented; unit tests and the zip probe cover both cases.
**Owner:** ala
**Opened:** 2026-11-13

## Report

> okay but you broke the s2v cli detector so now it doesn't work properly
> because gui s2v does not expose cli properties

## What was wrong

`forge/paths.find_s2v` accepted a configured path only when it was a directory
containing `Source2Viewer-CLI.exe` or the CLI file itself. Any other file —
including `Source2Viewer.exe`, the GUI, which ships **in the same folder** as the
CLI — returned `None`. Commit c675c6b added that refusal for a good reason (the
GUI cannot run `-i … --game …`, so it must never be executed as the extractor),
but it threw away the information that was already in hand: the folder.

So a Setup field pointing at the GUI, or at a folder the user picked from the
GUI's location, produced "Source 2 Viewer was not found" and left Detect
apparently broken, while the CLI sat next to the file.

A second, smaller defect: `detect()` builds its problem text from its
`s2v_cli` argument, but `find_s2v` also reads `S2V_CLI` from the environment.
A headless run with only the variable set reported a bare "not found" for a path
it had actually been given.

## Contract

1. `find_s2v(None)` keeps the old behaviour: the `S2V_CLI` environment value,
   then `PATH`. No personal or drive-letter candidate is added (TICKET-0007).
2. A configured **directory** resolves to `Source2Viewer-CLI.exe` inside it.
3. A configured **CLI file** is used as given.
4. A configured **GUI file**, or any other file in an install folder, resolves to
   the CLI beside it. The GUI is still never returned or executed.
5. If the folder holds only the GUI, nothing is returned and
   `paths.s2v_gui_note()` explains that the GUI has no CLI mode and names the file
   to choose. `detect()` puts that note in `env.problems`, and the Setup panel
   shows it as an error bubble next to the field, before Detect is pressed.
6. `DMF_OT_detect_paths` reports the substitution ("using Source2Viewer-CLI.exe
   beside the chosen file") rather than silently rewriting the field.
7. `detect()` uses `S2V_CLI` for its message when no argument was passed.

## Evidence

- `tests/test_paths.py` (9 tests): directory pick, GUI path resolving to the CLI
  beside it, GUI folder without a CLI returning nothing, GUI-only note wording
  and that a resolving pick has no note.
- `tools/blender_zip_probe.py` now asserts both live outcomes through the addon:
  a GUI pick resolves and reports the substitution; a GUI-only folder leaves the
  WARN status naming the GUI.
- `python tools/project.py gate` passes.

## Not claimed

No real S2V extraction was run in this change, and the owner's own folder layout
was not inspected beyond the documented `openlock_modern\tools\s2v` install.
