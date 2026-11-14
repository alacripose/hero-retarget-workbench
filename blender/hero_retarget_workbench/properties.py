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


def tail_clip_items(self, context):
    """Imported clips, named explicitly so a tail write never guesses the row."""
    items = [("NONE", "Choose an imported clip", "No source action selected yet")]
    for index, row in enumerate(getattr(self, "clips", ())):
        if row.action:
            items.append((str(index), row.label or row.name, row.path))
    return items


def _rule_changed(self, context) -> None:
    """A rule edit reaches the bone map just after the last keystroke."""
    settings = getattr(getattr(context, "scene", None), "dmf", None)
    if settings is None:
        return
    from . import rules

    rules.request_fill(settings)


def _bone_target_changed(self, context) -> None:
    """A typed target teaches its rule at once and places the mirror row.

    Property callbacks cannot report an error to the user, so every failure is
    swallowed here and surfaces on the next explicit action instead.
    """
    settings = getattr(getattr(context, "scene", None), "dmf", None)
    if settings is None:
        return
    from . import poseview, rules

    if rules.is_suppressed():
        # A batch (scan, rule fill) writes hundreds of targets. Re-running the
        # ref pose for each one is what made the panel lock; the batch refreshes
        # once when it finishes.
        return
    try:
        rules.auto_fill(settings, self)
    except Exception:
        pass
    try:
        poseview.refresh(settings)
    except Exception:
        pass


class DMF_BoneEntry(PropertyGroup):
    source: StringProperty(name="Source", description="Bone or vertex group on your model")
    target: StringProperty(
        name="Target",
        description="Hero bone this source drives; typing one also answers its mirror",
        update=_bone_target_changed,
    )
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
    # What the last scan or rule pass wrote into this row. A row that no longer
    # matches is the user's own decision, and a rescan keeps it.
    scanned: StringProperty(name="Scanned target", default="")
    scanned_state: StringProperty(name="Scanned state", default="")


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


class DMF_ClothChain(PropertyGroup):
    """One numbered bone chain: a cloth chain, a hair strand set, or a finger."""

    name: StringProperty(name="Chain", default="")
    side: StringProperty(name="Side", default="")
    count: IntProperty(name="Segments", default=0)
    root: StringProperty(name="First bone", default="")
    bones: StringProperty(name="Bones", default="")
    source: EnumProperty(
        name="Source rig",
        description="Where the chain's bones were read from",
        items=[
            ("HERO", "Hero skeleton", "The chain already exists on the imported hero skeleton"),
            ("CUSTOM", "Custom rig", "Copy these bones out of the imported custom armature"),
        ],
        default="HERO",
    )
    source_armature: StringProperty(name="Source armature", default="")
    source_mesh: PointerProperty(
        name="Cloth mesh",
        description="The custom mesh this chain is skinned to; its weights drive the cloth",
        type=Object,
        poll=lambda self, obj: obj.type == "MESH",
    )
    parent: StringProperty(
        name="New parent bone",
        description="Hero bone the first copied chain bone hangs from",
        default="",
    )
    joined: IntProperty(name="Joined bones", default=0, min=0)
    proxy: BoolProperty(
        name="Source 2 proxy",
        description="Export this mesh as a PulseSrcOps CLOTHPROXY with cloth_enable weights",
        default=False,
    )
    target_mesh: PointerProperty(
        name="Cloth mesh",
        description="The imported hero mesh this chain was built on",
        type=Object,
        poll=lambda self, obj: obj.type == "MESH",
    )
    chain_object: PointerProperty(
        name="Chain",
        description="The ordered bone chain built for this run",
        type=Object,
    )
    pin_group: StringProperty(name="Pin group", default="")
    pin_bone: StringProperty(name="Pinned bone", default="")
    pin_count: IntProperty(name="Pinned vertices", default=0)
    cloth_modifier: StringProperty(name="Cloth modifier", default="")


