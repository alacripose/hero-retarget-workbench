"""Native UI lists for the workbench.

Every list implements ``filter_items`` through ``_filter``, so the native header
Blender shows above it, the search field, the invert toggle, the A-Z button and
its reverse, changes the view. A list that returns a fixed selection
makes those controls look available while doing nothing.
"""
from __future__ import annotations

import bpy
from bpy.types import UIList
from forge import cloth as clothscan
from forge import uilist

from . import parts as partscan
from . import ui_popit

_ICONS = {
    "MAPPED": "CHECKMARK",
    "UNMATCHED": "QUESTION",
    "EXTRA": "BONE_DATA",
    "IGNORED": "HIDE_ON",
}


def _filter(ui_list, texts, restrict=None):
    """The list header's search, invert and sort, as ``bitflag_filter_item`` flags."""
    flags, order = uilist.rows(
        texts,
        getattr(ui_list, "filter_name", "") or "",
        sort_alpha=bool(getattr(ui_list, "use_filter_sort_alpha", False)),
        reverse=bool(getattr(ui_list, "use_filter_sort_reverse", False)),
        invert=bool(getattr(ui_list, "use_filter_invert", False)),
        restrict=restrict,
    )
    bit = getattr(ui_list, "bitflag_filter_item", 1)
    return [bit if flag else 0 for flag in flags], order


def _bone_map_text(entry) -> str:
    return f"{entry.source} {entry.target} {entry.note} {entry.state}"


def _rules_text(entry) -> str:
    state = "extra" if entry.state == "EXTRA" else "ignore" if entry.state == "IGNORED" else "mapped"
    origin = "learned" if entry.origin == "learned" else "user"
    return f"{entry.source} {entry.target} {state} {origin}"


class DMF_UL_heroes(UIList):
    bl_idname = "DMF_UL_heroes"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        settings = getattr(context.scene, "dmf", None)
        chosen = settings is not None and settings.hero_slug == item.slug
        width = getattr(settings, "source_name_width", 0.62)
        left, right = ui_popit.columns(layout, width)
        left.label(
            text=item.title or item.slug,
            icon="RADIOBUT_ON" if chosen else "RADIOBUT_OFF",
        )
        right.alignment = "RIGHT"
        folder = item.kind.rstrip("/").split("/")[-1] if item.kind else "models"
        right.label(text=folder)


class DMF_UL_model_folders(UIList):
    bl_idname = "DMF_UL_model_folders"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.label} {row.root} {row.description}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        settings = getattr(context.scene, "dmf", None)
        chosen = settings is not None and settings.model_root == item.root
        width = getattr(settings, "folder_name_width", 0.68)
        left, right = ui_popit.columns(layout, width)
        left.label(
            text=item.label or item.root,
            icon="RADIOBUT_ON" if chosen else "RADIOBUT_OFF",
        )
        right.alignment = "RIGHT"
        right.label(text=f"{item.count:,}")


class DMF_UL_bone_map(UIList):
    bl_idname = "DMF_UL_bone_map"

    def filter_items(self, context, data, propname):
        settings = context.scene.dmf
        rows = getattr(data, propname)
        mode = settings.bone_filter
        # The state selector is a restriction; the header's search narrows it and
        # the A-Z button sorts what survives.
        restrict = None if mode == "ALL" else [row.state == mode for row in rows]
        return _filter(self, [_bone_map_text(row) for row in rows], restrict)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "bone_name_width", 0.45)
        source, target, state = ui_popit.columns(layout, width, (0.35, 0.25))
        source.label(text=item.source or "source", icon=_ICONS.get(item.state, "DOT"))
        target.label(text=item.target or "no target", icon="FORWARD")
        state.alignment = "RIGHT"
        state.label(text=item.state.lower())
        if item.note:
            state.label(text="", icon="INFO")


class DMF_UL_hierarchy(UIList):
    bl_idname = "DMF_UL_hierarchy"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.name} {row.parent}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "hierarchy_name_width", 0.5)
        left, parent, children = ui_popit.columns(layout, width, (0.3, 0.4))
        for _ in range(min(item.depth, 10)):
            left.label(text="", icon="BLANK1")
        left.label(
            text=item.name or "bone",
            icon="BONE_DATA" if item.children else "DOT",
        )
        parent.label(text=item.parent or "root", icon="BLANK1")
        children.alignment = "RIGHT"
        children.label(text=f"{item.children}" if item.children else "leaf")


