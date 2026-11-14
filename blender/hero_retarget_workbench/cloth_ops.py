"""Hero mesh parts and cloth chains, on the Blender side.

The extraction gives the hero as several meshes; the workbench imports the body
and, with this module, every other mesh DMX beside it (hair, jacket, glasses, gun)
onto the same armature. The chain rows are read from the imported skeleton rather
than a vmdl: a chain is a numbered run of bones on one side, which is exactly the
set a cloth simulation would be built on.
"""
from __future__ import annotations

from pathlib import Path

import bpy
import traceback
from bpy.types import Operator
from forge import cloth as clothscan
from mathutils import Matrix

from . import core, source2


def hero_folder(settings) -> Path | None:
    if not settings.body_dmx:
        return None
    return Path(bpy.path.abspath(settings.body_dmx)).parent


def hero_parts(settings) -> list:
    return [row.object for row in settings.hero_parts if row.object is not None]


def record_part(settings, obj) -> bool:
    """Add a mesh to the hero-part list once; returns whether it was new."""
    for row in settings.hero_parts:
        if row.object == obj:
            return False
    row = settings.hero_parts.add()
    row.object = obj
    return True


def import_companions(context, settings) -> dict:
    """Import every other mesh DMX in the hero's folder onto the hero armature.

    A file only counts as a part when importing it actually produces a mesh, so a
    clip that shares the hero's prefix is skipped rather than guessed away.
    """
    armature = settings.target_armature
    folder = hero_folder(settings)
    if folder is None or not folder.is_dir():
        raise RuntimeError("cloth-hero-folder-missing: choose the hero body DMX first")
    files = clothscan.mesh_files(folder)
    if not files:
        raise RuntimeError("cloth-hero-parts-missing: no mesh DMX sits beside the body")
    body_stem = Path(bpy.path.abspath(settings.body_dmx)).stem
    imported: list[str] = []
    skipped: list[str] = []
    known = {clothscan.part_name(obj.name) for obj in hero_parts(settings)}
    # A companion DMX can carry an animation.  Its action is not the body's
    # action, but PulseSrcOps also leaves the sampled pose on the bones, which
    # makes Drifter look crouched and rotated after import.  Keep the body's
    # pose and put every bone back after each candidate.
    pose_basis = (
        {bone.name: bone.matrix_basis.copy() for bone in armature.pose.bones}
        if armature is not None
        else {}
    )
    for entry in files:
        if entry.stem == body_stem:
            continue
        if entry.part in known:
            skipped.append(f"{entry.stem} (already imported)")
            continue
        before = {obj.name for obj in context.scene.objects}
        before_actions = {action.name for action in bpy.data.actions}
        scene = context.scene
        data = armature.animation_data if armature is not None else None
        old_action = data.action if data is not None else None
        old_slot = getattr(data, "action_slot", None) if data is not None else None
        old_tracks = {track.name for track in data.nla_tracks} if data is not None else set()
        old_frame = scene.frame_current
        if armature is not None:
            core.select_only(context, [armature])
        try:
            source2.import_dmx(entry.path, append="APPEND")
        except Exception as error:  # one bad file must not lose the rest
            skipped.append(f"{entry.stem} ({error})")
            continue
        finally:
            # ``weapon_stand_idle`` and similar clip names can satisfy the part
            # word test.  Importing one poses the hero even though it produces
            # no mesh; put the body back in its pre-import pose every time.
            if data is not None:
                for track in list(data.nla_tracks):
                    if track.name not in old_tracks:
                        data.nla_tracks.remove(track)
                data.action = old_action
                if old_slot is not None:
                    try:
                        data.action_slot = old_slot
                    except (TypeError, ValueError):
                        pass
            if armature is not None:
                for bone in armature.pose.bones:
                    saved = pose_basis.get(bone.name)
                    bone.matrix_basis = saved.copy() if saved is not None else Matrix.Identity(4)
                bpy.context.view_layer.update()
            try:
                scene.frame_set(old_frame)
            except (TypeError, ValueError):
                pass
        created = [
            obj
            for obj in context.scene.objects
            if obj.name not in before and obj.type == "MESH"
        ]
        if not created:
            for action in [action for action in bpy.data.actions if action.name not in before_actions]:
                bpy.data.actions.remove(action)
            skipped.append(f"{entry.stem} (no mesh in the file)")
            continue
        for obj in created:
            record_part(settings, obj)
        imported.append(entry.stem)
    if armature is not None:
        # Removing a failed candidate's action can make Blender evaluate a stale
        # action slot once more; the last word on the body has to be its bind pose.
        for bone in armature.pose.bones:
            saved = pose_basis.get(bone.name)
            bone.matrix_basis = saved.copy() if saved is not None else Matrix.Identity(4)
        bpy.context.view_layer.update()
    return {"imported": imported, "skipped": skipped, "candidates": [entry.stem for entry in files]}


