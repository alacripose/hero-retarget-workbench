# TICKET-0023 — backports across game versions and their own VPKs

**Status:** first slice implemented; unit tests, gate and installed-zip probe pass.
**Owner:** ala
**Opened:** 2026-11-15

## Requirement

The owner's message, verbatim:

> okay the next work is going to be the game version agnostiscm features for stuff like backports into the csdk10 and older versions of the game, it's going to need to be able to handle a ton of weird cases where someone needs to use a hero model from a version of the game with it's own vpks

## What was in the way

`forge/backport.py` assumed one shape for an older client: exactly
`game/citadel/pak01_dir.vpk` plus `game/citadel/gameinfo.gi`, at an install root.
It extracted the mod's own model path from that one pak. Old builds break every
part of that assumption:

- the target may be an install, a `game` folder, or `game/citadel` itself;
- the hero may sit in a second pack (`pak02_dir.vpk`) or an `addons` pack;
- the target may use a single-file `pak01.vpk` with no `gameinfo.gi`;
- the path the mod was built with may no longer exist because the hero moved
  between `heroes_staging`, `heroes_wip` and `heroes`, or the folder was renamed
  (`doorman` → `doorman_v2`);
- the mod may ship only compiled `_c` entries.

The existing `backport_package` also called `migrate_trees(..., addon=...)` while
the function takes `addon_name`, so the path had never run end to end.

## Contract

1. `client_build(root)` accepts an install, its `game` folder, or
   `game/citadel`. It finds `gameinfo.gi` when present and keeps it optional.
2. Every top-level `*.vpk` in the game folder and in its `addons` folder is a
   candidate. Chunk files (`pak01_000.vpk`) are not packs; their `_dir.vpk` is.
   `_dir.vpk` sorts first, then single-file packs by name.
3. `find_client_model` reads each candidate's directory, never its file data.
   Normalised paths make Windows separators and case irrelevant, and a source
   `.vmdl` matches its compiled `.vmdl_c` sibling.
4. The requested path wins when present in any pack. Otherwise the mod's hero
   slug chooses among models in that build, preferring `heroes_staging`, then
   `heroes_wip`, then `heroes`, and source over compiled.
5. Extraction runs against the pack that actually holds the model, with that
   build's `gameinfo.gi` when it has one, and decompiles it to source.
6. The mod's old source model is the requested path, then the client path, then
   the only `.vmdl` in the extracted package; a compiled-only mod is not
   rejected before extraction.
7. The manifest records the target root, the pack used, the resolved model, the
   requested model, whether the path was exact, and the target `gameinfo.gi`.
   The Mods page reports the resolved path and marks a moved path.
8. A build with no packs, no model, or only chunk files is refused by name,
   naming what was searched. No model is invented and no path is silently
   rewritten without the manifest flag.

## Non-goals

- Downloading or installing old game builds.
- Parsing a build's roster or version metadata beyond `gameinfo.gi` presence.
- Running CSDK10's compiler automatically, or switching the Handoff compiler to
  the target client. The target compiler is not chosen for the user.
- Making a mod's cloth sections compile against a target that never had them;
  that remains the target compiler's answer, recorded by the existing port
  receipt.
- Rewriting the mod's own model path; the output model uses the target build's
  resolved path (`vmdl_relative`) and the manifest names the substitution.

## Evidence

- `tests/test_backport.py`: 8 tests. They cover all three roots, multiple packs
  and addon packs with chunk exclusion, exact match in a second pack, `.vmdl` ↔
  `.vmdl_c` matching, slug fallback with a moved model, missing-model refusal
  naming the searched pack count, a single-file pack without `gameinfo.gi`, and a
  patched end-to-end call that proves the target model/pack reach migration under
  `addon_name` and land in the manifest.
- Gate green; installed-zip probe 12/12 for 0.8.22.
- The Mods panel hint now states that backport searches every VPK and falls back
  to the hero when the path moved.

## Not checked

- A real CSDK10 install and a real older client extract through Source 2
  Viewer; the tests use synthetic VPK trees and a patched extractor.
- Whether CSDK10's `resourcecompiler` accepts cloth sections from newer builds.
- Roster or version detection beyond the target's own model paths.
