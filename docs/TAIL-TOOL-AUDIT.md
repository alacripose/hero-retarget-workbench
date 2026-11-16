# Tail tool audit — which `tools/` files re-do what the addon ships

**Owner request, verbatim:** *"you need to fucking do an audit to see how many of these tools are
worse versions of things the blender addon already shipped"*, and *"the blender addon is the target
surface not probes for specific heroes and tails which is why the shiv build got stuck"*.

This is that audit, measured on the tree at `fc15e0f`+`c430585`, not on memory. It answers one
question: **which tools produce a shipped artifact through a path the addon already owns?**

## Method, and what it deliberately does not count

Counted mechanically with `rg` over `tools/*.py`:

| Measure | Command | Count |
|---|---|---|
| tool files | `ls tools/*.py` | **93** |
| files that pack a VPK | `rg -l vpk_create tools/*.py` | **2** — `shiv_release_build.py`, `tail_release_pack.py` |
| files that run `resourcecompiler` | `rg -l resourcecompiler tools/*.py` | **6** — but 2 are `project.py` (gate) and `blender_zip_probe.py` (install probe) |
| files that export DMX through PulseSrcOps | `rg -l export_scene\.smd tools/*.py` | **2** — `blender_build_tail_component.py`, `blender_clip_export_probe.py` |
| files named after one hero | `rg -l '(shiv\|werewolf\|haze)' tools/*.py` | **48** |
| files that resolve a hero from the extraction instead | `rg -l port_target tools/*.py` | **3** — `blender_build_tail_component.py`, `blender_tail_auto_probe.py`, `blender_tail_motion_probe.py` |

Not counted as duplication: the ~37 `*_probe.py` files. A probe measures one property and produces a
receipt; it is not a product path, and folding probes into the addon would be the opposite error to
this one. The audit is about **artifact producers**.

## The addon's shipped path, as of the accepted state

Not 0.13.1/0.13.2. AGENTS.md records the owner's correction twice — *"13.2 and 13.1 are not the
fucking good versions"* and *"the 13.1 / 13.2 root_motion entries are not the accepted Shiv work"* —
so the reference for this table is the accepted 06:47 path:

- `tailops._bake_body_action` — reproduce a stock clip's solved pose on the hero rig, root divided out
  of FK bones and **kept** on solver inputs (`forge/solver.py` is that rule). Accepted in game.
- `tailops._copy_tail_bones` / `attach_tail` — append a source tail's rest chain to any hero.
- `tailops._write_tail_action` — key the source tail motion into an action, clearing only tail curves.
- `forge/animgraph.py` — find each clip's real source DMX from `m_sourceFilename`, widen the
  `vnmskel` mask/high-LOD sets, compile the documents with CSDK13.
- `forge/port_target.py` — resolve hero root, body DMX, game skeleton and clips from the extraction,
  so a port is not a pair of hard-coded hero names.
- `clipops.write_action(..., target=)` — write over the exact DMX a document names.

## The table

Verdicts: **duplicate** — same job, tool-side, and one of the two must stop; **weaker** — same job with
less standing between a bad input and a shipped file; **keep** — no addon equivalent, or evidence only.