def _source_armature(settings, source: str):
    if source == "CUSTOM":
        armature = settings.custom_armature
        if armature is None:
            raise RuntimeError(
                "cloth-needs-custom-rig: choose the imported custom model armature first"
            )
        return armature
    armature = settings.target_armature
    if armature is None:
        raise RuntimeError("cloth-needs-hero: import the hero skeleton first")
    return armature


def _world_head(armature, bone) -> object:
    return armature.matrix_world @ bone.head_local


def _nearest_parent(hero, source, root_name: str, chain: set[str]) -> str:
    """A hero bone to hang a copied chain from, by rest position.

    Name identity wins when the custom rig carries the hero's own parent name (a
    pelvis or spine).  Otherwise the closest hero deform bone is the useful
    default; the row still lets the owner replace it before joining.
    """
    source_bone = source.data.bones.get(root_name)
    if source_bone is not None and source_bone.parent is not None:
        parent = source_bone.parent.name
        if hero.data.bones.get(parent) is not None:
            return parent
    if source_bone is None:
        return ""
    point = _world_head(source, source_bone)
    best = None
    best_distance = None
    for bone in hero.data.bones:
        if bone.name in chain or not bone.use_deform:
            continue
        distance = (point - _world_head(hero, bone)).length
        if best_distance is None or distance < best_distance:
            best = bone.name
            best_distance = distance
    return best or ""


def scan_chains(settings) -> int:
    """Group numbered bones from the chosen rig into chains; nothing is edited.

    The source is the hero skeleton by default, or the imported custom model's
    armature when the owner switches the Cloth page to Custom rig.  The custom
    armature is often scaled differently in the viewport; no positions are baked
    here, so the later join can convert every bone through world space.
    """
    source = getattr(settings, "cloth_source", "HERO") or "HERO"
    armature = _source_armature(settings, source)
    hero = settings.target_armature
    if hero is None:
        raise RuntimeError("cloth-needs-hero: import the hero skeleton first")
    names = [bone.name for bone in armature.data.bones]
    groups = clothscan.chains(names)
    old = {
        (row.name, row.source): row
        for row in settings.cloth_chains
        if row.name
    }
    settings.cloth_chains.clear()
    for chain in groups:
        row = settings.cloth_chains.add()
        row.name = chain.name
        row.side = chain.side
        row.count = len(chain.bones)
        row.root = chain.bones[0]
        text = ", ".join(chain.bones)
        row.bones = text if len(text) <= 400 else text[:397] + "..."
        row.source = source
        row.source_armature = armature.name
        previous = old.get((chain.name, source))
        row.parent = (previous.parent if previous and previous.parent else "")
        if not row.parent:
            row.parent = _nearest_parent(hero, armature, chain.bones[0], set(chain.bones))
        row.source_mesh = (previous.source_mesh if previous else None) or (
            settings.custom_mesh if source == "CUSTOM" else None
        )
        row.joined = 0
    settings.cloth_index = 0
    return len(groups)


def cloth_parts(settings) -> list:
    return [obj for obj in hero_parts(settings) if clothscan.is_cloth(obj.name)]


