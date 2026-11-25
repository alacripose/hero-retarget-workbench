# 2026-11-23 — the Scout port reads its own build, and its tool has a Popit surface

## The requirement this obeys

The owner's instruction, verbatim:

> you will have to create popit uis for the tools that you make this is a new requiremnt for the probes that
> you use to work

So a tool is not finished when its Python runs. It is finished when the probe reads the tool's **Popit
surface** and the surface carries the reading the same run produced. `tools/scout_update.py probe` starts
the tool's own server, fetches `/` and `/report.json` over loopback HTTP, and refuses unless the page
carries `data-popit="scout-update"`, `id="port-state"`, `id="drift-table"`, `id="graph-clips"` and the
served report's own schema and check rows.

## What the probe attempted

| Step | Command | What it reads |
|---|---|---|
| Dota tools into the workspace | `python tools/scout_update.py extract-dota --zip "F:/Downloaded Files/dota-0423lite_ship.zip" --out artifacts/dota-tools` | only `content/dota_addons/animgraph/` and `game/bin/win64/resourcecompiler.exe` |
| The port and its scripts | `python tools/scout_update.py report --workspace F:/Documents --game D:/SteamLibrary/steamapps/common/Deadlock --live-heroes <extracted> --dota-tools artifacts/dota-tools --graph <template>` | TF2 Scout sources, the port's `heroes.vdata`, the live roster, the Dota graph |
| The graph retarget | `python tools/scout_update.py animgraph --template … --skeleton <port skeleton> --variation Scout --out artifacts/scout-update/animgraph/hero.vnmgraph+scout.vnmgraph` | replaces `m_variationID` and `m_skeleton` only; node and clip counts must not move |
| The surface | `python tools/scout_update.py probe …` | the Popit page and its `/report.json` |

## What is measured, and what is refused

- The port workspace is `F:/Documents`: `scout.qc`, `scout.mdl`, `scout_ANIM.mdl` and the SMD animation
  folders, plus its own `heroes.vdata` (a snapshot of the roster, not a parse of it).
- The Dota 2 tools tree is `dota-0423lite_ship.zip` on `F:`: 13,876 entries, 1,019,266,484 bytes, with
  `content/dota_addons/animgraph/animgraphs/biped_standard.vanmgrph` (328,344 bytes) and a
  `resourcecompiler.exe` under `game/bin/win64`. The extraction keeps `content/dota_addons/animgraph/`,
  `game/bin/` and `game/dota/gameinfo.gi`: **278 files, 588,314,380 bytes**. `game/bin` is not optional —
  the compiler is a `binlaunch` wrapper and `game/bin/win64/tools/animgraph_editor.dll` is the editor.
- The live roster is read from the installed build's own `scripts/heroes.vdata` through Source 2 Viewer,
  and the drift is reported per hero: **6 added, 2 gone, 13 moved** against the port's 63-entry snapshot.
- The Dota graph reads as `animgraph19`: **164 nodes, 24 sequence names**. **0 of 24** have a source
  animation in the port (TF2's `@…_corrective_animation` names do not match `walkn`, `crouch_walkne`).
- The reduced CSDK13 cannot compile a graph: its `animationsystem.dll` is disabled and every attempt ends
  `FS: Tried to FileExists NULL filename`. The Dota toolchain compiled `biped_standard.vanmgrph` to a
  **62,191-byte** `.vanmgrph_c` once the graph's model sat under the addon root (`OK: 1 compiled`).
- The port's hero binding is **not** recorded in the workspace's hero table: no entry names a Scout model.
  The tool therefore takes `--hero` and refuses `hero-not-declared` rather than picking one. That refusal is
  the finding, not a gap in the probe.

## Why the probe is a page and not a print

A print can say `pass` while the surface the owner would look at shows nothing, and that is how a tool ships
with an unreadable state. The probe reads the rendered page's contract and the served JSON together, so a
surface that stops rendering the drift table fails the probe by name.

## Not checked

- The compiled `.vnmgraph_c` in the live game (the compiler run is recorded separately, with its own return
  code, and a compile that does not produce `_c` is a `fail`, never a pass).
- The port in game. No launch was performed for this probe.
