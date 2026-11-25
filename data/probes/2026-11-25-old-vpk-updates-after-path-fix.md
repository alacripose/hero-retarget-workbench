# 2026-11-25 — the owner's old VPK migrates: the stored value was a model path

**Why 0.22.10 was still blocked.** The resolver added in 0.22.10 handled a *slug* miss, but the value the
Mods page stores in `settings.hero_slug` is a **model path** — `heropick.port_target` says so in its own
docstring: "the picker's rows are every model in the pak, so `hero_slug` is usually a model path". So
`models/heroes_staging/nano/nano_v2/nano.vmdl_c` reached `resolve_hero` as a path, matched no slug,
produced identity tokens for the whole path, matched no family, and fell through to `None` — where
`migrate.update_from_package` refuses with `new-extraction-or-hero-required`. The 0.22.10 zip published,
but the owner's own case was still refused.

**The rungs added in 0.22.11** (`forge.live.resolve_hero`, `_model_key` / `_path_tokens`):

1. exact slug — unchanged;
2. exact model path against the roster, compiled marker and `.vmdl` extension ignored
   (`roster-miss:<value>-><slug>:model-path`);
3. the same hero family, where a path reduces to the identity tokens of its vmdl stem *and* its parent
   folder, minus `models`/`heroes`/`staging`/`wip` (`roster-miss:<value>-><slug>`);
4. the value as a live model path, when the build still ships it (`…:live-model`);
5. the package's own model (`…:package-model`), then `None` (`…:no-model`).

**Measured on the owner's package** — `data/probes/2026-11-25-update-old-vpk-probe.py`, which calls the
same `forge.migrate.update_from_package` the operator calls, with the GUI's own settings
(`Preserve custom only`, keep cloth/physics, copy old materials):

| reading | value |
|---|---|
| roster | 355 heroes in 1.9 s (Source 2 Viewer **CLI**; the GUI builds emit no `heroes.vdata`) |
| selected value | `models/heroes_staging/nano/nano_v2/nano.vmdl_c` |
| resolution | `nano` / `models/heroes_staging/nano/nano_v2/nano.vmdl_c`, note `…->nano:model-path` |
| output vmdl | `artifacts/probes/old-vpk-update/content/citadel_addons/avahead_calico_v3_probe/models/heroes_staging/nano/nano_v2/nano.vmdl` |
| preserved model | yes — 4 old render DMXs kept (`body`, `head1`, `glasses2`, `shadow_form2`) |
| live model files | 9 (`nano_cat_v21`, LOD slots included) |
| materials | 11 copied materials, 11 textures |
| sections | `PhysicsJointList`, `ClothProxyMeshList`, `Softbody` all replaced; 4 cloth chains |
| time | 15.1 s |

Receipt: `artifacts/receipts/update-old-vpk-probe.json`. The probe ran against
`F:\Downloaded Files\avahead_calico_v2\pak04_dir.vpk` (6,669,684 bytes) and
`D:\SteamLibrary\steamapps\common\Deadlock`.

**Not checked.** The GUI click itself — this is the same function the operator calls, not the button — and
the compiled addon in the game. The owner's installed addon is replaced with 0.22.11 so the button carries
this code.