def _weighted_vertices(obj, group) -> list[int]:
    """Vertex indices with a non-zero weight in ``group``."""
    index = group.index
    found = []
    for vertex in obj.data.vertices:
        for element in vertex.groups:
            if element.group == index and element.weight > 0:
                found.append(vertex.index)
                break
    return found


def _chain_for(settings, index: int | None = None, name: str = ""):
    rows = list(settings.cloth_chains)
    if not rows:
        raise RuntimeError("cloth-no-chains: scan the hero chains first")
    if name:
        for row in rows:
            if row.name == name:
                return row
        raise RuntimeError(f"cloth-chain-missing: no chain named {name!r}")
    index = settings.cloth_index if index is None else index
    if not 0 <= index < len(rows):
        raise RuntimeError("cloth-chain-missing: choose a chain row first")
    return rows[index]


def _custom_meshes(settings) -> list:
    from . import parts

    rows = parts.collection_meshes(settings.custom_collection)
    if settings.custom_mesh is not None and settings.custom_mesh not in rows:
        rows.append(settings.custom_mesh)
    return rows


def choose_cloth_mesh(settings, bones: list[str], row=None):
    """The imported hero mesh most skinned to this chain, by real weights.

    A cloth part wins over the body: the body carries a few stray weights for
    collar and sleeve bones, and building a jacket chain on the body would make
    the page read right while the jacket stayed rigid.
    """
    best = (0, None)
    best_cloth = (0, None)
    source = getattr(row, "source", "HERO") if row is not None else "HERO"
    candidates = _custom_meshes(settings) if source == "CUSTOM" else hero_parts(settings)
    if source == "CUSTOM" and row is not None and row.source_mesh is not None:
        candidates = [row.source_mesh] + [obj for obj in candidates if obj != row.source_mesh]
    for obj in candidates:
        score = 0
        for bone in bones:
            group = obj.vertex_groups.get(bone)
            if group is not None:
                score += len(_weighted_vertices(obj, group))
        if score > best[0]:
            best = (score, obj)
        if score > best_cloth[0] and clothscan.is_cloth(obj.name):
            best_cloth = (score, obj)
    chosen = best_cloth[1] or best[1]
    if source == "CUSTOM" and row is not None and row.source_mesh is not None:
        chosen = row.source_mesh
    if chosen is None:
        raise RuntimeError(
            "cloth-no-weights: no mesh in this source carries weights for "
            f"{bones[0]}..{bones[-1]}"
        )
    return chosen


def _is_cloth_mesh(settings, obj) -> bool:
    return obj in hero_parts(settings) or obj in _custom_meshes(settings)


def _ensure_hero_binding(settings, mesh) -> None:
    """A copied chain only moves the mesh it is weighted to on the hero rig."""
    hero = settings.target_armature
    for modifier in [item for item in mesh.modifiers if item.type == "ARMATURE"]:
        if modifier.object is not hero:
            # A custom mesh usually arrives bound to its own rig.  Once the
            # chain has been copied, every weighted group may exist on the hero;
            # switching the modifier then is safe.  If a group would be lost,
            # refuse and name it instead of silently dropping that part.
            missing = sorted(
                group.name
                for group in mesh.vertex_groups
                if hero.data.bones.get(group.name) is None and _weighted_vertices(mesh, group)
            )
            if missing:
                raise RuntimeError(
                    f"cloth-mesh-other-rig: {mesh.name} is bound to "
                    f"{getattr(modifier.object, 'name', 'no armature')}; these weighted groups "
                    f"are not on the hero: {', '.join(missing[:4])}"
                )
            modifier.object = hero
    if not any(item.type == "ARMATURE" and item.object is hero for item in mesh.modifiers):
        modifier = mesh.modifiers.new("DMF Cloth Armature", "ARMATURE")
        modifier.object = hero
        modifier.use_vertex_groups = True
    # The armature has to evaluate before the cloth pins vertices to it.
    first = next((index for index, item in enumerate(mesh.modifiers) if item.type == "ARMATURE"), 0)
    if first > 0:
        core.select_only(bpy.context, [mesh])
        bpy.context.view_layer.objects.active = mesh
        modifier = next(item for item in mesh.modifiers if item.type == "ARMATURE" and item.object is hero)
        bpy.ops.object.modifier_move_to_index(modifier=modifier.name, index=0)


