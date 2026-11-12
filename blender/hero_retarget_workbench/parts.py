"""Collection-scoped custom model parts and explicit material slot assignment."""
from __future__ import annotations

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


def capture_import(context, path, imported: list[bpy.types.Object]) -> bpy.types.Collection:
    """Put one import in its own collection so parts and materials can be scoped."""
    name = f"DMF {path.stem or 'custom'}"
    collection = bpy.data.collections.new(name)
    context.scene.collection.children.link(collection)
    for obj in imported:
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)
    return collection


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
