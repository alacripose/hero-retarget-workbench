"""Settings for the Hero Retarget Workbench workbench."""
from __future__ import annotations

import os

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Object, PropertyGroup


HERO_ITEMS: list[tuple[str, str, str]] = [
    ("NONE", "Detect live heroes", "Find the current live hero models through Source 2 Viewer"),
]


def hero_items(self, context):
    return HERO_ITEMS


def set_hero_items(heroes) -> None:
    global HERO_ITEMS
    HERO_ITEMS = [("NONE", "Choose a hero", "Select a live hero from the current build")]
    HERO_ITEMS.extend((hero.slug, hero.title, hero.model_path) for hero in heroes)


class DMF_BoneEntry(PropertyGroup):
    source: StringProperty(name="Source", description="Bone or vertex group on your model")
    target: StringProperty(name="Target", description="Hero bone this source drives")
    state: EnumProperty(
        name="State",
        description="What this map row does when the solver runs",
        items=[
            ("MAPPED", "Mapped", "Copy this source's weights onto the target bone"),
            ("UNMATCHED", "Unmatched", "No target chosen; the solver refuses a weighted row"),
            ("EXTRA", "Extra", "Keep this bone as an extra appendage, or fold it by policy"),
            ("IGNORED", "Ignored", "Drop this group's weights from the solved mesh"),
        ],
        default="UNMATCHED",
    )
    note: StringProperty(name="Note", default="")


class DMF_ProofCheck(PropertyGroup):
    name: StringProperty(name="Check", default="")
    token: StringProperty(name="Token", default="unchecked")
    detail: StringProperty(name="Detail", default="")


class DMF_Part(PropertyGroup):
    object: PointerProperty(
        name="Mesh part",
        description="A mesh object in the selected collection that can be made the active part",
        type=Object,
        poll=lambda self, obj: obj.type == "MESH",
    )


class DMF_MaterialRow(PropertyGroup):
    material: PointerProperty(name="Material", type=bpy.types.Material)
    slot_index: IntProperty(name="Slot", default=-1)
    label: StringProperty(name="Label", default="")


