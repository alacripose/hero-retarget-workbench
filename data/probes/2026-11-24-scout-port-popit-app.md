# 2026-11-24 — the port is Scout's, and it now has a Popit-shell application

## The correction this pass records

The owner's words, verbatim:

> I never said it had anything to do with mapping onto frank I said it had to use the deadlock model
> forge and create popit-shell applications for working with it

The previous slice bound Scout's clips to `models/heroes_wip/frank/frank.vnmskel` and put a Scout entry
into the live hero table on top of that rig. That was my inference, not the owner's instruction, and it
is withdrawn as the plan. Scout is the port's own hero with its own skeleton and its own animations;
what stands is the forge that reads the port, and now the application surface for working on it.

Nothing was deleted. The frank-bound artifacts stay where they are and the application names them as
superseded, because a kept artifact with an honest label is evidence and a deleted one is a hole:

- `artifacts/scout-update/clips` — baked against `models/heroes_wip/frank/frank.vnmskel`
- `artifacts/scout-update/vpk/scout_animgraph_dir.vpk` — packs those clips plus a hero table entry

## What was built

`popit_apps/scout_port/` — a Popit-shell application in the shell's own pattern (`popit-shell/server.py`
names the session archive as the model: one loopback `ThreadingHTTPServer`, no framework, one JSON API,
a view that reads it).

| Piece | What it does |
|---|---|
| `server.py` | `127.0.0.1:8795`; `/`, `/api/state`, `/api/sequences`; reads the port through `forge.scout`, so the counts are the forge's own |
| `ui/index.html`, `ui/style.css`, `ui/app.js` | the family register: ground `#0c0e11`, one gold `#f0c454`, square data surfaces, Archivo + IBM Plex Mono, the square-in-square mark |
| `probe.py` | starts the app's own server on an ephemeral port, reads `/` and `/api/state`, fails by name |
| `start.cmd` | what the shell's Start row runs |

It is registered in the shell: `popit-shell/server.py`'s `tools()` gained a **Scout Port** row (target
overridable with `SCOUT_PORT_APP`), and `python tools/gate.py` still reports **21 checks, 0 refusals**.

## What the surface reads, measured

```
port F:\Documents · 379 $sequence names · 1,414 animation SMD
steps: inventory pass · skeleton blocked · clips blocked · graph blocked · pack blocked · hero blocked
```

The refusals are the point of the page: `skeleton-not-built` on the skeleton step, `hero-not-registered`
on the hero step. The port ships a Source 1 model and SMDs; a Deadlock hero needs a `.vnmskel` built from
**that** rig, and until it exists every later step says so instead of inventing a rig to bake onto.

- `python popit_apps/scout_port/probe.py` → **PASS (8/8)**: page served, `data-popit="scout-port"`, the
  four required ids, the state schema, six shaped steps, the skeleton refusal named, counts agreeing with
  the steps, and the port read from disk.
- Receipt: `artifacts/receipts/scout-port-app-probe.json`.

## Why the popit-shell gate matters here

The family rule is that a probe reads the surface, not a print. The shell's own gate is the register
authority, so the application is measured by the same gate the shell ships: `tools/gate.py` counts 21
checks and the launcher import returns `['Scout Port', 'Session archive', 'Reload applications', 'Close
the shell']`.

## Not done, named

- **No Scout skeleton yet.** The port's rig has not been converted to a Deadlock `.vnmskel` + skeleton
  DMX; the forge's Blender path is the tool for it, and the application refuses until it exists.
- **No clip bake onto Scout's own rig.** The bake code that produced 36 frank-bound clips is kept and
  reusable, but its skeleton input has to be Scout's skeleton.
- **No animgraph of the port's own.** `scout_loco.vanmgrph` was authored from the Dota branch template on
  the frank rig; it is superseded with the rest.
- **Not observed in game.** No launch was attempted this pass; the previously installed
  `scout_animgraph_dir.vpk` in `game/citadel/addons/` is still there and still frank-bound, and the
  localization keys added for `hero_scout` are still in place — both are named here so the next pass can
  decide, not discover.
