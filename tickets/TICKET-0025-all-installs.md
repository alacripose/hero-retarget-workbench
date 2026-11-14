# TICKET-0025 — Find clients reads every game and tools install

**Status:** implemented in 0.8.26; gate and installed-zip probe pass.
**Owner:** ala
**Opened:** 2026-11-15

## Requirement

The owner's reports, verbatim:

> it still only detects csdk13 as a client when I click the button unlick openlock where it shows me the different installs available

> your willingness to only use cases that are specific to my drives based on what you detect is dogshit the script in openlock is able to detect all kinds of paths including cs2 and cs2 based tools

## What was wrong

`refresh_clients` scanned only the clients folder (`<workspace>/clients` or the
configured folder) and the parent of the active CSDK. `find_clients` accepted
only trees with `game/bin/win64/resourcecompiler.exe`. Everything else — the
live Deadlock install, an older game tree with its own VPKs, CSDK10/12, a CS2
game, a `CSwin64_build_*` tools tree, a recorded Steam depot — was invisible.
The list therefore showed the one install beside CSDK13 and called it "clients".

## Contract

`forge/installs.py` is the general reader, modelled on Openlock's
`tools/list_installs.py` and `game_tree.py`:

1. Candidates come from Steam's registry/Program Files roots, every library in
   `libraryfolders.vdf` (including Steam folders on any drive), every
   `steamapps/common` title and `steamapps/content/<app>/<depot>` tree, plus the
   standard preview/tools placements across drives:
   `Users/*/Documents/Documents/deadlockpreview/Project8Staging/*`,
   `Users/*/Documents/deadlockpreview/Project8Staging/*`,
   `Users/*/Documents/*/Project8Staging/*`, `Users/*/Downloads/Reduced_CSDK_*`,
   `Users/*/Downloads/CSwin64_build_*`, `Users/*/*/Project8Staging/*`,
   `Projects/*/Project8Staging/*`, `dev/*/Project8Staging/*`,
   `Documents/*/Project8Staging/*`, `Downloaded Files/CSwin64_build_*`.
   It never walks a whole drive; these are bounded globs.
2. A tree is recognized by `game/<name>/gameinfo.gi`, whatever the game is:
   `citadel` (Deadlock), `csgo` (CS2), `core` (a CSDK tools host), `prime`, etc.
3. `kind` uses Openlock's rule: `tools` when `game/bin_tools` exists or the
   tree is Citadel/Core without the shipped `deadlock.exe`; otherwise `game`.
   `can_compile` is `resourcecompiler.exe` in `game/bin/win64` or
   `game/bin_tools/win64`. `can_backport` is Citadel with
   `game/citadel/pak01_dir.vpk`.
4. `refresh_clients` fills each row with label, build, kind, engine and both
   capabilities. `Use this client` sets `csdk_root` only for a compiler host and
   `mod_target_client` only for a backport target, so selecting the live game
   does not pretend it can compile.
5. The list is ordered compiler hosts first, then backport targets, then the
   rest; the UI shows kind, compiler/VPK flags and the build.

## Evidence

- `tests/test_installs.py` 6 tests: Steam common (Deadlock, CS2, CSDK), preview
  and `CSwin64` placements, Steam content depots, bounded client folders, the
  project8-without-deadlock tools rule, and empty discovery.
- On this machine `installs.discover()` reads **9** trees: live Deadlock 6861,
  the Dec 2024 depot, CSDK10 with VPKs, CSDK12, CSDK13, `CSwin64_build_10924`,
  the older H: Deadlock 6687, the older 5445 depot, and the `prime` 5433 tree.
- Installed-zip probe 14/14 including `find-clients-reads-installs` with
  `count: 9`; screenshot `artifacts/receipts/clients-setup-0.8.26.png` shows the
  list with game/tools and compiler/VPK columns.
- Gate green.

## Not checked

- Opening each listed game tree's VPKs or compiling with CSDK10/CSDK12; the
  rows are discovery and classification only.
- A machine with no Steam registry and no standard libraries; discovery then
  falls back to the configured clients folder and explicit paths.