class DMF_TailRow(PropertyGroup):
    """One hero tail channel and the tail-armature bone it drives."""

    source: StringProperty(name="Hero bone", default="")
    target: StringProperty(name="Tail bone", default="")
    state: EnumProperty(
        name="State",
        items=[
            ("MATCHED", "Matched", "The same name exists on both rigs"),
            ("CHOOSE", "Choose", "Pick the tail bone this hero bone drives"),
            ("MISSING", "Missing", "The chosen tail bone is not on the tail armature"),
        ],
        default="CHOOSE",
    )


class DMF_TailOption(PropertyGroup):
    """One discovered tail skeleton the Animations page can load as a tile."""

    label: StringProperty(name="Tail", default="")
    source: EnumProperty(
        name="Source",
        items=[
            ("HERO", "Hero", "The imported hero skeleton"),
            ("CUSTOM", "Custom rig", "The custom model's rig"),
            ("BODY", "Hero extract", "A body skeleton from an S2V extraction"),
            ("CLIP", "Clip", "An AG1/AG2 clip skeleton"),
            ("LIVE", "Live roster", "A skeleton decompiled from the live VPK"),
        ],
        default="CLIP",
    )
    path: StringProperty(name="File", subtype="FILE_PATH", default="")
    chain: StringProperty(name="Chain", default="")
    bones: StringProperty(name="Bones", default="")
    points: StringProperty(name="Points", default="")
    preview: StringProperty(name="Preview", subtype="FILE_PATH", default="")
    count: IntProperty(name="Bones", default=0)
    rig: PointerProperty(type=Object)


class DMF_MaterialRow(PropertyGroup):
    material: PointerProperty(name="Material", type=bpy.types.Material)
    slot_index: IntProperty(name="Slot", default=-1)
    label: StringProperty(name="Label", default="")


def _bone_map_toggle(_self, _context) -> None:
    """Drop the cached bone-map layout so the next draw re-reads the rig."""
    from . import hierarchy_view

    hierarchy_view.invalidate()


def _pose_preview_toggle(self, _context) -> None:
    """Show or clear the hero's reference stance on the mapped custom bones."""
    from . import poseview

    try:
        if self.pose_preview:
            poseview.apply(self)
            self.pose_preview_error = ""
        else:
            poseview.clear(self)
            self.pose_preview_error = ""
    except Exception as error:
        self.pose_preview_error = str(error)


class DMF_LodLevel(PropertyGroup):
    object: PointerProperty(
        name="LOD mesh",
        description="Persistent decimated mesh exported as this level",
        type=Object,
        poll=lambda self, obj: obj.type == "MESH",
    )
    level: IntProperty(name="Level", default=1, min=1)
    vertices: IntProperty(name="Vertices", default=0)


class DMF_BoneRule(PropertyGroup):
    """One pattern rule: a learned side rule, or a regex the user wrote."""

    source: StringProperty(
        name="Pattern",
        description="Stem for a side rule, prefix with *, # for a numbered series, regex",
        update=_rule_changed,
    )
    target: StringProperty(
        name="Target",
        description="Target stem, template with # for a series, or a bone name",
        update=_rule_changed,
    )
    delta: IntProperty(
        name="Number",
        description=(
            "For a series rule: the target's number is the source's number plus this; "
            "learned from one mapped row, editable by hand"
        ),
        default=0,
        update=_rule_changed,
    )
    regex: BoolProperty(
        name="Regex",
        description="Match the source as a regular expression",
        default=False,
        update=_rule_changed,
    )
    side_aware: BoolProperty(
        name="Side",
        description="Take the side token from the source and write it into the target",
        default=True,
        update=_rule_changed,
    )
    state: EnumProperty(
        name="Sets row to",
        description="What a row this rule answers becomes",
        items=[
            ("MAPPED", "Mapped", "Map the row onto the target bone"),
            ("EXTRA", "Extra", "Keep the row as an appendage; the extra-bone policy decides how"),
            ("IGNORED", "Ignored", "Drop the row's weights"),
        ],
        default="MAPPED",
        update=_rule_changed,
    )
    origin: StringProperty(
        name="From",
        description="Where the rule came from: a typed row, a bone-map row, or you",
        default="user",
    )
    enabled: BoolProperty(
        name="On",
        description="Use this rule when filling rows",
        default=True,
        update=_rule_changed,
    )
    support: IntProperty(name="Support", description="How many mapped rows agree with this rule", default=1)