def join_chain(settings, row) -> dict:
    """Copy one custom chain's bones into the hero armature at world scale.

    This is the Blender half of the documented custom-skeleton workflow: the
    custom rig's root may be tiny, huge, parented to nothing or offset in the
    viewport.  Each bone's head and tail are read in world space and converted
    through the hero's inverse matrix, so the joined chain lands exactly where it
    sits in the viewport.  Existing hero bones are never moved or renamed; only
    bones that do not yet exist are created.
    """
    hero = settings.target_armature
    if hero is None:
        raise RuntimeError("cloth-needs-hero: import the hero skeleton first")
    source_name = getattr(row, "source", "HERO") or "HERO"
    if source_name == "HERO":
        missing = [name for name in row.bones.split(",") if name.strip() and hero.data.bones.get(name.strip()) is None]
        if missing:
            raise RuntimeError(f"cloth-chain-bone-missing: {missing[0]} is not on the hero rig")
        row.joined = 0
        return {"copied": 0, "existing": row.count, "parent": row.parent, "armature": hero.name}
    source = _source_armature(settings, source_name)
    if source is hero:
        raise RuntimeError("cloth-source-is-hero: a custom chain must come from the custom rig")
    bones = [name.strip() for name in (row.bones or "").split(",") if name.strip()]
    if not bones:
        raise RuntimeError(f"cloth-chain-empty: {row.name} has no bones")
    chain = set(bones)
    parent = (row.parent or "").strip()
    if parent and hero.data.bones.get(parent) is None:
        raise RuntimeError(f"cloth-parent-missing: {parent} is not a hero bone")
    if not parent:
        parent = _nearest_parent(hero, source, bones[0], chain)
        row.parent = parent

    source_bones = {name: source.data.bones.get(name) for name in bones}
    missing_source = [name for name, bone in source_bones.items() if bone is None]
    if missing_source:
        raise RuntimeError(f"cloth-source-bone-missing: {missing_source[0]} is not on {source.name}")

    created: list[str] = []
    existing: list[str] = []
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    old_mode = hero.mode
    try:
        core.select_only(bpy.context, [hero])
        bpy.context.view_layer.objects.active = hero
        if hero.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = hero.data.edit_bones
        origin = hero.matrix_world.inverted()
        previous = None
        for index, name in enumerate(bones):
            source_bone = source_bones[name]
            edit = edit_bones.get(name)
            if edit is None:
                edit = edit_bones.new(name)
                edit.head = origin @ (source.matrix_world @ source_bone.head_local)
                edit.tail = origin @ (source.matrix_world @ source_bone.tail_local)
                try:
                    # Roll is part of the bone's orientation, not just its
                    # endpoints. Convert the source rest matrix through the same
                    # two world matrices so a rotated or scaled custom armature
                    # keeps its twist axis after the join.
                    rest = origin @ source.matrix_world @ source_bone.matrix_local
                    edit.roll = bpy.types.Bone.AxisRollFromMatrix(rest.to_3x3())[1]
                except (AttributeError, TypeError, ValueError):
                    pass
                edit.use_deform = True
                created.append(name)
            else:
                existing.append(name)
            # Only the first copied bone gets the explicit new parent. The rest
            # follow their own source chain, never an unrelated hero bone.
            if index == 0 and name in created and parent:
                edit.parent = edit_bones.get(parent)
                edit.use_connect = False
            elif index > 0 and name in created and previous is not None:
                edit.parent = edit_bones.get(previous)
                edit.use_connect = (edit.parent is not None and (edit.parent.tail - edit.head).length < 1e-4)
            previous = name
    finally:
        current = bpy.data.objects.get(hero.name) or hero
        if current.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        core.select_only(bpy.context, selected)
        if active is not None:
            bpy.context.view_layer.objects.active = active
        elif old_mode == "OBJECT":
            bpy.context.view_layer.objects.active = None
    row.joined = len(created)
    settings.cloth_build_skipped = ""
    return {
        "copied": len(created),
        "existing": len(existing),
        "parent": parent,
        "armature": hero.name,
        "bones": created,
    }


