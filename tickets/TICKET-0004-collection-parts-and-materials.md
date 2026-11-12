# TICKET-0004 — Collection-scoped parts and material slots

**Status:** implemented; owner visual acceptance pending.
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-parts-materials.jsonl`
**Opened:** 2026-11-12

## Requirement

The owner rejected the single-button material copy and the implicit choice of
one imported mesh:

> just like all the other things are not supposed to be press one button and it
> does things for you there seriously needs to be a better materials and model
> parts selection that works with blender collections

The concrete requirements:

1. Importing a custom model puts its imported objects in a dedicated Blender
   collection and records that collection on the scene settings.
2. A `Parts & Materials` subpanel scans the chosen collection, including child
   collections, and lists every mesh part. The active part is explicit; the
   panel never silently chooses a different mesh after a scan.
3. The user can use the active Blender collection, scan it, and select the
   working part. Fit, weights, material assignment, and export read that active
   part and name it in the status line.
4. Materials are assigned one slot at a time. The user selects a source object
   and a source slot, selects a part slot, then assigns, appends, or clears.
   There is no `Replace with hero materials` action.
5. The source list and the active part's slot list are visible native UI lists.
   Assign replaces the selected part slot; append adds a slot; clear removes
   the selected part slot and remaps face material indices.
6. The material roots remain content roots. This ticket does not parse or
   rewrite `.vmat` files; it changes only Blender material-slot selection.

## Non-goals

- Parsing, rewriting, or flattening Source 2 `.vmat` files.
- Automatically mapping material names or choosing a nearest part.
- Merging multiple mesh parts into one export mesh. Export reads the active
  part; a future ticket can add a deliberate join or multi-part export.
- Changing the bone map, weight solver, proof gate, or vmdl staging rules.

## Acceptance

- `blender_probe.py` creates a collection with two custom parts, scans it,
  switches the active part both ways, appends every hero slot through explicit
  calls, replaces one selected slot, clears one slot, appends it back, and
  stages the result.
- `blender_workbench_probe.py` still passes every existing workbench and proof
  check with the new properties registered.
- `blender_zip_probe.py` still imports the zip, registers the new panel and
  operators, and validates every icon.
- The panel is checked in a real Blender window at a sidebar width; the active
  part, source slot, and part slot are distinguishable without opening a modal.

## Evidence

- `artifacts/receipts/deadlock-model-forge-workbench.json`
- `artifacts/receipts/deadlock-model-forge-zip.json`
- `artifacts/receipts/compare-panel.png`
- `artifacts/receipts/parts-panel.png`
- `artifacts/receipts/deadlock-model-forge-real-parts.json`
- `artifacts/parts-probe-stage/content/citadel_addons/probe/stage.json`
- `ledger/ledger.jsonl`
