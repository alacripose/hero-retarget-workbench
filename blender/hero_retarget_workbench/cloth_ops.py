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


CLASSES = (DMF_OT_import_hero_parts, DMF_OT_scan_cloth)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
