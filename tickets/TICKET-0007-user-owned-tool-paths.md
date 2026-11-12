# TICKET-0007 — User-owned tool paths

**Status:** done; verified by unit, zip, persistence, and GUI probes.
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-user-owned-tool-paths.jsonl`
**Opened:** 2026-11-12

## Requirement

The owner rejected machine-specific defaults and script-provided paths:

> it seriously can't be dependant on my personal drives and directoruies, what if someone has something newer? the paths should not be set by a python script someone runs it should be something the user sets up and can save to their default blend file

## Contract

1. The addon exposes the Deadlock install, Source 2 Viewer CLI, CSDK13 root,
   workspace, extraction, and stage folders as user-facing settings.
2. Those settings live on the scene property group, so they are written into the
   `.blend` and can be saved into the user's startup file.
3. A visible Setup panel in the Deadlock sidebar edits the tool paths and the
   workspace. It does not require a Python script or environment variable.
4. Path detection prefers the scene values. Environment variables remain a
   fallback for headless commands; generic Steam discovery remains a fallback
   when no value is set.
5. No personal home-directory or drive-letter path is a built-in candidate.
   The addon must not depend on `openlock_modern`, the owner's Downloads folder,
   or a particular Steam library letter.
6. The extract, detect, and compile actions use the same configured paths and
   name the Setup field when one is missing.
7. A `Detect installed` action fills the scene fields from what it finds without
   requiring the user to know the paths first.

## Non-goals

- Moving the addon's runtime files out of Blender's user data directory.
- Replacing PulseSrcOps or SourceIO.
- Changing the staging, retarget, or CSDK compile contracts.
- Guessing a tool path from a personal folder when the user has not set it.

## Acceptance

- `python -m unittest discover -s tests -v` passes, including explicit path
  precedence and the absence of personal defaults.
- The addon registers with a Setup panel and a detect-paths operator.
- A headless probe writes the paths to a scene, saves it, reloads it, and reads
  the same values back.
- The zip probe sees the new panel and operator counts.
- README and the addon UI tell the user to save the startup file, not to run a
  path-setting script.

## Evidence

- `artifacts/receipts/hero-retarget-workbench-path-config.json`
- `artifacts/receipts/hero-retarget-workbench-zip.json`
- `artifacts/receipts/hero-retarget-workbench-workbench.json`
- `artifacts/receipts/compare-panel.png`
- `ledger/ledger.jsonl`

All 58 unit tests pass. The extracted zip reports 8 panels, 41 operator
classes, 50 icons, `path_config_saved: true`, `path_detect_operator: true`, and
`path_namespace_isolated: true`. The installed addon was then run against the
user's actual Deadlock 6861, Source 2 Viewer, and CSDK13 paths; `detect_paths`
returned `FINISHED` and reported `all tool paths found`.

The old `deadlock_model_forge` addon was still enabled and had already loaded a
top-level `forge` module. The new addon now imports its own
`hero_retarget_workbench.forge` namespace, so the old module cannot supply the
old `detect()` signature. The Setup panel drew in a real Blender window
alongside the six workflow subpanels.

GitHub Actions run `43317516973` passed on `5c48744`: 58 unit tests, addon zip
build, zip identity, and artifact upload. The release job was skipped because
this was a push to `main`, not a version tag. The CI-built zip is 274,119 bytes
(SHA-256 `f6f7ae99ff32278a38ae45b23b89f2b0c4c1c9ce10170bbff6471698c1248abd`); the
local working-tree zip is 273,624 bytes because Windows CI checks out different
line endings and timestamps.
