"""Collection-scoped custom model parts and explicit material slot assignment."""
from __future__ import annotations

from pathlib import Path

import bpy


def _walk(collection, seen: set[str], result: list[bpy.types.Object]) -> None:
    if collection is None or collection.name in seen:
        return
    seen.add(collection.name)
    result.extend(collection.objects)
    for child in collection.children:
        _walk(child, seen, result)


def collection_objects(collection) -> list[bpy.types.Object]:
    """Every object in a collection and its child collections, de-duplicated."""
    if collection is None:
        return []
    result: list[bpy.types.Object] = []
    _walk(collection, set(), result)
    unique = {}
    for obj in result:
        unique.setdefault(obj.name, obj)
    return [unique[name] for name in sorted(unique)]


def collection_meshes(collection) -> list[bpy.types.Object]:
    return [obj for obj in collection_objects(collection) if obj.type == "MESH"]


def collection_armatures(collection) -> list[bpy.types.Object]:
    return [obj for obj in collection_objects(collection) if obj.type == "ARMATURE"]


def export_meshes(settings) -> list[bpy.types.Object]:
    """Every mesh part that belongs in the exported model.

    The active part is the working part for fit, weights and material edits.
    Export is deliberately different: a ported character is usually split into
    body, head, hair, accessories and weapon meshes, and selecting one part must
    not silently drop the rest. The selected collection is the export scope.
    """
    collection = settings.custom_collection
    if collection is not None:
        rows = [
            obj
            for obj in collection_meshes(collection)
            if obj.data is not None and len(obj.data.vertices) > 0
        ]
        if rows:
            return rows

    rows = []
    seen = set()
    for row in settings.parts:
        obj = row.object
        if obj is None or obj.data is None or not len(obj.data.vertices):
            continue
        if obj.name in seen:
            continue
        seen.add(obj.name)
        rows.append(obj)
    if rows:
        return rows

    mesh = settings.custom_mesh
    return [mesh] if mesh is not None and mesh.data is not None else []


def largest_armature(collection) -> bpy.types.Object | None:
    arms = collection_armatures(collection)
    return max(arms, key=lambda obj: len(obj.data.bones)) if arms else None


def _slot_label(material) -> str:
    return material.name if material is not None else "empty slot"


def scan_materials(settings, source=None, target=None) -> tuple[int, int]:
    """Refresh the source and active-part slot lists without assigning anything."""
    source = source if source is not None else settings.material_source
    if source is None:
        source = settings.target_body
    if source is not None and settings.material_source is None:
        settings.material_source = source
    target = target if target is not None else settings.custom_mesh

    settings.source_materials.clear()
    if source is not None:
        for index, material in enumerate(source.data.materials):
            row = settings.source_materials.add()
            row.material = material
            row.slot_index = index
            row.label = _slot_label(material)

    settings.part_materials.clear()
    if target is not None:
        for index, material in enumerate(target.data.materials):
            row = settings.part_materials.add()
            row.material = material
            row.slot_index = index
            row.label = _slot_label(material)

    settings.source_material_count = len(settings.source_materials)
    settings.material_count = len(settings.part_materials)
    settings.source_material_index = max(
        0, min(settings.source_material_index, settings.source_material_count - 1)
    ) if settings.source_material_count else 0
    settings.part_material_index = max(
        0, min(settings.part_material_index, settings.material_count - 1)
    ) if settings.material_count else 0
    return settings.source_material_count, settings.material_count


def scan_parts(settings) -> int:
    """Scan the saved collection without choosing a new active part."""
    collection = settings.custom_collection
    if collection is None:
        raise RuntimeError("part-collection-missing: choose a Blender collection")
    rows = collection_meshes(collection)
    settings.parts.clear()
    for obj in rows:
        row = settings.parts.add()
        row.object = obj

    if settings.custom_mesh not in rows:
        settings.custom_mesh = None
    armatures = collection_armatures(collection)
    if settings.custom_armature not in armatures:
        settings.custom_armature = largest_armature(collection)
    if settings.custom_mesh is not None:
        settings.part_index = rows.index(settings.custom_mesh)
    else:
        settings.part_index = 0

    scan_materials(settings, target=settings.custom_mesh)
    return len(rows)


def use_part(settings, index: int) -> bpy.types.Object:
    if index < 0 or index >= len(settings.parts):
        raise RuntimeError("part-row-missing: scan the collection and choose a row")
    row = settings.parts[index]
    obj = row.object
    if obj is None:
        raise RuntimeError("part-object-missing: the collection row points at a deleted object")
    settings.part_index = index
    settings.custom_mesh = obj
    scan_materials(settings, target=obj)
    return obj


