# TICKET-0011 — 0.2.9: background staging, one addon-folder source, panel layout

**Status:** implemented; gate, zip probe and panel draw probe must be observed before release.
**Owner:** ala
**Authority:** owner message recorded in this turn (see below)
**Opened:** 2026-11-13

## Requirement

The owner's message, verbatim:

> why does the export & stage and compile buttons block the main thread??? why are there so many inconsistencies? why are mandatory skills not being loaded? why are extra skills from my global agents skills folder in my user directory not being used? I want you to utilize as many as possible to create a refined 0.2.9 version that reorganizes everything into a better layout and descriptions (not an excuse to claudify the prose)

## Findings

1. **Export & stage blocked the main thread** because one `execute()` did the
   join, the PulseSrcOps DMX export, the full extraction/material copy and the
   SHA-256/BLAKE3 pass over every staged file. Only the first two need Blender.
2. **Compile did not block.** It already runs in `jobs.BackgroundJob`; the
   operator only resolves paths and starts the job. The perceived block was the
   0.2.7 install (see the partial-zip repair), not the compile path.
3. **Inconsistency had four concrete causes:**
   - `stage_dir` was simultaneously the install destination, the "installed"
     flag and a display path.
   - The panel claimed "installed" whenever `stage_dir` was a non-empty string,
     even when no `stage.json` existed.
   - Compile read the stage from `stage_dir` but the folder name from
     `addon_name`, so changing the name after staging looked in the wrong place.
   - Docs, STATUS and probe tools described the retired temporary mirror.
4. **Skills.** `impeccable` is mandatory per AGENTS.md but is absent from this
   session's skill catalog. It lives at `C:\Users\ala\.agents\skills\impeccable`;
   the family AGENTS.md files now name that path. Its `context` launcher produced
   no output, so PRODUCT.md, DESIGN.md, `reference/operate.md` and
   `reference/craft-floor.md` were read directly.

## Contract

1. Export & stage keeps join/export on the main thread and moves the copy and
   hashing to the background job; the operator returns `FINISHED` immediately
   and the status reports progress.
2. `core.csdk_addon_root(settings)` and `core.csdk_addon_folder(settings)` are the single
   source for the addon location; export, compile and the panel use them.
3. `stage_dir` overrides the install root only when it is a CSDK13 install.
4. Panel state is derived: `staged` from `stage.json`, `compiled` from the
   `.vmdl_c` in the game addon.
5. Subpanels are ordered by workflow and the handoff subpanel is labelled
   **CSDK Addon**. `DMF_PT_handoff` keeps its id so saved panel states survive.
6. Labels stay sentence case, name the action, and keep the project's own
   register; no decorative prose.

## Not claimed

No stage or compile has been observed against the owner's `.blend` after this
change. The evidence is the gate, the zip probe, and the panel draw probe.
