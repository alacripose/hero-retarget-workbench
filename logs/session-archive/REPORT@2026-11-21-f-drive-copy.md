# The F-drive session archive, measured

Root: `F:\Documents\_session-archive`. Read on 2026-11-21, after the owner named the path.

## What it is

A per-thread export of 13 Freebuff stores, written by a `session-archive/1` run at
`2026-11-21T20:00:22Z`. Each thread is a `.jsonl` whose first record carries the thread id
and every later record carries `seq`, `at`, `role`, `parts`, `attachments`. The stores are
the family's project sessions: openlock, shploingus-clean, planet-shploingus,
ala_package_designer, agent_god_files, ala_civ_bots_prototype, portal_shell, secure_shell_v2,
deadlock-model-forge, openlock_modern, testport1, db-mc-indev, and one local project.

## What the manifest claims, and what the disk holds

| measure | manifest | measured |
|---|---|---|
| stores | 13 | 13 |
| threads | 43 | 43 distinct ids |
| messages | 3781 | 3781, from `records − 1` per file |
| thread files | — | 77 |
| files matching the pinned digest | — | 43 |
| files not matching it | — | 34 |
| duplicated threads | — | 33, and no pair is byte-identical |

Every file's record count equals its manifest message count plus one, because the header
record is not a message. That off-by-one is arithmetic, not loss.

## Three defects, recorded rather than repaired

1. **`raw-copies.json` names thirteen database copies under `session-archive\raw\`, and this
   root has no `raw` folder.** Each row reports `match: true` for a copy that is not here.
   The thirteen source stores still exist on `C:`, and all thirteen match their recorded byte
   counts today, so nothing is lost. The archive's own copy claim is what is unsupported.
2. **Thirty-three threads appear twice, in two generations that differ in bytes.** The
   manifest pins one generation per thread, and that pinned generation is the one read here.
   The other is retained but unaccounted for.
3. **Eight threads carry a title and a manifest row but export zero messages.** Seven of the
   eight titles are real prompts, so their text is unreadable from the archive. They include
   the deadlock-model-forge threads on the thick Mayu body, the CSDK stage, the openlock shell
   update, and the agent-god-files fork.

## What the threads establish

These are the family's own words, read from the pinned generation.

- **The layered references are named, and they are different things.** shploingus-clean is
  the design reference and the data implementation. shploingus is the architectural
  reference. agent_god_files is the logic reference. ala-cities is the architecture source
  for gameplay, and its expanded features live in the GRILLING C documents.
- **The world format is cubic chunks, not columns.** The owner corrected this repeatedly:
  "it is actual cubic chunks not fucking columns". Voxels are 1 m in game and one eighth of
  real-world scale; the terrain itself is real-world terrain scaled down, not voxel terrain.
- **The civilians author the city.** The owner's standard is that the citizens build through
  the ingested logic, and an agent that shapes the city itself has failed the design.
- **Materials cannot come from nothing.** The owner flagged "materials are being created from
  nothing" as a violation of ala-cities' design reference. C9 makes the same claim mechanical.
- **The axis crates are the gate, not a rendering replacement.** Axis adds performance
  optimisation and refusal; it does not replace a renderer with cells.
- **Civilians are piloted on CPU through the CUA driver, run by laya and von.** The patch
  corpus is meant to become recipes through the dynamic classifier built from prose-logic
  output, and the civilians carry a cut-down proof-of-work model under a hardened axis gate.
- **The shell lineage runs openlock → dl-enclave.** The Debian host is the server side. Its
  display shell or TUI fallback stands in place of a desktop environment. Hand-rolled shells
  are to be refused by name, and the port must come from openlock's own declaration data.
- **The taskbar expansion is recorded and unbuilt.** Move the taskbar to any of four corners,
  and a setting that makes window buttons circular.

## What the shell threads add

- **A window glyph set is named.** Alpha shell uses `◧ ⬓ ⇱ ×`, and the owner called the
  `M P _ [] X` set awful. A move glyph `✥` belongs in the bar for windows dragged off-screen.
- **Window frames disappear when the taskbar hides.** Pinned windows keep their content and
  lose their controls until the bar opens.
- **The client mod is not Deadworks.** The shell mounts as a VPK UI mod, agnostic of install
  location, and must persist when no server is connected.
- **Bots are never verification.** The owner is the witness; bots may be used for other work.

## What was read, and what remains

Read in full: the manifest, `raw-copies.json`, and the owner-word files for security
restoration, python use, city-builder integration, package designer, v4 proof, secure
enclave planning, the Windows terminal thread, both Deadworks threads, axis baselines,
shapers on cadence, the rust ingest threads, moon reflectance, renderer merge fixes, voxel
clouds, GPU quad bloat, the rendering bug, portal shell, corpus widening, profile32, and the
screenshots thread. The ui-shell thread was read to line 330 of 3100.

Not yet read: the remainder of ui-shell, and the owner-word files for clean-room rebuild,
subvoxel octree, shader fix, the Minecraft plan, and three one-line threads.

One correction to this document's own earlier reading: the ui-shell thread is 3,100 lines,
the largest owner-word set in the archive, at 158,569 characters.

The archive is evidence, not authority. Its threads predate the current round, and where a
thread contradicts a later ruling the later ruling stands.