| tool | what it produces | addon equivalent | verdict |
|---|---|---|---|
| `shiv_release_build.py` | compiled clips **and** a packed VPK | `animgraph.compile_documents` + stage/pack | duplicate, hero-locked |
| `shiv_perclip_build.py` | compiles each clip document | `animgraph.compile_documents` | duplicate; loses `prepare_skeleton`'s mask widening |
| `shiv_merge_compile.py` | compiles merged clips | `animgraph.compile_documents` | duplicate, `HERO = Path("models/heroes_staging/shiv")` |
| `shiv_bulk_merge.py` | imports + re-keys every clip in bulk | `start_auto` + `_auto_tick` (one clip per tick) | duplicate; the bulk pass is what wrote the horizontal builds |
| `shiv_stock_tail_merge.py` | merges stock clips onto the rig | `_bake_body_action` | duplicate of the **accepted** path |
| `shiv_bodies.py` | stages one body per clip | `_hero_roots` + `animgraph.documents` | duplicate |
| `dmx_tail_append.py` | appends tail joints/channels to a clip DMX | `_write_tail_action` + `_copy_tail_bones` | duplicate; never imports a clip, which is its one real property |
| `clip_rebase_to_skeleton.py` | rebases a clip onto the skeleton time base | `_write_tail_action` resampling | duplicate |
| `clip_retarget_frames.py` | frame remap across rigs | `_source_frame` | duplicate |
| `clip_joint_align.py` | joint alignment | `_bake_body_action` root handling | duplicate |
| `skeleton_with_tail.py`, `append_tail_to_vnmskel.py`, `skeleton_append_tail.py` | build a skeleton/vnmskel with the tail | `_copy_tail_bones` + `animgraph.prepare_skeleton` | duplicate |
| `skeleton_fix_parents.py`, `skeleton_union.py`, `dmx_dedupe_joints.py` | repair joint trees | `_copy_tail_bones` parenting | duplicate |
| `tail_port_build.py`, `tail_motion_apply.py` | per-hero tail build | `attach_tail` + `_write_tail_action` | duplicate |
| `tail_release_pack.py` | the VPK, with named refusals | none in the addon | **keep** — but see the contradiction below |
| `tail_release_gate.py` | refusals over model/skeleton/clips | none in the addon | **keep** |
| `vpk_parity.py` | parity against a reference pak | none | **keep** |
| `project.py`, `port_gate.py`, `agents_audit.py` | gate and audit | none | **keep** |
| 37 `*_probe.py` | measurements and receipts | none | **keep** |

**Count: 18 artifact-producing tools duplicate an addon path; 3 of them compile or pack.** Of the 48
files that name a hero, only 3 resolve one from the extraction. Every row was confirmed against the
file's own docstring, not inferred from its name.

## Why the Shiv build got stuck

The shipped work ran through the tool column of that table, not the addon's. The tool column is
hero-locked (`HERO = Path("models/heroes_staging/shiv")` in `shiv_merge_compile.py`,
`SOURCE = "models/heroes_staging/shiv/dmx/animation"` in `clip_compile_ab.py`), so each new hero
started as a new script instead of a parameter, and each script re-decided a question the addon had
already answered — which skeleton, which track set, whose `root_motion`. That is why the same
questions were re-litigated across Haze, Shiv and Werewolf entries and why the accepted 06:47 recipe
had to be rediscovered twice.

## The divergence this audit found, and its resolution

`tools/tail_release_pack.py` refuses `skeleton-not-shipped`, and `tools/vpk_parity.py` scores
`skeleton-not-shipped` as a parity dimension. `tailops.publish_tail_anims` (0.13.1/0.13.2) instead
appends the tail bones to **the model's own skeleton** and deliberately ships no `vnmskel_c`.

**The rule is the first one.** Owner correction, verbatim: *"We ship the nmskeleton for the
animations"*. The compiled `vnmskel_c` carries the tail chain the clips are authored against, the
pinned Shiv pak ships exactly that, and the pak exists — so this is not an open question to be
arbitrated by a flag. A first attempt to settle it with `--skeleton-convention in-model` was wrong
for the reason above: a flag that can express the unshipped convention is a way to ship it. The
option was removed, not defaulted; the packer refuses a pak with no compiled `vnmskel_c` and the
addon's in-model branch is the branch recorded as not accepted.

**Also recorded:** the 0.13.1/0.13.2 tailops work is uncommitted in the working tree and is **not**
the accepted state. It must not be published as the target surface on the strength of its tests
(279 pass) or its version number.

## What to do with this, in order

1. A tool in the **duplicate** column that produced an installed pak is demoted to a record: it keeps
   its receipt and stops being a publish path. `rigspace.py` already shows the shape — the module
   stays as the record of a measured dead end, and nothing calls it.
2. `forge/port_target.py` becomes the only way a tool names a hero. A new hero is then a parameter,
   which is the property the addon already had.
3. `tail_release_pack.py` keeps one skeleton rule with no alternative: a pak ships its compiled
   `.vnmskel_c` (`skeleton-not-shipped` otherwise), and it refuses a hand-picked clip subset
   (`clip-inventory-partial`, `clip-inventory-missing`). Verified on the hand-built trees: every one
   refuses and no pak is written.