class DMF_Settings(PropertyGroup):
    project_root: StringProperty(
        name="Workspace folder",
        description="Where this addon keeps extractions, proofs, logs and the compiler handoff when it is not bundled",
        subtype="DIR_PATH",
    )
    deadlock_root: StringProperty(
        name="Deadlock install",
        description="The Steam Deadlock folder that contains game/citadel/gameinfo.gi; saved with this .blend",
        subtype="DIR_PATH",
    )
    s2v_cli: StringProperty(
        name="Source 2 Viewer CLI",
        description="Source2Viewer-CLI executable; saved with this .blend",
        subtype="FILE_PATH",
    )
    csdk_root: StringProperty(
        name="CSDK13 root",
        description="The CSDK13 folder that contains game/bin/win64/resourcecompiler.exe; saved with this .blend",
        subtype="DIR_PATH",
    )
    hero_slug: EnumProperty(name="Hero", items=hero_items)
    build: StringProperty(name="Build", default="")
    hero_model_path: StringProperty(name="Live model", default="")
    extraction_dir: StringProperty(
        name="S2V extraction",
        description="Source 2 Viewer writes this folder for the selected hero",
        subtype="DIR_PATH",
    )
    vmdl: StringProperty(
        name="Hero vmdl",
        description="The S2V-extracted vmdl. Staging copies it unchanged to the compiler handoff",
        subtype="FILE_PATH",
    )
    vmdl_relative: StringProperty(
        name="vmdl path in content",
        description="Logical path for the vmdl copy. It must match the target DMX path",
        default="models/heroes_staging/haze/haze.vmdl",
    )
    body_dmx: StringProperty(
        name="Hero body DMX",
        description="The target body file to import and replace",
        subtype="FILE_PATH",
    )
    materials_dir: StringProperty(
        name="Hero material root",
        description=(
            "Content root containing the hero's materials tree: models/**/materials/*.vmat "
            "and the texture images they reference. Paths below this root are preserved. "
            "Leave blank to use the hero extraction."
        ),
        subtype="DIR_PATH",
    )
    custom_materials_dir: StringProperty(
        name="Custom material root",
        description=(
            "Content root containing your model's materials/*.vmat and texture images at "
            "the same relative paths the model references. Copied after the hero materials."
        ),
        subtype="DIR_PATH",
    )
    target_dmx_relative: StringProperty(
        name="DMX path in content",
        description="Logical path of the DMX that the hero vmdl references",
        default="models/heroes_staging/haze/haze_body.dmx",
    )
    custom_model: StringProperty(
        name="Custom model",
        description="glTF, GLB, FBX, OBJ, or DMX to port",
        subtype="FILE_PATH",
    )
    custom_collection: PointerProperty(
        name="Part collection",
        description="Blender collection whose mesh objects are the custom model parts. Child collections are included",
        type=bpy.types.Collection,
    )
    custom_mesh: PointerProperty(name="Mesh", type=Object, poll=lambda self, obj: obj.type == "MESH")
    custom_armature: PointerProperty(name="Rig", type=Object, poll=lambda self, obj: obj.type == "ARMATURE")
    target_armature: PointerProperty(name="Hero skeleton", type=Object, poll=lambda self, obj: obj.type == "ARMATURE")
    target_body: PointerProperty(name="Hero body", type=Object, poll=lambda self, obj: obj.type == "MESH")

    parts: CollectionProperty(
        type=DMF_Part,
        description="Mesh objects found in the selected part collection",
    )
    part_index: IntProperty(name="Part row", default=0)
    material_source: PointerProperty(
        name="Material source",
        description="Object whose material slots are the source list; defaults to the hero body",
        type=Object,
        poll=lambda self, obj: obj.type == "MESH",
    )
    source_materials: CollectionProperty(type=DMF_MaterialRow)
    source_material_index: IntProperty(name="Source slot", default=0)
    source_material_count: IntProperty(name="Source slots", default=0)
    part_materials: CollectionProperty(type=DMF_MaterialRow)
    part_material_index: IntProperty(name="Part slot", default=0)
    axis_preset: EnumProperty(
        name="Fit transform",
        description="Change this only if the custom model uses a different axis system",
        items=[
            ("identity", "Identity", "Keep the custom model axes"),
            ("blender-to-source2", "Blender to Source 2", "Map the Blender forward and side axes into Source 2"),
            ("source2-to-blender", "Source 2 to Blender", "Map the Source 2 forward and side axes into Blender"),
            ("gltf-to-source2", "glTF to Source 2", "Map the glTF forward and side axes into Source 2"),
            ("source2-to-gltf", "Source 2 to glTF", "Map the Source 2 forward and side axes into glTF"),
            ("mirror-x", "Mirror X", "Mirror across X; this flips handedness"),
        ],
        default="identity",
    )
    fit_scale: FloatProperty(
        name="Scale",
        description="Adds a uniform scale to the fit transform",
        default=1.0,
        min=0.0001,
        soft_max=10.0,
    )
    fit_to_height: BoolProperty(
        name="Match hero height",
        description="Scale the custom mesh to the target body's height before retargeting",
        default=False,
    )

    bone_map: CollectionProperty(type=DMF_BoneEntry)
    bone_map_index: IntProperty(name="Bone map row", default=0)
    bone_filter: EnumProperty(
        name="Show",
        description="Filter the bone map without changing what the solver reads",
        items=[
            ("ALL", "All rows", "Show every source bone"),
            ("UNMATCHED", "Unmatched", "Show only rows with no target"),
            ("MAPPED", "Mapped", "Show only mapped rows"),
            ("EXTRA", "Extra", "Show only extra appendage rows"),
            ("IGNORED", "Ignored", "Show only ignored rows"),
        ],
        default="ALL",
    )
    fallback_bone: StringProperty(
        name="Fold fallback",
        description="If no mapped parent exists, fold an extra group onto this hero bone",
        default="",
    )

    weight_mode: EnumProperty(
        name="Weight method",
        description="How the custom mesh gets hero weights",
        items=[
            ("HYBRID", "Surface + envelope", "Sample the hero body near the mesh; use bone envelopes for wings, tails, hair and other geometry outside the body"),
            ("CUSTOM", "Custom groups", "Use the mapped custom weights only; extra groups follow the extra-bone policy"),
            ("ENVELOPE", "Bone envelope", "Weight every vertex to the nearest mapped bone segments, independent of the hero body surface"),
        ],
        default="HYBRID",
    )
    max_distance: FloatProperty(
        name="Surface reach",
        description="How far a vertex can be from the hero body before the bone envelope takes over",
        default=0.35,
        min=0.001,
        soft_max=5.0,
        precision=3,
    )
    falloff: FloatProperty(
        name="Falloff",
        description="Higher values keep weights closer to the nearest bone or surface sample",
        default=2.0,
        min=0.25,
        soft_max=8.0,
        precision=2,
    )
    max_influences: IntProperty(
        name="Max influences",
        description="Keep at most this many bones per vertex, then normalize",
        default=4,
        min=1,
        max=12,
    )
    surface_samples: IntProperty(
        name="Surface samples",
        description="Hero body vertices blended for each custom vertex near the body",
        default=4,
        min=1,
        max=12,
    )
    extra_policy: EnumProperty(
        name="Extra bones",
        description="What to do with bones that are not in the hero skeleton",
        items=[
            ("FOLD", "Fold into parent", "Move extra weights to the nearest mapped ancestor or the fold fallback"),
            ("KEEP", "Keep extra bones", "Copy the extra bones into the hero armature and keep their weights"),
            ("DROP", "Drop extra weights", "Remove unmapped extra groups"),
        ],
        default="FOLD",
    )
    protected_groups: StringProperty(
        name="Protect groups",
        description="Comma-separated vertex groups the solver must not overwrite",
        default="",
    )
    clear_existing: BoolProperty(
        name="Clear old groups",
        description="Remove vertex groups the solver does not use before writing the new weights",
        default=True,
    )
    manual_weight: FloatProperty(
        name="Assign weight",
        description="Weight used by Assign selected to the active group",
        default=1.0,
        min=0.0,
        max=1.0,
        precision=3,
    )
    nudge_axis: EnumProperty(
        name="Nudge axis",
        description="Pose-space axis for the manual bone nudge",
        items=[("X", "X", "X"), ("Y", "Y", "Y"), ("Z", "Z", "Z")],
        default="X",
    )
    nudge_amount: FloatProperty(
        name="Step",
        description="Distance or angle per nudge click",
        default=0.01,
        min=0.0001,
        soft_max=0.25,
        precision=4,
    )
    nudge_rotate: BoolProperty(
        name="Rotate",
        description="Rotate the active pose bone instead of translating it",
        default=False,
    )

    compare_action: PointerProperty(
        name="Preview action",
        description="Action applied to both comparison rigs before playback",
        type=bpy.types.Action,
    )
    compare_active: BoolProperty(name="Split compare active", default=False)

    axis_tick: IntProperty(
        name="Axis tick",
        description="Work tick. A proof is current only at the tick it was minted",
        default=0,
        min=0,
    )
    proof_presenter: StringProperty(
        name="Presenter",
        description="Who is accountable for the retarget proof",
        default=os.environ.get("USERNAME", "artist"),
    )
    proof_ticket: StringProperty(
        name="Ticket",
        description="The ticket this retarget serves",
        default="TICKET-0002",
    )
    proof_status: StringProperty(name="Proof status", default="unchecked")
    proof_path: StringProperty(name="Proof path", subtype="FILE_PATH", default="")
    proof_artifact: StringProperty(name="Artifact path", subtype="FILE_PATH", default="")
    proof_digest: StringProperty(name="Proof digest", default="")
    proof_claim: StringProperty(name="Proof claim", default="")
    proof_tick: StringProperty(name="Proof tick", default="")
    proof_world_digest: StringProperty(name="World digest", default="")
    proof_checks: CollectionProperty(type=DMF_ProofCheck)

    job_running: BoolProperty(name="Job running", default=False)
    job_kind: StringProperty(name="Job kind", default="")
    job_label: StringProperty(name="Job", default="")
    job_message: StringProperty(name="Job step", default="")
    job_progress: FloatProperty(name="Progress", default=0.0, min=0.0, max=1.0, subtype="FACTOR")
    job_cancellable: BoolProperty(name="Cancellable", default=False)

    generate_lods: BoolProperty(
        name="Generate LODs",
        description="Generate decimated LOD DMXs and replace the hero LOD slots with them",
        default=True,
    )
    lod_count: IntProperty(
        name="LOD count",
        description="Zero matches the hero extraction; otherwise this many LODs are generated",
        default=0,
        min=0,
        soft_max=6,
    )
    lod_decimate: FloatProperty(
        name="Decimate per LOD",
        description="Percentage of faces removed for each successive LOD",
        default=25.0,
        min=1.0,
        max=90.0,
        precision=1,
    )
    addon_name: StringProperty(name="Addon name", default="my_hero_port")
    stage_dir: StringProperty(
        name="Stage folder",
        description="The compiler handoff folder. Staging copies the vmdl and materials here",
        subtype="DIR_PATH",
    )
    status: StringProperty(name="Status", default="Detect the live build to begin")
    status_kind: EnumProperty(
        name="Status kind",
        items=[
            ("INFO", "Info", ""),
            ("BUSY", "Busy", ""),
            ("OK", "Ready", ""),
            ("ERROR", "Error", ""),
            ("WARN", "Warning", ""),
        ],
        default="INFO",
    )
    unmatched: StringProperty(name="Unmatched groups", default="")
    material_count: IntProperty(name="Materials", default=0)
    exported_dmx: StringProperty(name="Exported DMX", subtype="FILE_PATH", default="")


CLASSES = (DMF_BoneEntry, DMF_ProofCheck, DMF_Part, DMF_MaterialRow, DMF_Settings)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dmf = PointerProperty(type=DMF_Settings)


def unregister() -> None:
    del bpy.types.Scene.dmf
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
