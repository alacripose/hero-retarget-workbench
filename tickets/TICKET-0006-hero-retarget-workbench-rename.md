# TICKET-0006 — Rename to Hero Retarget Workbench

**Status:** done; repository and release verified 2026-11-12.
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
   The rename releases as version `0.2.4`.
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
- The public release is `v0.2.4`; the old `v0.2.3` release and tag are removed.
- Main CI run `43311632441` and tag CI run `43311644789` both pass.
- The downloaded release asset `hero_retarget_workbench-0.2.4.zip` (272,442
  bytes, SHA-256 `25c8691c5517b9c3ae4b426c4ae92d7dd23e8ae977dcc7f0769789edea29e492`)
  imports with 7 panels, 40 operator classes, and 48 icons.

## Evidence

- `artifacts/receipts/hero-retarget-workbench-build.txt`
- `artifacts/receipts/hero-retarget-workbench-zip.json`
- `artifacts/receipts/hero-retarget-workbench-workbench.json`
- `artifacts/receipts/hero-retarget-workbench-real-parts.json`
- `artifacts/receipts/hero-retarget-workbench-release.json`
- `artifacts/receipts/compare-panel.png`
- `artifacts/receipts/parts-panel.png`
- `ledger/ledger.jsonl`