def _cloth_collection():
    collection = bpy.data.collections.get("DMF Cloth")
    if collection is None:
        collection = bpy.data.collections.new("DMF Cloth")
        bpy.context.scene.collection.children.link(collection)
    return collection


def build_chain_object(settings, chain_name: str, bones: list[str]):
    """The chain as real hero-rig data, not a second armature.

    ModelDoc's Skeleton node reads the exported hero armature.  A separate
    ``DMF <chain> chain`` object is invisible to that node, so a custom chain that
    only existed there would disappear on compile.  The chain therefore lives on
    the hero armature; this helper verifies it after :func:`join_chain`.
    """
    armature = settings.target_armature
    if armature is None:
        raise RuntimeError("cloth-needs-hero: import the hero skeleton first")
    missing = [name for name in bones if armature.data.bones.get(name) is None]
    if missing:
        raise RuntimeError(f"cloth-chain-bone-missing: {missing[0]} is not on the hero rig")
    armature["dmf_cloth_chain"] = chain_name
    armature["dmf_cloth_chain_bones"] = ",".join(bones)
    return armature


def _cloth_modifier(obj):
    """The mesh's cloth simulation, if it already has one."""
    for modifier in obj.modifiers:
        if modifier.type == "CLOTH" and modifier.name.startswith("DMF Cloth "):
            return modifier
    return None