class DMF_UL_parts(UIList):
    bl_idname = "DMF_UL_parts"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [row.object.name if row.object is not None else "missing part" for row in rows],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "parts_name_width", 0.55)
        left, verts, materials = ui_popit.columns(layout, width, (0.2, 0.2))
        obj = item.object
        if obj is None:
            left.label(text="missing part", icon="ERROR")
            return
        left.label(text=obj.name, icon="MESH_DATA")
        verts.alignment = "RIGHT"
        verts.label(text=f"{len(obj.data.vertices):,}v")
        materials.alignment = "RIGHT"
        materials.label(text=f"{len(obj.data.materials)}m")


class DMF_UL_collections(UIList):
    bl_idname = "DMF_UL_collections"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [row.name for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        settings = getattr(context.scene, "dmf", None)
        chosen = settings is not None and settings.custom_collection == item
        width = getattr(settings, "collection_name_width", 0.58)
        left, meshes, objects = ui_popit.columns(layout, width, (0.2, 0.2))
        left.label(
            text=item.name or "collection",
            icon="RADIOBUT_ON" if chosen else "FILE_FOLDER",
        )
        objects_in_collection = partscan.collection_objects(item)
        meshes.alignment = "RIGHT"
        meshes.label(text=f"{sum(1 for obj in objects_in_collection if obj.type == 'MESH'):,}m")
        objects.alignment = "RIGHT"
        objects.label(text=f"{len(objects_in_collection):,}o")


class DMF_UL_materials(UIList):
    bl_idname = "DMF_UL_materials"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.label} {row.material.name if row.material else ''} {row.slot_index}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        prop = (
            "part_materials_name_width"
            if active_propname == "part_material_index"
            else "source_materials_name_width"
        )
        width = getattr(context.scene.dmf, prop, 0.72)
        left, slot = ui_popit.columns(layout, width)
        material = item.material
        left.label(
            text=item.label or (material.name if material else "empty slot"),
            icon="MATERIAL" if material else "BLANK1",
        )
        slot.alignment = "RIGHT"
        slot.label(text=f"[{item.slot_index}]")


class DMF_UL_hero_parts(UIList):
    bl_idname = "DMF_UL_hero_parts"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.object.name if row.object else 'missing part'} "
                f"{'cloth' if row.object and clothscan.is_cloth(row.object.name) else ''}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "hero_parts_name_width", 0.55)
        left, kind, verts = ui_popit.columns(layout, width, (0.25, 0.2))
        obj = item.object
        if obj is None:
            left.label(text="missing part", icon="ERROR")
            return
        left.label(text=obj.name, icon="MESH_DATA")
        kind.label(text="cloth" if clothscan.is_cloth(obj.name) else "mesh")
        verts.alignment = "RIGHT"
        verts.label(text=f"{len(obj.data.vertices):,}v")


class DMF_UL_cloth_chains(UIList):
    bl_idname = "DMF_UL_cloth_chains"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.name} {row.root} {row.side} {'cloth' if clothscan.is_cloth(row.name) else ''}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "cloth_name_width", 0.55)
        left, kind, bones = ui_popit.columns(layout, width, (0.25, 0.2))
        icon = "MOD_CLOTH" if clothscan.is_cloth(item.name) else "BONE_DATA"
        built = item.target_mesh is not None
        left.label(
            text=item.name or "chain",
            icon="CHECKMARK" if built else icon,
        )
        kind.label(text="cloth" if built else item.source.lower())
        bones.alignment = "RIGHT"
        bones.label(text=f"{item.count}")


class DMF_UL_rules(UIList):
    bl_idname = "DMF_UL_bone_rules"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [_rules_text(row) for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "rules_name_width", 0.65)
        left, right = ui_popit.columns(layout, width)
        left.prop(item, "enabled", text="", emboss=False, icon="CHECKBOX_HLT" if item.enabled else "CHECKBOX_DEHLT")
        pattern = item.source or "pattern"
        target = item.target or "no target"
        if item.regex:
            left.label(text=f"{pattern} -> {target}", icon="DRIVER")
        elif "#" in pattern:
            left.label(text=f"{pattern} -> {target} {item.delta:+d}", icon="SORT_NUMERIC")
        elif pattern.strip().endswith("*"):
            left.label(text=f"{pattern} -> {target or 'extra'}", icon="FILE_FONT")
        else:
            stem = target.rsplit("_", 1)[0] if target.rsplit("_", 1)[-1] in ("L", "R") else target
            left.label(text=f"{pattern}* -> {stem or '?'}*", icon="LINKED")
        right.alignment = "RIGHT"
        if item.state == "EXTRA":
            right.label(text="extra")
        elif item.state == "IGNORED":
            right.label(text="ignore")
        elif item.origin == "learned":
            right.label(text="learned")