def capture_import(
    context,
    path,
    imported: list[bpy.types.Object],
    prefixes: list[str] | None = None,
) -> bpy.types.Collection:
    """Put one import in its own collection and give its parts their own names.

    A port that follows another port arrives carrying the previous rig's names.
    ``prefixes`` are the stale ones (this hero's body, the addon, the vmdl); a
    part keeps its own word — body, head, hair — and loses the old owner.
    """
    from forge import naming

    taken = {obj.name for obj in bpy.data.objects}
    plan = naming.part_names([obj.name for obj in imported], list(prefixes or []))
    for obj in imported:
        target = plan.get(obj.name, {}).get("object")
        if not target or target == obj.name:
            continue
        if target in taken:
            # Another object already owns that name; Blender would suffix this one
            # silently, which is exactly the kind of ghost name this avoids.
            target = obj.name
        taken.discard(obj.name)
        taken.add(target)
        obj.name = target
        if obj.data is not None and obj.data.users == 1:
            obj.data.name = target

    collection = bpy.data.collections.new(naming.collection_name(path))
    context.scene.collection.children.link(collection)
    for obj in imported:
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)
    return collection


def name_model(settings) -> dict[str, int]:
    """Apply the Model name to the imported collection, rig and parts.

    Parts lose a stale prefix and keep their own word; the rig gets ``_rig`` so it
    never shares a name with the mesh it deforms.
    """
    from pathlib import Path

    from forge import naming

    collection = settings.custom_collection
    armature = settings.custom_armature
    model = naming.sanitize(settings.custom_name)
    if not model:
        raise RuntimeError("model-name-missing: type a model name first")
    renamed = 0
    if collection is not None:
        wanted = f"DMF {model}"
        if collection.name != wanted:
            collection.name = wanted
            renamed += 1
    if armature is not None:
        wanted = f"{model}_rig"
        if armature.name != wanted:
            armature.name = wanted
            if armature.data is not None and armature.data.users == 1:
                armature.data.name = wanted
            renamed += 1
    prefixes = stale_prefixes(settings)
    meshes = collection_meshes(collection) if collection is not None else []
    plan = naming.part_names([obj.name for obj in meshes], prefixes)
    for obj in meshes:
        target = plan.get(obj.name, {}).get("object")
        if not target or target == obj.name:
            continue
        obj.name = target
        if obj.data is not None and obj.data.users == 1:
            obj.data.name = target
        renamed += 1
    settings.custom_name = model
    return {"renamed": renamed, "parts": len(meshes)}


def stale_prefixes(settings) -> list[str]:
    """Names a new import must not inherit: the hero, the addon, the vmdl.

    ``shiv_body`` also contributes ``shiv``: a hero's body is usually named
    ``<hero>_body``, so the hero's own name is the first token of it, and that is
    the token a previous import leaves on every part it made.
    """
    rows: list[str] = []
    for value in (
        settings.target_body.name if settings.target_body is not None else "",
        settings.target_armature.name if settings.target_armature is not None else "",
        settings.addon_name,
        Path(settings.vmdl).stem if settings.vmdl else "",
        Path(settings.hero_model_path).stem if settings.hero_model_path else "",
    ):
        value = (value or "").strip()
        if not value:
            continue
        rows.append(value)
        head = value.split("_")[0]
        if head and head != value and len(head) >= 4:
            rows.append(head)
    seen: set[str] = set()
    unique: list[str] = []
    for row in rows:
        if row.lower() in seen:
            continue
        seen.add(row.lower())
        unique.append(row)
    return unique


def _selected_source(settings) -> tuple[bpy.types.Material, str]:
    if not settings.source_materials:
        raise RuntimeError("material-source-empty: scan the source object's slots")
    index = max(0, min(settings.source_material_index, len(settings.source_materials) - 1))
    row = settings.source_materials[index]
    material = row.material
    if material is None:
        raise RuntimeError("material-source-slot-empty: choose a slot with a material")
    return material, row.label


def assign_material(settings, append: bool = False) -> tuple[str, int, bool]:
    target = settings.custom_mesh
    if target is None:
        raise RuntimeError("material-target-missing: choose an active part first")
    material, source_label = _selected_source(settings)

    if append or not target.data.materials:
        target.data.materials.append(material)
        slot_index = len(target.data.materials) - 1
        added = True
    else:
        slot_index = max(0, min(settings.part_material_index, len(target.data.materials) - 1))
        target.data.materials[slot_index] = material
        added = False

    scan_materials(settings, source=settings.material_source, target=target)
    settings.part_material_index = slot_index
    return source_label, slot_index, added


def clear_material(settings) -> tuple[str, int]:
    target = settings.custom_mesh
    if target is None:
        raise RuntimeError("material-target-missing: choose an active part first")
    if not target.data.materials:
        raise RuntimeError("material-target-empty: the active part has no material slots")
    index = max(0, min(settings.part_material_index, len(target.data.materials) - 1))
    removed = _slot_label(target.data.materials[index])
    old_indices = [polygon.material_index for polygon in target.data.polygons]
    target.data.materials.pop(index=index)
    for polygon, old_index in zip(target.data.polygons, old_indices):
        if old_index == index:
            polygon.material_index = 0
        elif old_index > index:
            polygon.material_index = old_index - 1
    scan_materials(settings, source=settings.material_source, target=target)
    return removed, index