def build_chain_cloth(
    settings, index: int | None = None, name: str = "", mesh=None
) -> dict:
    """Turn one discovered chain into vertex groups, a chain and a cloth modifier.

    Everything comes from the imported data: the mesh is the hero part that is
    actually skinned to the chain's bones, the vertex groups are those bones (a
    missing one is created empty, never filled with invented weights), the pin
    group is the vertices the first bone already drives, and the cloth modifier
    keeps the pin group at those vertices. The mesh keeps its armature modifier
    first, so the cloth hangs from the posed mesh.
    """
    row = _chain_for(settings, index, name)
    bones = [bone.strip() for bone in (row.bones or "").split(",") if bone.strip()]
    if len(bones) < 2:
        raise RuntimeError(f"cloth-chain-short: {row.name} has no segments")
    joined = join_chain(settings, row)
    target = mesh if mesh is not None else choose_cloth_mesh(settings, bones, row)
    if target is None:
        raise RuntimeError("cloth-mesh-missing: choose a cloth mesh for this chain")
    if not _is_cloth_mesh(settings, target):
        raise RuntimeError(
            f"cloth-mesh-not-source: {target.name} is neither a hero part nor in the custom model collection"
        )
    _ensure_hero_binding(settings, target)
    created: list[str] = []
    assigned: dict[str, int] = {}
    for bone in bones:
        group = target.vertex_groups.get(bone)
        if group is None:
            group = target.vertex_groups.new(name=bone)
            created.append(bone)
        assigned[bone] = len(_weighted_vertices(target, group))

    pin_name = f"DMF_pin_{row.name}"
    pin = target.vertex_groups.get(pin_name)
    if pin is None:
        pin = target.vertex_groups.new(name=pin_name)
    # Pin from the first segment that actually has vertices: a chain whose root
    # bone is a helper with no weights still hangs from the mesh.
    pin_bone = ""
    pinned: list[int] = []
    for bone in bones:
        group = target.vertex_groups.get(bone)
        pinned = _weighted_vertices(target, group) if group is not None else []
        if pinned:
            pin_bone = bone
            break
    if pinned:
        pin.add(pinned, 1.0, "REPLACE")

    # Blender runs one cloth simulation per object: a second Cloth modifier is
    # refused outright (modifiers.new returns None). So a mesh keeps one cloth
    # and every chain on it pins through that same simulation, while each chain
    # still owns its pin group and its own DMF <chain> bone chain.
    modifier = _cloth_modifier(target)
    modifier_name = f"DMF Cloth {row.name}"
    if modifier is None:
        modifier = target.modifiers.new(modifier_name, "CLOTH")
    if modifier is None:
        raise RuntimeError(
            f"cloth-modifier-failed: {modifier_name} on {target.name} "
            f"(mode={target.mode}, existing={[m.name for m in target.modifiers]})"
        )
    cloth = modifier.settings
    if not cloth.vertex_group_mass or cloth.vertex_group_mass not in target.vertex_groups:
        cloth.vertex_group_mass = pin.name
    elif cloth.vertex_group_mass != pin.name and pinned:
        shared = target.vertex_groups.get(cloth.vertex_group_mass)
        if shared is not None:
            shared.add(pinned, 1.0, "REPLACE")
    cloth.pin_stiffness = 1.0
    cloth.quality = 5
    cloth.use_pressure = False
    if target.modifiers and target.modifiers[-1] != modifier:
        core.select_only(bpy.context, [target])
        bpy.context.view_layer.objects.active = target
        bpy.ops.object.modifier_move_to_index(
            modifier=modifier.name, index=len(target.modifiers) - 1
        )

    chain = build_chain_object(settings, row.name, bones)
    target["dmf_cloth_chain"] = row.name
    target["dmf_cloth_chain_bones"] = ",".join(bones)
    target["dmf_cloth_pin_group"] = pin.name
    row.target_mesh = target
    row.chain_object = chain
    row.pin_group = pin.name
    row.pin_bone = pin_bone
    row.pin_count = len(pinned)
    row.cloth_modifier = modifier.name
    target["dmf_cloth_parent"] = joined.get("parent", "")
    return {
        "chain": row.name,
        "mesh": target.name,
        "bones": bones,
        "groups_created": created,
        "assigned": assigned,
        "pinned": len(pinned),
        "pin_bone": pin_bone,
        "pin_group": pin.name,
        "chain_object": chain.name,
        "cloth_modifier": modifier.name,
        "modifier_order": [mod.type for mod in target.modifiers],
        "joined": joined,
    }


def _primary_entry(mesh_name: str, entries: list[dict]) -> dict:
    """The chain a mesh's single cloth simulation should be named for."""
    lowered = mesh_name.lower()
    for entry in entries:
        if entry["chain"].lower() in lowered:
            return entry
    if "jacket" in lowered:
        for entry in entries:
            if entry["chain"] == "coat":
                return entry
    return max(entries, key=lambda entry: entry["pinned"])


def name_mesh_cloth(settings, built: list[dict]) -> None:
    """Name each mesh's one cloth simulation after its main chain.

    The modifier is created by whichever chain is built first, which is
    alphabetical and would leave the jacket's cloth called after a sleeve. The
    rows then point at the renamed modifier so the page reports the truth.
    """
    by_mesh: dict[str, list[dict]] = {}
    for entry in built:
        by_mesh.setdefault(entry["mesh"], []).append(entry)
    for mesh_name, entries in by_mesh.items():
        obj = bpy.data.objects.get(mesh_name)
        modifier = _cloth_modifier(obj) if obj is not None else None
        if modifier is None:
            continue
        primary = _primary_entry(mesh_name, entries)
        wanted = f"DMF Cloth {primary['chain']}"
        if modifier.name != wanted:
            modifier.name = wanted
        for entry in entries:
            entry["cloth_modifier"] = modifier.name
        for row in settings.cloth_chains:
            if row.target_mesh is not None and row.target_mesh.name == mesh_name:
                row.cloth_modifier = modifier.name