class DMF_UL_clips(UIList):
    bl_idname = "DMF_UL_clips"

    _ICONS = {
        "EDITABLE": "ACTION",
        "IMPORTED": "CHECKMARK",
        "WRITTEN": "EXPORT",
        "FAILED": "ERROR",
        "OPAQUE": "LOCKED",
    }

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        wanted = getattr(getattr(context.scene, "dmf", None), "clip_ag_filter", "ALL")
        return _filter(
            self,
            [
                f"{row.label} {row.name} {row.kind} {'compiled' if row.compiled else ''} "
                f"{row.ag} {row.state} {row.action} {row.source_hero}"
                for row in rows
            ],
            restrict=None if wanted == "ALL" else [row.ag == wanted for row in rows],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "clips_name_width", 0.52)
        left, graph, kind = ui_popit.columns(layout, width, (0.2, 0.28))
        left.label(text=item.label or item.name, icon=self._ICONS.get(item.state, "ACTION"))
        graph.label(text=item.ag if item.ag != "UNKNOWN" else "unknown")
        tag = item.kind if item.kind != "dmx" else ("dmx_c" if item.compiled else "dmx")
        kind.alignment = "RIGHT"
        kind.label(text=tag)
        if item.action and item.action != item.label:
            kind.label(text="", icon="ACTION")
        if item.export_bytes:
            kind.label(text="", icon="EXPORT")


class DMF_UL_ik(UIList):
    bl_idname = "DMF_UL_ik"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.bone} {row.target} {row.state}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "ik_name_width", 0.5)
        left, right = ui_popit.columns(layout, width)
        left.label(
            text=item.bone or "IK target",
            icon="BONE_DATA" if item.state == "READY" else "CONSTRAINT",
        )
        right.alignment = "RIGHT"
        right.label(text=item.target or "choose a limb")
        if item.constraints:
            right.label(text="", icon="CHECKMARK")


class DMF_UL_tail(UIList):
    bl_idname = "DMF_UL_tail"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.source} {row.target} {row.state}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "tail_name_width", 0.5)
        left, right = ui_popit.columns(layout, width)
        left.label(text=item.source or "hero tail", icon="BONE_DATA")
        right.alignment = "RIGHT"
        right.label(text=item.target or "choose a tail bone")
        if item.state == "MATCHED":
            right.label(text="", icon="CHECKMARK")


class DMF_UL_scan_roots(UIList):
    bl_idname = "DMF_UL_scan_roots"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.path} {row.note}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "scan_name_width", 0.66)
        left, right = ui_popit.columns(layout, width)
        left.prop(item, "enabled", text="", emboss=False)
        parts = [part for part in item.path.replace("\\", "/").rstrip("/").split("/") if part]
        # Two scan roots can both be called ``mods``. Three components keep the
        # Keep two Documents/mods folders distinguishable in the row.
        name = "/".join(parts[-3:]) or item.path or "folder"
        left.label(text=name, icon="FILE_FOLDER")
        right.alignment = "RIGHT"
        if item.packages:
            right.label(text=f"{item.packages}")
            if item.folders:
                right.label(text="", icon="FILE_FOLDER")
            if item.vpks:
                right.label(text="", icon="PACKAGE")
            if item.blends:
                right.label(text="", icon="FILE_BLEND")
        elif item.note:
            right.label(text="missing", icon="ERROR")


class DMF_UL_mod_contents(UIList):
    bl_idname = "DMF_UL_mod_contents"

    _ICONS = {
        "models": "MESH_DATA",
        "clips": "ACTION",
        "materials": "MATERIAL",
        "blends": "FILE_BLEND",
        "other": "FILE",
    }

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.label} {row.category}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "mod_contents_name_width", 0.7)
        left, right = ui_popit.columns(layout, width)
        left.label(text=item.label, icon=self._ICONS.get(item.category, "FILE"))
        right.alignment = "RIGHT"
        right.label(text=item.category)


class DMF_UL_mod_matches(UIList):
    bl_idname = "DMF_UL_mod_matches"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.label} {row.build} {row.install} {row.relative} {row.entry} {row.kind}"
                for row in rows
            ],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "mod_matches_name_width", 0.42)
        left, right = ui_popit.columns(layout, width)
        left.label(text=item.label or item.install or "install", icon="PACKAGE" if item.kind == "vpk" else "FILE_FOLDER")
        right.label(text=item.relative or item.entry or "file", icon="FILE")


