# Decisions

Append-only. Each decision names its owner/source and its consequence. Do not
replace an older decision; add a superseding entry.

## D-01 — The hero always comes from the live game through S2V

**Status:** accepted, owner correction.

The hero body, skeleton, attachments, camera data, and source vmdl come from the
current live Deadlock install. The project calls S2V with `pak01_dir.vpk` and the
live `game/citadel/gameinfo.gi`.

**Consequence:** CSDK13 is never a hero source. Its `doorman.vmdl` and other
hero files are not imported, copied, or merged into this pipeline.

## D-02 — The extracted vmdl is opaque and copied byte-for-byte

**Status:** accepted, owner correction.

S2V's vmdl already carries what the hero needs. The forge never reconstructs a
hero vmdl and never parses its metadata. The compiler receives the same bytes
that came out of S2V.

**Consequence:** `stage` hashes the input and output vmdl and refuses to proceed
if they differ. There is no vmdl writer, no KV3 parser, and no metadata fallback.
S2V's `-d` extraction does emit the source vmdl on the observed build; if a
particular extraction does not, the user selects the vmdl from their S2V
extraction and the addon does not invent one.

## D-03 — Addon scope is custom model, fit/retarget, materials, handoff

**Status:** accepted, owner correction.

The Blender addon chooses a live hero and a custom model. It imports the hero
body, fits the custom mesh, maps or transfers weights, puts the hero materials
on the custom mesh, exports the replacement DMX, and stages the unchanged vmdl
plus copied materials for CSDK13.

**Consequence:** No web application, no custom interchange format, no synthetic
model standard, and no hero reconstruction are part of the deliverable.

## D-04 — CSDK13 is the compiler, invoked directly

**Status:** accepted.

`resourcecompiler.exe` is called with `-nop4 -f -game <csdk/game/citadel>
-i <staged vmdl>`. Its return code and log are recorded. The compiler resolves
content from the SDK's `content` root, so a stage is mirrored into
`content/citadel_addons/<addon>` for the build, and the resulting `.vmdl_c` is
saved back under the stage's `compiled/` folder.

**Consequence:** A stage is not a compile. `STATUS.md` reports the last observed
compile row; the 2026-11-12 probe compiled the staged live Haze vmdl with 1
compiled, 0 failed, and 3 missing-material warnings.

**2026-11-12 — superseded in part (owner correction).** The persistent mirror
was rejected as flooding CSDK with uncompiled sources. `compile_stage` now uses
a unique temporary `content/citadel_addons/dmf_build_<addon>_<random>` folder,
removes both that folder and its `game` counterpart in `finally`, and copies
only compiled `_c` files back under `<stage>/compiled/<addon>/`. The source
vmdl still remains byte-identical, and a failed compile preserves the prior
compiled output rather than replacing it with a partial tree.

## D-05 — Materials are copied, not interpreted

**Status:** accepted.

Live `.vmat` files are copied verbatim into the handoff, preserving layers,
options, textures, and paths. The addon assigns the imported hero material slots
to the custom mesh instead of rebuilding materials from a parsed schema.

**Consequence:** No material parser and no vmat rewrite.

## D-06 — Axis fitting never touches weights

**Status:** implementation decision, 2026-11-12.

Axis conversion is a permutation matrix plus a positive scale. It transforms
positions and normals. Vertex-group weights and joint indices are left intact.

**Consequence:** The `fit` command is reversible and reports its determinant;
mirrors are explicit and named. Imported custom models default to identity.

## D-07 — The family loop is ticket → ledger → gate → generated status

**Status:** accepted, project convention.

Work starts with a ticket and authority. Commands append evidence to the ledger.
`gate` runs tests and structural checks and regenerates `STATUS.md`. A previous
pass becoming a fail is a ratchet regression and exits non-zero.

**Consequence:** `STATUS.md` is not edited by hand; `ledger/ledger.jsonl` and the
authority log are append-only.

## D-08 — The live hero table defines the roster

**Status:** accepted, owner correction, 2026-11-12.

The owner required every hero, not a curated list and not the staging-only folder
scan. Hero identity, display name and model path come from every top-level
`hero_*` entry in the live `scripts/heroes.vdata` that Source 2 Viewer emits for
the current build. Model paths under `heroes_wip`, versioned folders and nested
folders are valid.

**Consequence:** There is no allow-list of heroes and no active-only filter.
On build 6861 the table has 67 entries; 63 have body models. The four entries
without a body model are listed and extraction fails with the declared missing
path rather than silently substituting a body. Only the roster's hero/model
fields are read; the vmdl stays opaque and is copied byte-for-byte.

## D-09 — The addon is a manual workbench, not a one-click pipeline

**Status:** accepted, owner correction, 2026-11-12.

The owner rejected a button queue that hides the work. The addon exposes the
bone map, rename, rest/pose alignment, split comparison, extra-bone policy,
weight-paint tools and proof checks. The user decides an unmatched group; the
addon does not guess a nearest bone or report it as a completed bind.

**Consequence:** `dmf.retarget` starts a chunked solver only after the map is
resolvable. It does not use Blender's `DATA_TRANSFER` modifier. Long S2V and
CSDK13 calls run in a background thread; the weight solve runs in timer chunks.

## D-10 — Retarget identity is BLAKE3 with an Axis proof gate

**Status:** accepted, owner correction, 2026-11-12.

**Owner correction, verbatim:** *"do not fucking regress the project because you
don't want to install a modern package dependency why the fuck would I want to
use legacy"*.

A retarget proof carries the Axis fields: artifact bytes and digest, claim,
origin, evidence, tick span, world digest, presenter, ticket and named checks. A
proof is not a pass; every check must return `pass`, the artifact bytes must
match, and the tick must be current. Export refuses a stale, refused, unchecked
or missing proof.

**Consequence:** `forge/proof.py` uses BLAKE3, `requirements.txt` declares
`blake3==1.0.11`, and `blender/hero_retarget_workbench/_vendor/blake3` carries the
Windows extension into the installable zip. SHA-256 remains only as named legacy
stage evidence; new proof identity never falls back to it. The schema ids are
hash-pinned, not numeric `/1` ids.