def mark_source2_proxy(settings, row) -> dict:
    """Make a mesh a PulseSrcOps cloth proxy instead of a Blender-only cloth.

    A Blender Cloth modifier is a viewport preview; the DMX exporter only writes
    Source 2 cloth vertex maps for a mesh whose PulseSrcOps mesh type is
    ``CLOTHPROXY``.  This writes the one map the proxy needs to enable simulation
    (``cloth_enable``) and leaves every tuning map to PulseSrcOps' own Cloth Proxy
    section in the N panel.
    """
    target = row.target_mesh or row.source_mesh or settings.custom_mesh
    if target is None:
        raise RuntimeError("cloth-proxy-mesh-missing: choose the cloth mesh first")
    if not hasattr(target, "vs") or not hasattr(target.vs, "mesh_type"):
        raise RuntimeError("cloth-proxy-needs-pulsesrcops: enable the PulseSrcOps extension")
    target.vs.mesh_type = "CLOTHPROXY"
    group = target.vertex_groups.get("cloth_enable")
    if group is None:
        group = target.vertex_groups.new(name="cloth_enable")
    group.add([vertex.index for vertex in target.data.vertices], 1.0, "REPLACE")
    remaps = getattr(target.vs, "vertex_map_remaps", None)
    if remaps is not None and not any(item.group == "cloth_enable" for item in remaps):
        item = remaps.add()
        item.group = "cloth_enable"
        item.min = 0.0
        item.max = 1.0
    row.proxy = True
    target["dmf_cloth_chain"] = row.name
    target["dmf_cloth_proxy"] = True
    return {"mesh": target.name, "group": group.name, "mesh_type": target.vs.mesh_type}


def build_import_cloth(settings) -> dict:
    """Build every cloth-named chain on the cloth part it is skinned to.

    This is the step that makes a fresh hero import cloth-capable instead of just
    complete: each chain gets its groups, pin group, bone chain and a cloth
    simulation before the import operator reports back. Chains that belong to the
    body rather than to a cloth part are reported, not built: simulating a whole
    hero body is not what a jacket chain means.
    """
    built: list[dict] = []
    skipped: list[str] = []
    for row in list(settings.cloth_chains):
        if getattr(row, "source", "HERO") != "HERO":
            continue
        if not clothscan.is_cloth(row.name):
            continue
        bones = [bone.strip() for bone in (row.bones or "").split(",") if bone.strip()]
        try:
            target = choose_cloth_mesh(settings, bones)
            if not clothscan.is_cloth(target.name):
                skipped.append(
                    f"{row.name} (weights are on {target.name}, which is not a cloth part)"
                )
                continue
            result = build_chain_cloth(settings, name=row.name, mesh=target)
        except Exception as error:
            frame = traceback.extract_tb(error.__traceback__)[-1]
            skipped.append(
                f"{row.name} ({type(error).__name__}: {error} at "
                f"{frame.name}:{frame.lineno})"
            )
            continue
        if result["pinned"]:
            built.append(result)
        else:
            skipped.append(f"{row.name} (no segment has vertices to pin)")
    name_mesh_cloth(settings, built)
    return {"built": built, "skipped": skipped}


