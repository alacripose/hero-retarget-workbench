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

from . import core


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
    for entry in files:
        if entry.stem == body_stem:
            continue
        if entry.part in known:
            skipped.append(f"{entry.stem} (already imported)")
            continue
        before = {obj.name for obj in context.scene.objects}
        if armature is not None:
            core.select_only(context, [armature])
        try:
            bpy.ops.import_scene.kst_dmx(filepath=str(entry.path), append="APPEND")
        except Exception as error:  # one bad file must not lose the rest
            skipped.append(f"{entry.stem} ({error})")
            continue
        created = [
            obj
            for obj in context.scene.objects
            if obj.name not in before and obj.type == "MESH"
        ]
        if not created:
            skipped.append(f"{entry.stem} (no mesh in the file)")
            continue
        for obj in created:
            record_part(settings, obj)
        imported.append(entry.stem)
    return {"imported": imported, "skipped": skipped, "candidates": [entry.stem for entry in files]}


def scan_chains(settings) -> int:
    """Group the hero skeleton's numbered bones into chains; nothing is edited."""
    armature = settings.target_armature
    if armature is None:
        raise RuntimeError("cloth-needs-hero: import the hero skeleton first")
    names = [bone.name for bone in armature.data.bones]
    groups = clothscan.chains(names)
    settings.cloth_chains.clear()
    for chain in groups:
        row = settings.cloth_chains.add()
        row.name = chain.name
        row.side = chain.side
        row.count = len(chain.bones)
        row.root = chain.bones[0]
        text = ", ".join(chain.bones)
        row.bones = text if len(text) <= 400 else text[:397] + "..."
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


def choose_cloth_mesh(settings, bones: list[str]):
    """The imported hero mesh most skinned to this chain, by real weights.

    A cloth part wins over the body: the body carries a few stray weights for
    collar and sleeve bones, and building a jacket chain on the body would make
    the page read right while the jacket stayed rigid.
    """
    best = (0, None)
    best_cloth = (0, None)
    for obj in hero_parts(settings):
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
    if chosen is None:
        raise RuntimeError(
            "cloth-no-weights: no imported hero mesh carries weights for "
            f"{bones[0]}..{bones[-1]}"
        )
    return chosen


def _cloth_collection():
    collection = bpy.data.collections.get("DMF Cloth")
    if collection is None:
        collection = bpy.data.collections.new("DMF Cloth")
        bpy.context.scene.collection.children.link(collection)
    return collection


def build_chain_object(settings, chain_name: str, bones: list[str]):
    """The chain as real rig data: one connected bone per segment, in order."""
    object_name = f"DMF {chain_name} chain"
    existing = bpy.data.objects.get(object_name)
    if existing is not None and existing.type == "ARMATURE":
        return existing
    armature = settings.target_armature
    if armature is None:
        raise RuntimeError("cloth-needs-hero: import the hero skeleton first")
    data = bpy.data.armatures.new(object_name)
    obj = bpy.data.objects.new(object_name, data)
    _cloth_collection().objects.link(obj)
    obj.matrix_world = armature.matrix_world
    core.select_only(bpy.context, [obj])
    bpy.ops.object.mode_set(mode="EDIT")
    previous = None
    try:
        for bone_name in bones:
            source = armature.data.bones.get(bone_name)
            if source is None:
                raise RuntimeError(f"cloth-chain-bone-missing: {bone_name} is not on the hero rig")
            edit = data.edit_bones.new(bone_name)
            edit.head = source.head_local
            edit.tail = source.tail_local
            if previous is not None:
                edit.parent = previous
                edit.use_connect = (previous.tail - edit.head).length < 1e-4
            previous = edit
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return obj


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
    target = mesh if mesh is not None else choose_cloth_mesh(settings, bones)
    if target not in hero_parts(settings):
        raise RuntimeError(f"cloth-mesh-not-hero: {target.name} is not an imported hero part")
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
        core.set_status(
            settings,
            f"{count} bone chains; {cloth_like} read like cloth"
            if count
            else "No numbered bone chain on this skeleton",
            "OK" if count else "WARN",
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
    DMF_OT_build_chain_cloth,
    DMF_OT_build_all_cloth,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
