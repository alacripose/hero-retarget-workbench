# 2026-11-25 — the roster is a picker, not an allowlist

**What the owner hit.** Updating an old package (`avahead_calico_v2`) on Live 6868 / CSDK 6836, the
Mods page reported:

```
Updating old addon        failed
failed: Live hero models/heroes_staging/nano/nano_v2/nano.vmdl_c is no longer in the roster
```

**Why it was wrong.** Three call sites looked the selected slug up in the live roster and raised when
the entry was absent:

| file | line (before) | message |
|---|---|---|
| `blender/hero_retarget_workbench/operators.py` | 1651 | `Live hero {slug} is no longer in the roster` |
| `blender/hero_retarget_workbench/pipeline_ops.py` | 607 | `Hero {slug} is not in the live roster` |
| `blender/hero_retarget_workbench/pipeline_ops.py` | 711 | `Hero {slug} is not in the live roster` |

The roster is `forge.live.list_heroes`, read from the installed build's `scripts/heroes.vdata`. It is
the **picker's** list. It is not a declaration of what the workbench may work on, and
`forge.migrate.update_from_package` already accepts `hero=None` (it keeps the package's own body). So
the lookup was gating work on a hand-maintained reading of one build, and an old mod that named a
re-versioned model (Nano's table moved from `nano_v2` to another entry) could not be updated at all.

**The fix.** `forge.live.resolve_hero(heroes, slug, model_hint=...)` returns `(Hero | None, note)` and
never raises. The rungs are:

1. an exact slug match → `note = ""`;
2. the same hero family, compared on *identity tokens with version suffixes removed* (`nano_v2` and
   `nano_v3` both reduce to `{"nano"}`; `nano` never matches `nanobot`) → `roster-miss:<slug>-><slug>`;
3. the model the package itself names (`model_hint`) → `roster-miss:<slug>:package-model`;
4. nothing usable → `None` and `roster-miss:<slug>:no-model`, which `migrate` already handles.

Each call site now passes the resolved hero (possibly `None`) to `update_from_package` and shows the
note in the job progress. No refusal remains on that path; `grep -rn "not in the live roster"` over
`forge/`, `tools/` and `blender/` finds only stale `__pycache__` entries.

**Measured.**

- `python -m pytest -q tests/test_live.py` → **12 passed**, including
  `test_a_roster_miss_is_a_note_not_a_refusal`, which asserts all four rungs and the exact failure text
  this probe records.
- `python -m pytest -q tests` → 414 passed, 1 failed: `tests/test_scout_port_app.py::
  test_live_mesh_step_is_converted_and_downstream_stays_refused`, which fails on
  `hero entry hero_scout names 2 model and 6 image paths, 1 absent` — a live-build file check in the
  Scout app, not a roster lookup. It is recorded here rather than repaired, because it is a different
  unit and its assertion depends on the installed game.

**What is not claimed.** The owner's own GUI click through `Import & update old addon` was not
re-run in Blender by this pass; the resolver, the three call sites and the migration's `hero=None`
contract are what was measured.
