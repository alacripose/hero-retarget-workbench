# TICKET-0019 — a fresh hero import builds the cloth it brought

Status: implemented in 0.7.1
Authority: `logs/authority/2026-11-14-import-builds-cloth.jsonl`

## Owner request

Close the loop on the original symptom: importing Shiv must bring his hair and
jacket in **cloth-capable**, not merely present. The import must end with those
meshes, their pin groups, `DMF <chain>` bone chains and `DMF Cloth` modifiers, and
the Cloth page must list them.

## What was actually dropping them

0.6.x imported the meshes and scanned the chains, but never ran the chain-to-cloth
build; the Cloth page could build one chain by hand and nothing built on import.
0.7.1 calls `cloth_ops.build_import_cloth` at the end of `dmf.import_hero`,
inside the import try-block so a build failure warns instead of aborting the
import, and records why any chain was skipped in `settings.cloth_build_skipped`.

Two real constraints surfaced while closing it:

1. **Blender allows one Cloth modifier per object.** `ObjectModifiers.new(name,
   "CLOTH")` returns `None` on the second call for the same mesh (checked with
   `artifacts/probes/cloth-two-modifiers.py`). So a mesh keeps one simulation,
   named for its main chain (`DMF Cloth coat` on `shiv_jacket4`, `DMF Cloth hair`
   on `shiv_hair3`); every other chain on that mesh keeps its own pin group and
   bone chain and folds its pinned vertices into the shared pin group.
2. **A body is not cloth.** `collar_L`/`collar_R` weights live only on
   `shiv_body`. Building there would simulate the whole 35k-vertex body, so those
   chains are reported as skipped with the reason, not built.

Two probe defects had been hiding the state: both probes re-ran `scan_chains`
after the import, which clears the rows the import had just built, and the cloth
probe reused a loop variable named `bones`, which clobbered the hero bone count
in the receipt.

## Evidence (0.7.1)

- `tools/blender_cloth_probe.py`, stock daily and PR 165087: 21/21 checks, no
  addon tracebacks. Receipts `artifacts/receipts/cloth.json`,
  `artifacts/receipts/cloth-pr.json`.
- Fresh import on Shiv: `shiv_jacket4` 3,880 vertices with `DMF Cloth coat`
  (ARMATURE then CLOTH), `coat` 932 pinned, `sleeve_L` 388, `sleeve_R` 176;
  `shiv_hair3` 2,068 vertices with `DMF Cloth hair`, `hair` 434,
  `collar_back` 436; chains `DMF coat chain`, `DMF sleeve_L chain`,
  `DMF sleeve_R chain`, `DMF hair chain`, `DMF collar_back chain` in `DMF Cloth`.
- `tools/blender_pages_gui_probe.py`: 17/17 page draws, 0 exceptions, log scan
  clean on both surfaces; screenshots `artifacts/receipts/cloth-page-editor.png`
  and `artifacts/receipts/cloth-page-properties.png`.
- Not checked: an actual cloth simulation step (no frame was played); the stock
  Properties screenshot still shows native panels above the page, so the editor
  screenshot is the one that shows the Cloth parts list.