class DMF_ClipRow(PropertyGroup):
    """One animation file found beside the hero extraction."""

    name: StringProperty(name="File", default="")
    label: StringProperty(name="Clip", default="")
    kind: StringProperty(name="Kind", default="dmx")
    compiled: BoolProperty(name="Compiled", default=False)
    ag: StringProperty(name="AnimGraph", default="UNKNOWN")
    path: StringProperty(name="Path", subtype="FILE_PATH", default="")
    size: IntProperty(name="Bytes", default=0)
    source_hero: StringProperty(name="Source hero", default="")
    action: StringProperty(name="Action", default="")
    tail_action: StringProperty(name="Tail action", default="")
    exported: StringProperty(name="Written", subtype="FILE_PATH", default="")
    export_bytes: IntProperty(name="Written bytes", default=0)
    state: EnumProperty(
        name="State",
        items=[
            ("EDITABLE", "Editable", "A decompiled DMX that can be imported"),
            ("IMPORTED", "Imported", "Imported onto the hero rig as an action"),
            ("WRITTEN", "Written", "The action was written back out as an animation DMX"),
            ("FAILED", "Failed", "The import or write refused this file; the reason is in the status"),
            ("OPAQUE", "Opaque", "Compiled game data or a skeleton; listed, never parsed"),
        ],
        default="EDITABLE",
    )


class DMF_IKRow(PropertyGroup):
    """One Source 2 IK target bone and the limb it is constrained to."""

    bone: StringProperty(name="IK target", default="")
    target: StringProperty(name="Follows", default="")
    state: EnumProperty(
        name="State",
        items=[
            ("READY", "Ready", "A limb is suggested; apply the constraints"),
            ("CHOOSE", "Choose", "No limb was suggested; choose one"),
            ("APPLIED", "Applied", "This addon's IK constraints are on the target"),
            ("MISSING", "Missing", "The chosen limb is not on the armature"),
        ],
        default="CHOOSE",
    )
    constraints: IntProperty(name="Constraints", default=0, min=0)


class DMF_HierarchyRow(PropertyGroup):
    name: StringProperty(name="Bone", default="")
    parent: StringProperty(name="Parent", default="")
    depth: IntProperty(name="Depth", default=0, min=0)
    children: IntProperty(name="Children", default=0, min=0)


class DMF_ScanRoot(PropertyGroup):
    """One folder the Mods page scans for old packages."""

    path: StringProperty(name="Folder", subtype="DIR_PATH", default="")
    enabled: BoolProperty(name="On", description="Include this folder in the next scan", default=True)
    packages: IntProperty(name="Packages", default=0)
    with_cloth: IntProperty(name="With cloth", default=0)
    note: StringProperty(name="Note", default="")


class DMF_ModRow(PropertyGroup):
    """One old package found on disk."""

    path: StringProperty(name="Path", subtype="FILE_PATH", default="")
    addon: StringProperty(name="Package", default="")
    kind: StringProperty(name="Kind", default="vpk")
    hero: StringProperty(name="Hero", default="")
    modified: StringProperty(name="Modified", default="")
    sections: StringProperty(name="Cloth sections", default="")
    bytes: IntProperty(name="Bytes", default=0)
    note: StringProperty(name="Note", default="")
    models: StringProperty(name="Models", default="")


class DMF_ClientRow(PropertyGroup):
    """One game or tools install the file can compile with or backport onto."""

    path: StringProperty(name="Path", subtype="DIR_PATH", default="")
    label: StringProperty(name="Client", default="")
    build: StringProperty(name="Build", default="")
    kind: StringProperty(name="Kind", default="")
    engine: StringProperty(name="Game", default="")
    can_compile: BoolProperty(name="Has compiler", default=False)
    can_backport: BoolProperty(name="Has game VPKs", default=False)
    active: BoolProperty(name="Active", default=False)


class DMF_ComponentRow(PropertyGroup):
    """One render-mesh asset in the current model extraction."""

    name: StringProperty(name="File", default="")
    relative: StringProperty(name="Relative path", default="")
    path: StringProperty(name="Source", subtype="FILE_PATH", default="")
    kind: StringProperty(name="Kind", default="dmx")
    bytes: IntProperty(name="Bytes", default=0)
    selected: BoolProperty(name="Stage", default=False)