class DMF_UL_mod_nodes(UIList):
    bl_idname = "DMF_UL_mod_nodes"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.name} {'changed' if row.changed else 'same'}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "mod_nodes_name_width", 0.62)
        left, right = ui_popit.columns(layout, width)
        left.prop(
            item,
            "selected",
            text="",
            emboss=False,
            icon="CHECKBOX_HLT" if item.selected else "CHECKBOX_DEHLT",
        )
        left.label(text=item.name or "node", icon="NODETREE")
        right.alignment = "RIGHT"
        right.label(
            text=f"{item.old_lines} / {item.new_lines}" if item.changed else "same",
            icon="FILE_REFRESH" if item.changed else "CHECKMARK",
        )


class DMF_UL_mod_diffs(UIList):
    bl_idname = "DMF_UL_mod_diffs"

    _ICONS = {
        "changed": "FILE_REFRESH",
        "old-only": "IMPORT",
        "new-only": "EXPORT",
        "missing": "ERROR",
    }

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.path} {row.state}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "mod_diffs_name_width", 0.64)
        left, right = ui_popit.columns(layout, width)
        left.label(text=item.path or "file", icon=self._ICONS.get(item.state, "FILE"))
        right.alignment = "RIGHT"
        right.label(text=item.state or "changed")


class DMF_UL_mods(UIList):
    bl_idname = "DMF_UL_mods"

    _ICONS = {"vpk": "PACKAGE", "addon": "FILE_FOLDER", "blend": "FILE_BLEND"}

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [
                f"{row.addon} {row.hero} {row.kind} {row.modified} {row.toolchain} {row.sections} {row.note} {row.path}"
                for row in rows
            ],
        )

    _KIND_LABELS = {"vpk": "VPK", "addon": "Folder", "blend": "Blend"}

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "mods_name_width", 0.52)
        left, kind, hero, modified = ui_popit.columns(layout, width, (0.32, 0.33, 0.35))
        left.label(
            text=item.addon or "package",
            icon=self._ICONS.get(item.kind, "PACKAGE"),
        )
        kind.label(text=self._KIND_LABELS.get(item.kind, item.kind))
        hero.label(text=item.hero or "unknown")
        modified.alignment = "RIGHT"
        modified.label(text=item.modified or "unknown")


class DMF_UL_clients(UIList):
    bl_idname = "DMF_UL_clients"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(
            self,
            [f"{row.label} {row.kind} {row.engine} {row.build} {row.path}" for row in rows],
        )

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "clients_name_width", 0.55)
        left, kind, build = ui_popit.columns(layout, width, (0.2, 0.25))
        if item.active:
            icon = "CHECKMARK"
        elif item.tool_active:
            icon = "TOOL_SETTINGS"
        elif item.can_compile:
            icon = "SETTINGS"
        else:
            icon = "PACKAGE"
        left.label(text=item.label or "install", icon=icon)
        kind.label(text=item.kind or "install")
        build.alignment = "RIGHT"
        build.label(text=item.build or "unknown")


class DMF_UL_components(UIList):
    bl_idname = "DMF_UL_components"

    def filter_items(self, context, data, propname):
        rows = getattr(data, propname)
        return _filter(self, [f"{row.name} {row.relative} {row.kind} {row.bytes}" for row in rows])

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        width = getattr(context.scene.dmf, "components_name_width", 0.55)
        left, kind, size = ui_popit.columns(layout, width, (0.2, 0.2))
        left.prop(
            item,
            "selected",
            text="",
            emboss=False,
            icon="CHECKBOX_HLT" if item.selected else "CHECKBOX_DEHLT",
        )
        left.label(text=item.name, icon="MESH_DATA" if item.kind == "dmx" else "FILE")
        kind.label(text=item.kind)
        size.alignment = "RIGHT"
        size.label(text=f"{item.bytes // 1024}k")


CLASSES = (
    DMF_UL_model_folders,
    DMF_UL_scan_roots,
    DMF_UL_mod_contents,
    DMF_UL_mod_matches,
    DMF_UL_mod_nodes,
    DMF_UL_mod_diffs,
    DMF_UL_heroes,
    DMF_UL_bone_map,
    DMF_UL_mods,
    DMF_UL_clients,
    DMF_UL_components,
    DMF_UL_hierarchy,
    DMF_UL_parts,
    DMF_UL_collections,
    DMF_UL_materials,
    DMF_UL_hero_parts,
    DMF_UL_cloth_chains,
    DMF_UL_rules,
    DMF_UL_clips,
    DMF_UL_ik,
    DMF_UL_tail,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
