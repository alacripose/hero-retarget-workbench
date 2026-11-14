# TICKET-0018 — chain to cloth, and the Workbench as its own editor

Status: implemented in 0.7.0
Authority: `logs/authority/2026-11-14-own-editor-type.jsonl`

## Owner request (verbatim)

> we're on 5.4 so we can actually have our own editor types please

> I've updated my build of blender daily see if it changes anything

## What the builds actually do

The installed stock build is **5.4.0 Alpha, daily 2026-11-13**. It refuses both
halves of the recipe:

```
bpy.utils.register_class(<a bpy.types.Space subclass>)
ValueError: register_class(...): expected a subclass of a registerable RNA type
(Space does not support registration)

Panel.bl_space_type enum: EMPTY, VIEW_3D, …, PROPERTIES, … — no 'CUSTOM'
```

Custom space types are **PR 165087**, still a work in progress, with an official
patch build: <https://builder.blender.org/download/patch/PR165087>. That build
(5.4.0 Alpha, 2026-10-21) accepts the registration, and an area switches to it
with:

```python
area.type = "CUSTOM"          # the shared host
area.ui_type = "DMF_ST_workbench"   # which registered space
```

So the addon cannot have its own editor on the stock build, and can on the patch
build. The surface is therefore chosen at registration, in `__init__.py`:

- `ui_space.register()` builds `DMF_ST_workbench`, a header (`DMF_HT_workbench`)
  and the page panels with `bl_space_type='CUSTOM'`; it returns False when the
  build has no custom space support.
- on False, `ui_props.register()` puts the identical page panels in the
  Properties editor (`PROPERTIES`/`scene`), which is what 0.6.x shipped.
- `SURFACE` exposes `"editor"` or `"properties"` so a probe never has to assume
  which happened, and `dmf.open_workbench` switches the current area to whichever
  exists (falling back to Properties with a status line, not a silent no-op).

Both surfaces are built from the same page set: every page panel is a subclass of
the sidebar panel that inherits its `draw` body, so a page cannot differ between
the editors. Dynamically created classes are published in their module
(`ui_props.materialize`) because Blender resolves a registered panel back to its
Python class by module and name; without that, the editor draws structs with no
Python class.

## Chain to cloth

From a discovered chain (`coat_0..coat_3`, `hair_0..hair_3`), **Build cloth on this
chain** (`dmf.build_chain_cloth`, and `dmf.build_all_cloth` for every cloth-named
chain):

1. picks the imported hero mesh that is actually skinned to the chain's bones by
   real weights (for Shiv, `coat` → `shiv_jacket4`, `hair` → `shiv_hair3`);
2. ensures one vertex group per chain bone, keeping the existing skin weights and
   only creating an empty group when one is missing — no invented weights;
3. makes `DMF_pin_<chain>` from the vertices the chain **root** already drives
   (932 for `coat`, 434 for `hair`);
4. builds `DMF <chain> chain`, an armature whose bones are the chain in order,
   parented in sequence, in a `DMF Cloth` collection — connected only where the
   hero's rest positions actually meet, so a gap is not welded shut;
5. adds `DMF Cloth <chain>` to the mesh with `vertex_group_mass` pointing at the
   pin group, armature modifier first and cloth last, so the cloth hangs from the
   posed mesh;
6. records mesh, chain object, pin group and modifier on the chain row, which the
   Cloth page shows as built.

Cloth constraint nodes are still modeldoc data: this builds Blender cloth from the
imported skinning and does not import those nodes.

## Evidence

- `tools/blender_cloth_probe.py` on the real Shiv extraction: **22/22** checks on
  both the PR patch build (`surface: editor`) and the stock daily
  (`surface: properties`). Five hero meshes on one 161-bone rig; `coat` built with
  4 bone groups (932/713/739/1463 weighted vertices), 932 pinned, modifier order
  `ARMATURE, CLOTH`, chain object `DMF coat chain` with `coat_0..coat_3` parented
  in order; `hair` built on `shiv_hair3` with 434 pinned.
- `tools/blender_pages_gui_probe.py`, a real Blender window that switches an area
  to the surface and draws every page:
  - PR patch build: `area.type=CUSTOM`, `area.ui_type=DMF_ST_workbench`,
    **17/17 page draws, 0 exceptions**, screenshot
    `artifacts/receipts/editor-pr.png` shows the editor with the page selector,
    the Cloth page, hero meshes and chains.
  - stock daily: `PROPERTIES` surface, 17/17 page draws, 0 exceptions,
    screenshot `artifacts/receipts/workbench-properties.png`.
- Receipts: `artifacts/receipts/pages-pr.json`, `pages.json`, `cloth-pr.json`.

## Not proven / open

- The own editor exists only on a Blender build with PR 165087. The addon's
  manifest still says `blender: (5, 4, 0)` because it loads and works on the stock
  daily; on that build the page surface is the Properties tab.
- The PR build is experimental: in this profile other extensions
  (`cgmatter_nodes`) throw `SpaceNodeEditor has no attribute draw_handler_add` on
  every depsgraph update, and redraw logs `unable to get Python class for RNA
  struct 'DMF_PT_<sidebar panel>'` for the sidebar panels while the custom space
  is drawn. Both surfaces still render (screenshots), but those two warnings are
  other add-ons' and core/PR noise, not addon failures.
- No cloth simulation was baked on the imported meshes, and no game compile of a
  cloth model was run.
