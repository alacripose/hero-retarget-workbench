# PRODUCT

## Product

Deadlock Model Forge is a Blender 5.4 addon for porting a custom model onto a
live Deadlock hero. It is a tool, not a hosted service or a public website.

## User

A modder who already knows Deadlock, Source 2 Viewer, Blender, and the reduced
CSDK13 toolchain. They are working inside Blender with a live hero extraction
and a custom mesh. They need a repeatable handoff, not a tutorial.

## Job

Choose a hero from the current live build, import its real body and materials,
map and rename the custom skeleton, compare both models in a split viewport,
solve and prove the weights, then produce a compiler-ready addon folder without
touching the hero vmdl. The user makes the mapping and extra-bone decisions; the
addon must show what succeeded, what was skipped, and what still needs a real
compiler run.

## Truth and constraints

- The hero source is the current live game through S2V.
- CSDK13 is only the compiler.
- The S2V vmdl is opaque and is copied unchanged.
- Materials are copied as live `.vmat` files, not rebuilt.
- The addon handles the custom model, fit, retargeting, and materials.
- Failure messages must name the missing file, object, or stage rather than
  offering a generic success state.

## Success

A user can finish the manual workbench and land at a staged folder that another
person can compile, with the vmdl hash proving it was not modified and a BLAKE3
Axis proof showing the checks that passed. The UI should feel like a native
Blender tool with a short, honest status line.

## Assumptions

- Blender's native theme and controls are the visual system; this is a sidebar,
  not a branded standalone application.
- The user has PulseSrcOps installed for DMX import/export.
- Some S2V CLI extractions do not emit a `.vmdl`; the user supplies the one from
  their S2V extraction. The addon must never fill that gap by generating one.

## Public landing surface

`landing/index.html` is the public Persuade surface for the addon. It reports
the live-build workbench, the real Haze readings, the hard boundaries, and the
install path. It is separate from the native Blender sidebar, which remains the
Operate surface. The landing page does not add a second product claim: the
README, STATUS.md, tickets, and ledger remain the evidence record.

The public source repository is `alacripose/deadlock-model-forge`. The landing
page links to that repository and to `README.md`, `docs/ARCHITECTURE.md`, and
`STATUS.md` after the first push.