class DMF_OT_import_hero_parts(Operator):
    bl_idname = "dmf.import_hero_parts"
    bl_label = "Import Hero Parts"
    bl_description = (
        "Import every other mesh DMX beside the hero body (hair, jacket, glasses, gun) "
        "onto the hero armature"
    )

    def execute(self, context):
        settings = context.scene.dmf
        if settings.target_armature is None:
            self.report({"ERROR"}, "Import the hero skeleton first")
            return {"CANCELLED"}
        try:
            result = import_companions(context, settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        imported = result["imported"]
        skipped = result["skipped"]
        if imported:
            core.set_status(
                settings,
                f"Imported {len(imported)} hero parts: {', '.join(imported)}"
                + (f"; skipped {len(skipped)}" if skipped else ""),
                "OK" if not skipped else "WARN",
            )
        else:
            core.set_status(
                settings,
                f"No new hero part to import; {len(skipped)} skipped: {', '.join(skipped[:3])}",
                "WARN",
            )
        return {"FINISHED"}


class DMF_OT_scan_cloth(Operator):
    bl_idname = "dmf.scan_cloth"
    bl_label = "Scan Cloth Chains"
    bl_description = "Group the hero skeleton's numbered bones into the chains a cloth simulation hangs from"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = scan_chains(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        cloth_like = sum(1 for row in settings.cloth_chains if clothscan.is_cloth(row.name))
        source = "custom rig" if getattr(settings, "cloth_source", "HERO") == "CUSTOM" else "hero skeleton"
        core.set_status(
            settings,
            f"{count} bone chains from the {source}; {cloth_like} read like cloth"
            if count
            else f"No numbered bone chain on the {source}",
            "OK" if count else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_join_cloth_chain(Operator):
    bl_idname = "dmf.join_cloth_chain"
    bl_label = "Join Chain to Hero"
    bl_description = (
        "Copy the selected custom chain's bones into the hero armature in world space "
        "and hang the first bone from the chosen parent; existing hero bones are never moved"
    )

    def execute(self, context):
        settings = context.scene.dmf
        try:
            row = _chain_for(settings)
            result = join_chain(settings, row)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(
            settings,
            f"Joined {result['copied']} new bones for {row.name} to {result['armature']}"
            + (f", parent {result['parent']}" if result["parent"] else "")
            + (f"; {result['existing']} already existed" if result["existing"] else ""),
            "OK" if result["copied"] or result["existing"] else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_build_chain_cloth(Operator):
    bl_idname = "dmf.build_chain_cloth"
    bl_label = "Build Cloth on This Chain"
    bl_description = (
        "Build the selected chain into Blender data: one vertex group per chain bone on the "
        "hero mesh that is skinned to it, a pin group from the chain root, an ordered bone "
        "chain, and a cloth modifier driven by that pin group"
    )

    def execute(self, context):
        settings = context.scene.dmf
        try:
            result = build_chain_cloth(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(
            settings,
            f"Cloth on {result['mesh']}: {len(result['bones'])} bone groups, "
            f"{result['pinned']} pinned vertices, {result['cloth_modifier']}",
            "OK" if result["pinned"] else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_mark_cloth_proxy(Operator):
    bl_idname = "dmf.mark_cloth_proxy"
    bl_label = "Mark Source 2 Cloth"
    bl_description = (
        "Set this mesh to PulseSrcOps CLOTHPROXY and give it a cloth_enable map so the "
        "DMX carries Source 2 cloth data instead of only a Blender preview modifier"
    )

    def execute(self, context):
        settings = context.scene.dmf
        try:
            row = _chain_for(settings)
            result = mark_source2_proxy(settings, row)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(
            settings,
            f"{result['mesh']} is a Source 2 {result['mesh_type']} with {result['group']}",
            "OK",
        )
        return {"FINISHED"}


class DMF_OT_build_all_cloth(Operator):
    bl_idname = "dmf.build_all_cloth"
    bl_label = "Build Every Cloth Chain"
    bl_description = "Build every chain whose name reads like cloth (coat, hair, sleeve, jacket) on its mesh"

    def execute(self, context):
        settings = context.scene.dmf
        result = build_import_cloth(settings)
        built = [entry["chain"] for entry in result["built"]]
        skipped = result["skipped"]
        if built:
            core.set_status(
                settings,
                f"Built cloth for {', '.join(built)}"
                + (f"; skipped {', '.join(skipped)}" if skipped else ""),
                "OK" if not skipped else "WARN",
            )
        else:
            core.set_status(
                settings,
                "No cloth chain could be built" + (f": {', '.join(skipped)}" if skipped else ""),
                "WARN",
            )
        return {"FINISHED"}


CLASSES = (
    DMF_OT_import_hero_parts,
    DMF_OT_scan_cloth,
    DMF_OT_join_cloth_chain,
    DMF_OT_build_chain_cloth,
    DMF_OT_mark_cloth_proxy,
    DMF_OT_build_all_cloth,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