def _paths_edited(self, context=None) -> None:
    """A path edit invalidates a detection failure shown on every page.

    The job card and status line outlive the failure that produced them. Without
    this, fixing the tool path still leaves the other pages saying it was not
    found, which is what 0.8.22's shared job block made visible.
    """
    if getattr(self, "job_state", "") == "FAILED":
        self.job_state = ""
        self.job_log = ""
        self.job_message = ""
        self.job_progress = 0.0
    status = (getattr(self, "status", "") or "").lower()
    if any(
        token in status
        for token in ("not found", "not detected", "choose source2viewer", "no tool paths")
    ):
        self.status = ""


class DMF_Settings(PropertyGroup):
    project_root: StringProperty(
        name="Workspace folder",
        description="Where this addon keeps extractions, proofs and logs when it is not bundled; the addon install itself goes into the CSDK13 root",
        subtype="DIR_PATH",
    )
    deadlock_root: StringProperty(
        name="Deadlock install",
        description="The Steam Deadlock folder that contains game/citadel/gameinfo.gi; saved with this .blend",
        subtype="DIR_PATH",
        update=_paths_edited,
    )
    s2v_cli: StringProperty(
        name="Source 2 Viewer CLI",
        description=(
            "Source2Viewer-CLI.exe, or the folder or GUI path whose folder holds it; "
            "the GUI itself cannot extract VPK files. Saved with this .blend"
        ),
        subtype="FILE_PATH",
        update=_paths_edited,
    )
    csdk_root: StringProperty(
        name="CSDK13 root",
        description="The CSDK13 folder that contains game/bin/win64/resourcecompiler.exe; saved with this .blend",
        subtype="DIR_PATH",
        update=_paths_edited,
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
        description="The S2V-extracted vmdl. Staging copies it unchanged into the CSDK13 addon",
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
    hero_parts: CollectionProperty(
        type=DMF_Part,
        description="Meshes imported from the hero extraction beside the body",
    )
    hero_part_index: IntProperty(name="Hero part row", default=0)
    cloth_chains: CollectionProperty(
        type=DMF_ClothChain,
        description="Numbered bone chains on the hero skeleton",
    )
    cloth_index: IntProperty(name="Cloth chain row", default=0)
    cloth_source: EnumProperty(
        name="Scan chains from",
        description="Use chains already on the hero skeleton, or copy them from the custom rig",
        items=[
            ("HERO", "Hero", "Scan the imported hero skeleton"),
            ("CUSTOM", "Custom rig", "Scan the imported custom model armature"),
        ],
        default="HERO",
    )
    cloth_build_skipped: StringProperty(
        name="Cloth build notes",
        description="Chains the last import could not build cloth for, and why",
        default="",
    )
    props_page: EnumProperty(
        name="Page",
        description="Which page the Hero Retarget properties tab shows",
        items=[
            ("SETUP", "Setup", "Live game, CSDK13 and workspace"),
            ("SOURCE", "Source", "Hero and custom model import"),
            ("PARTS", "Parts", "Custom model parts and material slots"),
            ("CLOTH", "Cloth", "Hero meshes and the chains cloth hangs from"),
            ("SKELETON", "Skeleton", "Bone map and reference pose"),
            ("RULES", "Rules", "Mapping rules"),
            ("ANIMATIONS", "Animations", "Clip import and write-back"),
            ("COMPARE", "Compare", "Split view and preview action"),
            ("WEIGHTS", "Weights", "Weight solve and the proof gate"),
            ("HANDOFF", "Handoff", "Export, stage and compile"),
            ("MODS", "Mods", "Scan older packages, update them, or backport them"),
            ("COMPONENTS", "Components", "Stage live cosmetic parts beside a mod"),
        ],
        default="CLOTH",
    )

    # Mods page: folders to scan, what the scan found, and where a port goes.
    scan_roots: CollectionProperty(type=DMF_ScanRoot, description="Folders scanned for old packages")
    scan_root_index: IntProperty(name="Scan folder row", default=0)
    scan_since: StringProperty(name="Since", description="Only packages modified on or after this date", default="2024-01-01")
    scan_until: StringProperty(name="Until", description="Only packages modified on or before this date", default="")
    mods: CollectionProperty(type=DMF_ModRow, description="Old packages found by the last scan")
    mod_index: IntProperty(name="Package row", default=0)
    mod_report: StringProperty(name="Corpus receipt", subtype="FILE_PATH", default="")
    mod_note: StringProperty(name="Mods note", default="")
    mods_scanned: IntProperty(name="Packages scanned", default=0)
    mod_target_client: StringProperty(
        name="Target client",
        description="Older game build (install, game, or game/citadel folder); every VPK in it is searched for the hero model",
        subtype="DIR_PATH",
        default="",
    )
    backport_experimental: BoolProperty(
        name="Enable backport",
        description="Allow transplanting a mod onto an older client's hero model; experimental",
        default=False,
    )

    # Setup page: tools and client installs.
    tools_folder: StringProperty(
        name="Tools folder",
        description="Where downloaded tools are installed; blank uses <workspace>/tools",
        subtype="DIR_PATH",
        default="",
    )
    clients_folder: StringProperty(
        name="Clients folder",
        description="Folder holding custom CSDK installs; blank uses <workspace>/clients",
        subtype="DIR_PATH",
        default="",
    )
    s2v_version: StringProperty(name="Source 2 Viewer version", default="")
    clients: CollectionProperty(type=DMF_ClientRow, description="CSDK-style installs this file can compile with")
    client_index: IntProperty(name="Client row", default=0)
    tools_note: StringProperty(name="Tools note", default="")

    # Components page: cosmetic-shaped assets and their staging target.
    components: CollectionProperty(type=DMF_ComponentRow, description="Component assets found in the current model extraction")
    component_index: IntProperty(name="Component row", default=0)
    component_addon: StringProperty(name="Component addon", description="Addon folder the component files are staged under", default="")
    component_note: StringProperty(name="Components note", default="")
    component_vmdl: StringProperty(
        name="Target vmdl",
        description="The staged addon vmdl whose RenderMeshList and BodyGroupList receive the component",
        subtype="FILE_PATH",
        default="",
    )
    component_slot: StringProperty(
        name="Body group",
        description="Body group the staged meshes become choices of; created when absent",
        default="component",
    )
    component_merge: BoolProperty(
        name="Register in vmdl",
        description=(
            "Add each staged DMX as a RenderMeshFile and a BodyGroupChoice so the game can "
            "switch it, instead of copying files only"
        ),
        default=True,
    )
    component_manifest: StringProperty(name="Components manifest", subtype="FILE_PATH", default="")
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
    bone_rules: CollectionProperty(
        type=DMF_BoneRule,
        description="Patterns learned from mapped rows, plus any regex rule you add",
    )
    bone_rule_index: IntProperty(name="Rule row", default=0)
    pose_preview: BoolProperty(
        name="Ref pose",
        description=(
            "Pose every mapped custom bone in the hero's reference stance, without editing "
            "the rest pose or writing keys"
        ),
        default=False,
        update=_pose_preview_toggle,
    )
    pose_preview_error: StringProperty(
        name="Ref pose error",
        description="Why the ref pose could not be applied, shown in Skeleton instead of failing silently",
        default="",
    )
    pose_stance: StringProperty(name="Source stance", default="")
    custom_name: StringProperty(
        name="Model name",
        description=(
            "What this port is called. Imported parts are named from their own file, and a "
            "prefix left over from the last rig is dropped"
        ),
        default="",
    )
    clips_dir: StringProperty(
        name="Clip folder",
        description=(
            "Optional folder holding animation DMX clips and their vnmclip pairs. Blank "
            "auto-discovers clips beside the hero extraction and its .vnmskel"
        ),
        subtype="DIR_PATH",
    )
    clip_ag_filter: EnumProperty(
        name="AnimGraph",
        description="Show only clips classified for one animation graph generation",
        items=[
            ("ALL", "All graphs", "Show every discovered clip"),
            ("AG1", "AG1", "Legacy AnimGraph 1 source clips"),
            ("AG2", "AG2", "AnimGraph 2 source clips and vnmclips"),
            ("UNKNOWN", "Unknown", "Clips whose folder does not identify a graph generation"),
        ],
        default="ALL",
    )
    clip_vnmskel: StringProperty(
        name="AG2 skeleton",
        description="Decompiled .vnmskel used by ModelDoc's Make Default Animgraph2",
        subtype="FILE_PATH",
        default="",
    )
    clip_export_dir: StringProperty(
        name="Write folder",
        description=(
            "Folder the written clips go under; blank writes to <clip folder>/edited, never over "
            "the extraction itself"
        ),
        subtype="DIR_PATH",
        default="",
    )
    clips: CollectionProperty(type=DMF_ClipRow, description="Animation clips found in the clip folder")
    clip_index: IntProperty(name="Clip row", default=0)
    clip_prefix: StringProperty(name="Prefix", description="Prefix applied to imported action names", default="")
    clip_note: StringProperty(name="Clip note", default="")
    clip_imported: IntProperty(name="Imported clips", default=0)
    clip_written: IntProperty(name="Written clips", default=0)
    clip_baked: IntProperty(name="Baked clips", default=0)
    clip_auto_note: StringProperty(name="Auto scan note", default="")
    tail_clip: EnumProperty(
        name="Source clip",
        description="Imported hero clip whose tail channels are written to the tail rig",
        items=tail_clip_items,
    )
    tail_armature: PointerProperty(
        name="Tail armature",
        description="Custom tail rig that receives the hero clip's tail channels (experimental)",
        type=Object,
        poll=lambda self, obj: obj.type == "ARMATURE",
    )
    tail_bones: CollectionProperty(type=DMF_TailRow, description="Hero tail channels mapped to tail bones")
    tail_index: IntProperty(name="Tail row", default=0)
    tail_scanned: IntProperty(name="Tail bones", default=0)
    tail_weight: FloatProperty(
        name="Blend",
        description="How much of the hero tail motion reaches the custom tail rig",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    tail_note: StringProperty(name="Tail note", default="")
    tail_options: CollectionProperty(type=DMF_TailOption, description="Tail skeletons found in the hero, custom rig, extractions and clips")
    tail_option_index: IntProperty(name="Tail option", default=0)
    tail_scan_dir: StringProperty(
        name="Extra tail folder",
        description="Optional folder of older hero models or clips to scan for tails",
        subtype="DIR_PATH",
        default="",
    )
    tail_option_note: StringProperty(name="Tail scan note", default="")
    ik_bones: CollectionProperty(type=DMF_IKRow, description="Source 2 IK targets on the hero rig")
    ik_index: IntProperty(name="IK row", default=0)
    ik_scanned: IntProperty(name="IK targets", default=0)
    ik_note: StringProperty(name="IK note", default="")
    rule_fill_running: BoolProperty(name="Rules running", default=False)
    rule_fill_done: IntProperty(name="Rows answered", default=0)
    rule_fill_total: IntProperty(name="Rows to answer", default=0)
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
    list_name_width: FloatProperty(
        name="Name width",
        description="Share of a list row given to the name; the rest holds the details",
        default=0.5,
        min=0.25,
        max=0.8,
        subtype="FACTOR",
    )
    job_cancellable: BoolProperty(name="Cancellable", default=False)
    job_state: StringProperty(name="Job state", default="")
    job_log: StringProperty(
        name="Job log",
        description="Steps of the running or last finished job, newest last",
        default="",
    )

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
    live_lods: BoolProperty(
        name="Use built LODs",
        description=(
            "Export the LOD meshes built in this file instead of asking PulseSrcOps to "
            "generate them, so export does not copy the armature per level"
        ),
        default=False,
    )
    lod_levels: CollectionProperty(
        type=DMF_LodLevel,
        description="LOD meshes built from the export scope and reused by every export",
    )
    lod_index: IntProperty(name="LOD row", default=0)
    lod_tick: IntProperty(
        name="LOD tick",
        description="Work tick the LOD meshes were built at; a later edit makes them stale",
        default=-1,
    )
    hierarchy: CollectionProperty(
        type=DMF_HierarchyRow,
        description="Bone hierarchy of the hero skeleton, drawn depth first",
    )
    hierarchy_index: IntProperty(name="Bone row", default=0)
    show_bone_map: BoolProperty(
        name="Bone map",
        description=(
            "Draw the hero skeleton in the 3D viewport at its rest positions: every bone "
            "head, tail and parent link, coloured by depth, clickable to select"
        ),
        default=False,
        update=_bone_map_toggle,
    )
    bone_map_plane: EnumProperty(
        name="Plane",
        description="Which axis pair the bone map looks along",
        items=[
            ("FRONT", "Front", "Look along +Y: side-to-side against up"),
            ("SIDE", "Side", "Look along +X: front-to-back against up"),
            ("TOP", "Top", "Look along +Z: side-to-side against front-to-back"),
        ],
        default="FRONT",
    )
    bone_map_labels: BoolProperty(
        name="All names",
        description="Label every bone; without it only the selected bone, its chain and its children are named",
        default=False,
    )
    bone_map_hover: StringProperty(name="Hovered bone", default="")
    bone_map_error: StringProperty(
        name="Bone map error",
        description="Set when the bone map's draw handler fails, so a broken pass is visible instead of silent",
        default="",
    )
    addon_name: StringProperty(
        name="Addon name",
        description=(
            "CSDK13 addon folder name. Staged to content/citadel_addons/<name>, "
            "compiled to game/citadel_addons/<name>"
        ),
        default="my_hero_port",
    )
    old_vpk: StringProperty(
        name="Old addon VPK",
        description="A compiled addon VPK or an extracted addon content folder to migrate onto the current live hero",
        subtype="FILE_PATH",
    )
    update_old_vmdl: StringProperty(
        name="Old model vmdl",
        description="Optional old vmdl when the old package has more than one; path may be relative to the old package",
        subtype="FILE_PATH",
    )
    update_output: StringProperty(
        name="Update output",
        description="Stage folder for the migrated addon; blank uses <workspace>/updates",
        subtype="DIR_PATH",
    )
    update_addon_name: StringProperty(
        name="Updated addon",
        description="Folder name for the migrated addon; blank derives it from the old package",
        default="",
    )
    update_model_policy: EnumProperty(
        name="Old model",
        description="Keep the old addon render meshes when they differ from the live hero, always keep them, or use the live meshes",
        items=[
            ("auto", "Preserve custom only", "Keep old meshes when their files differ from the live hero"),
            ("old", "Always old", "Always keep the old render meshes"),
            ("live", "Always live", "Use the live hero render meshes and leave old mesh files out"),
        ],
        default="auto",
    )
    update_preserve_cloth: BoolProperty(
        name="Preserve cloth/physics",
        description="Transplant every old cloth/physics section exactly; section names are discovered from the old model, not hard-coded",
        default=True,
    )
    update_preserve_materials: BoolProperty(
        name="Preserve old materials",
        description="Overlay the old addon's vmat and texture assets onto the live extraction",
        default=True,
    )
    update_replace_output: BoolProperty(
        name="Replace output",
        description="Replace the addon folder if the update output already exists",
        default=False,
    )
    stage_dir: StringProperty(
        name="Install root",
        description=(
            "Optional CSDK13 install override. Used only when it contains "
            "game/bin/win64/resourcecompiler.exe; blank uses the CSDK13 root from Setup"
        ),
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


CLASSES = (
    DMF_BoneEntry,
    DMF_ProofCheck,
    DMF_Part,
    DMF_ClothChain,
    DMF_MaterialRow,
    DMF_TailOption,
    DMF_LodLevel,
    DMF_BoneRule,
    DMF_ClipRow,
    DMF_IKRow,
    DMF_TailRow,
    DMF_HierarchyRow,
    DMF_ScanRoot,
    DMF_ModRow,
    DMF_ClientRow,
    DMF_ComponentRow,
    DMF_Settings,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dmf = PointerProperty(type=DMF_Settings)


def unregister() -> None:
    del bpy.types.Scene.dmf
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
