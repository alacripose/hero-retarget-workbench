# TICKET-0006 — Rename to Hero Retarget Workbench

**Status:** active.
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-hero-retarget-workbench.jsonl`
**Opened:** 2026-11-12
**Selected name:** Hero Retarget Workbench

## Requirement

The owner rejected the public name `Deadlock Model Forge` because it is too
close to `Deadlock Forge`:

> can you also make sure it's not named deadlock model forge since it's too close to deadlock forge who I have not asked if that name is fine

## Contract

1. The product name becomes **Hero Retarget Workbench**.
2. The Blender addon metadata, sidebar header, package directory, build zip name,
   archive top-level directory, README, DESIGN/PRODUCT docs, architecture docs,
   landing page, CI artifact, and release title use the new name.
3. The package slug becomes `hero_retarget_workbench`; the repository becomes
   `hero-retarget-workbench`; archive paths use `hero_retarget_workbench-<version>.zip`.
4. The release page for the current build carries a zip with the new name, and
   no old-name zip remains as an alternative download.
5. Internal operator IDs keep the `dmf.*` prefix as a compatibility boundary.
   They are not the public product name and are not renamed in this ticket. A
   later ticket can migrate them if the owner wants a clean break.
6. The old name may remain in dated historical evidence paths in `tickets/` and
   `ledger/`; active docs and user-facing surfaces must use the new name.

## Non-goals

- Changing the addon version's feature scope.
- Renaming the generic `forge/` core package or the `dmf.*` operator namespace.
- Rebuilding historical evidence artifacts under new filenames.

## Acceptance

- `blender/hero_retarget_workbench/` is the installed package.
- `python tools/build_addon.py` writes
  `dist/hero_retarget_workbench-<version>.zip` with the new top-level directory.
- Unit tests, Blender zip probe, workbench probe, and real Haze probe pass after
  the rename.
- The repository is renamed `alacripose/hero-retarget-workbench`.
- The latest published release is titled with the new name and has a new-name
  zip asset; the old-name release asset is deleted.
- The landing page and README links resolve to the renamed repository.

## Evidence

- `artifacts/receipts/hero-retarget-workbench-build.txt`
- `artifacts/receipts/hero-retarget-workbench-zip.json`
- `artifacts/receipts/hero-retarget-workbench-workbench.json`
- `artifacts/receipts/hero-retarget-workbench-real-parts.json`
- `artifacts/receipts/hero-retarget-workbench-release.json`
- `artifacts/receipts/compare-panel.png`
- `artifacts/receipts/parts-panel.png`
- `ledger/ledger.jsonl`
