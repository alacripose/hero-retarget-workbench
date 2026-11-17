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

# Bumped whenever the roster changes, so the picker rebuilds its visible rows
# without the panel draw comparing hundreds of entries.
ROSTER_SERIAL = 0

# Every live model the pak lists, as (slug, title, model path, vpk folder). The
# picker's Show filter is built from the folders this carries, so the choices are
# the pak's own directories instead of a hand-written category list.
MODEL_ITEMS: list[tuple[str, str, str, str]] = []
MODEL_ROOT_ITEMS: list[tuple[str, str, str]] = [
    ("ALL", "All folders", "Every model the pak lists"),
]


def model_root_items(self, context):
    return MODEL_ROOT_ITEMS


def set_model_items(rows) -> None:
    """Record the full model roster and the folders it came from.

    `rows` are `forge.live.Hero` shaped: slug, title and model path. The folder is
    the first two path segments under `models/`, which is what a VPK directory is.
    """
    global MODEL_ITEMS, MODEL_ROOT_ITEMS
    MODEL_ITEMS = []
    roots: set[str] = set()
    for row in rows:
        path = str(getattr(row, "model_path", "") or "").replace("\\", "/")
        parts = [part for part in path.strip("/").split("/") if part]
        folders = parts[:-1]
        root = "/".join(folders[:2]) if len(folders) >= 2 else (folders[0] if folders else "")
        if root:
            roots.add(root)
        MODEL_ITEMS.append(
            (str(getattr(row, "slug", path)), str(getattr(row, "title", path)), path, root)
        )
    MODEL_ROOT_ITEMS = [("ALL", "All folders", "Every model the pak lists")] + [
        (root, root[len("models/"):] if root.startswith("models/") else root, root)
        for root in sorted(roots)
    ]


def sync_folders(settings, force: bool = False) -> None:
    """Fill the folder picker with one row per VPK directory and its model count."""
    roots = tuple(item[0] for item in MODEL_ROOT_ITEMS)
    signature = "|".join(roots) + f"#{len(MODEL_ITEMS)}"
    if not force and settings.folder_signature == signature:
        return
    current = settings.model_root
    settings.folder_signature = signature
    settings.folder_rows.clear()
    counts: dict[str, int] = {}
    for *_, root in MODEL_ITEMS:
        counts[root] = counts.get(root, 0) + 1
    for value, label, description in MODEL_ROOT_ITEMS:
        row = settings.folder_rows.add()
        row.root = value
        row.label = label
        row.description = description
        row.count = len(MODEL_ITEMS) if value == "ALL" else counts.get(value, 0)
    settings.folder_index = next(
        (index for index, row in enumerate(settings.folder_rows) if row.root == current),
        0,
    )


def hero_items(self, context):
    return HERO_ITEMS


def set_hero_items(heroes) -> None:
    global HERO_ITEMS, ROSTER_SERIAL
    HERO_ITEMS = [("NONE", "Choose a hero", "Select a live hero from the current build")]
    HERO_ITEMS.extend((hero.slug, hero.title, hero.model_path) for hero in heroes)
    ROSTER_SERIAL += 1


class DMF_HeroRow(PropertyGroup):
    """One visible row of the Source page's hero picker."""

    slug: StringProperty()
    title: StringProperty()
    kind: StringProperty()
    model: StringProperty()


class DMF_FolderRow(PropertyGroup):
    """One VPK directory the model roster came from."""

    root: StringProperty()
    label: StringProperty()
    description: StringProperty()
    count: IntProperty()


def _hero_filter_changed(self, context) -> None:
    from . import heropick

    heropick.refresh(self)


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


class DMF_JobStage(PropertyGroup):
    """One visible bar for a stage of a background job."""

    key: StringProperty(name="Key", default="")
    label: StringProperty(name="Stage", default="")
    message: StringProperty(name="Step", default="")
    progress: FloatProperty(name="Progress", default=0.0, min=0.0, max=1.0, subtype="FACTOR")
    state: StringProperty(name="State", default="QUEUED")


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
            ("NEW", "New", "A gameplay clip queued by the automatic tail pass"),
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
    folders: IntProperty(name="Folders", default=0)
    vpks: IntProperty(name="VPKs", default=0)
    blends: IntProperty(name="Blends", default=0)
    with_cloth: IntProperty(name="With cloth", default=0)
    note: StringProperty(name="Note", default="")


class DMF_ModRow(PropertyGroup):
    """One old package found on disk, or one visible row of the filtered list."""

    path: StringProperty(name="Path", subtype="FILE_PATH", default="")
    addon: StringProperty(name="Package", default="")
    kind: StringProperty(name="Kind", default="vpk")
    hero: StringProperty(name="Hero", default="")
    modified: StringProperty(name="Modified", default="")
    toolchain: StringProperty(name="Toolchain", default="")
    sections: StringProperty(name="Cloth sections", default="")
    # Package folders can exceed the signed 32-bit range. This is display-only,
    # so a float holds the byte count without
    # wrapping; the scanner keeps the exact integer in its own record.
    bytes: FloatProperty(name="Bytes", default=0)
    note: StringProperty(name="Note", default="")
    models: StringProperty(name="Models", default="")
    blends: StringProperty(name="Blend files", default="")
    files: StringProperty(name="Contents", default="")
    counts: StringProperty(name="Content counts", default="")
    total_files: IntProperty(name="Files", default=0)


class DMF_ModContentRow(PropertyGroup):
    """One file inside the selected mod."""

    label: StringProperty(name="File", default="")
    category: StringProperty(name="Type", default="other")


class DMF_ModNodeRow(PropertyGroup):
    """One top-level node in the old model, kept or left behind."""

    name: StringProperty(name="Node", default="")
    selected: BoolProperty(name="Keep", default=False)
    changed: BoolProperty(name="Different", default=False)
    old_lines: IntProperty(name="Old lines", default=0)
    new_lines: IntProperty(name="Modern lines", default=0)


class DMF_ModDiffRow(PropertyGroup):
    """One file the old and modern models name differently."""

    path: StringProperty(name="File", default="")
    state: StringProperty(name="State", default="")
    old_size: FloatProperty(name="Old bytes", default=0.0)
    new_size: FloatProperty(name="Modern bytes", default=0.0)


class DMF_ModMatchRow(PropertyGroup):
    """One byte-identical file in a detected game or tools install."""

    mod_path: StringProperty(name="Package", default="")
    relative: StringProperty(name="Mod file", default="")
    install: StringProperty(name="Install", default="")
    label: StringProperty(name="Build name", default="")
    build: StringProperty(name="Build", default="")
    kind: StringProperty(name="Kind", default="")
    container: StringProperty(name="Container", subtype="FILE_PATH", default="")
    entry: StringProperty(name="Entry", default="")
    size: FloatProperty(name="Bytes", default=0.0)
    crc32: StringProperty(name="CRC32", default="")
    gameinfo: StringProperty(name="Gameinfo", subtype="FILE_PATH", default="")


def _mod_filter_changed(self, context) -> None:
    refresh_mod_rows(self)


def _mod_index_changed(self, context) -> None:
    refresh_mod_contents(self)
    refresh_mod_matches(self)
    clear_mod_analysis(self)


def _mod_content_filter_changed(self, context) -> None:
    refresh_mod_content_rows(self)


def refresh_mod_contents(settings) -> None:
    """List the selected mod's files, grouped by content type."""
    settings.mod_contents.clear()
    if settings.mod_rows:
        index = min(max(settings.mod_index, 0), len(settings.mod_rows) - 1)
        files = [
            line for line in (settings.mod_rows[index].files or "").splitlines() if line.strip()
        ]
        from forge import oldmods

        order = {"models": 0, "clips": 1, "materials": 2, "blends": 3, "other": 4}
        for line in sorted(
            files, key=lambda item: (order.get(oldmods.content_category(item), 9), item.lower())
        )[:300]:
            row = settings.mod_contents.add()
            row.label = line
            row.category = oldmods.content_category(line)
    refresh_mod_content_rows(settings)


def refresh_mod_matches(settings) -> None:
    """Show install copies of the selected package's files."""
    settings.mod_match_rows.clear()
    selected = None
    if settings.mod_rows:
        selected = settings.mod_rows[min(max(settings.mod_index, 0), len(settings.mod_rows) - 1)]
    if selected is None:
        settings.mod_match_index = 0
        return
    for row in settings.mod_matches:
        if row.mod_path != selected.path:
            continue
        copy = settings.mod_match_rows.add()
        for field in (
            "mod_path", "relative", "install", "label", "build", "kind",
            "container", "entry", "size", "crc32", "gameinfo",
        ):
            setattr(copy, field, getattr(row, field))
    settings.mod_match_index = min(
        max(settings.mod_match_index, 0), max(0, len(settings.mod_match_rows) - 1)
    )


def clear_mod_analysis(settings) -> None:
    settings.mod_nodes.clear()
    settings.mod_diffs.clear()
    settings.mod_node_index = 0
    settings.mod_diff_index = 0
    settings.mod_analysis_note = ""
    settings.mod_analysis_old_vmdl = ""
    settings.mod_analysis_new_vmdl = ""
    settings.mod_analysis_source = ""


def refresh_mod_content_rows(settings) -> None:
    """Copy the selected mod's files into the visible list for the active type."""
    wanted = getattr(settings, "mod_content_filter", "ALL").lower()
    settings.mod_content_rows.clear()
    for row in settings.mod_contents:
        if wanted != "all" and row.category != wanted:
            continue
        copy = settings.mod_content_rows.add()
        copy.label = row.label
        copy.category = row.category
    settings.mod_content_index = min(
        max(settings.mod_content_index, 0), max(0, len(settings.mod_content_rows) - 1)
    )


def refresh_mod_rows(settings) -> None:
    """Copy the scanned packages into the visible list for the active type."""
    wanted = getattr(settings, "mod_filter", "ALL")
    settings.mod_rows.clear()
    for row in settings.mods:
        if wanted == "FOLDER" and row.kind != "addon":
            continue
        if wanted == "VPK" and row.kind != "vpk":
            continue
        if wanted == "BLEND" and row.kind != "blend":
            continue
        copy = settings.mod_rows.add()
        for field in (
            "path", "addon", "kind", "hero", "modified", "toolchain", "sections",
            "bytes", "note", "models", "blends", "files", "counts", "total_files",
        ):
            setattr(copy, field, getattr(row, field))
    settings.mod_index = min(max(settings.mod_index, 0), max(0, len(settings.mod_rows) - 1))
    clear_mod_analysis(settings)
    refresh_mod_contents(settings)
    refresh_mod_matches(settings)


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
    tool_active: BoolProperty(name="Compiling", default=False)


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
        name="Project folder",
        description="Folder the active Blender project and its outputs are written under",
        subtype="DIR_PATH",
    )
    project_file: StringProperty(
        name="Project blend",
        description="The .blend created or opened for the active mod",
        subtype="FILE_PATH",
        default="",
    )
    source_origin: StringProperty(
        name="Source origin",
        description="The old package or scene the current Source files came from",
        default="",
    )
    mod_source_package: StringProperty(
        name="Source package",
        description="Folder, VPK or blend the active project was created from",
        default="",
    )
    mod_source_addon: StringProperty(name="Source addon", default="")
    mod_source_kind: StringProperty(name="Source kind", default="")
    mod_source_vmdl: StringProperty(
        name="Source model",
        description="The vmdl path the project uses when it is read as a Source-page package",
        default="",
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
    hero_slug: StringProperty(
        name="Hero",
        description="The chosen live model path, written by the picker",
        default="NONE",
    )
    mod_target: EnumProperty(
        name="Target hero",
        description="The live hero an old package is ported onto",
        items=hero_items,
        default=0,
    )
    hero_rows: CollectionProperty(type=DMF_HeroRow, description="Models the picker shows after the search and folder filter")
    hero_index: IntProperty(name="Model row", default=0)
    hero_query: StringProperty(
        name="Search models",
        description="Narrow the model list by title or model path",
        default="",
        update=_hero_filter_changed,
    )
    model_root: EnumProperty(
        name="Show",
        description="Restrict the list to one VPK folder the pak carries",
        items=model_root_items,
        default=0,
        update=_hero_filter_changed,
    )
    folder_rows: CollectionProperty(
        type=DMF_FolderRow,
        description="Every VPK directory the detected model roster came from",
    )
    folder_index: IntProperty(name="Folder row", default=0)
    folder_signature: StringProperty(name="Folder signature", default="")
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
        description=(
            "Logical path for the vmdl copy. It must match the target DMX path; the hero "
            "selection fills it from the live model path so no hero is baked in here"
        ),
        default="",
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
        default="",
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
    collection_index: IntProperty(name="Collection row", default=0)
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
    release_pak: StringProperty(
        name="Port pak",
        description="Where the packed VPK is written and read back for install",
        subtype="FILE_PATH",
        default="",
    )
    release_note: StringProperty(name="Release note", default="")
    release_model: StringProperty(
        name="Written vmdl",
        description="The model release.write_model produced, and the one staging copies",
        subtype="FILE_PATH",
        default="",
    )
    release_slot_number: IntProperty(
        name="Addon pak number",
        description=(
            "Which pakNN_dir.vpk to install into (1-99); 0 reuses the newest pak already in the "
            "selected game's addons folder"
        ),
        default=0,
        min=0,
        max=99,
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
            ("MODS", "Mods", "Scan older packages, update them, or backport them"),
            ("COMPONENTS", "Components", "Stage live cosmetic parts beside a mod"),
            ("RELEASE", "Release", "Write the model, compile, pack, install and launch"),
        ],
        default="SETUP",
    )

    # Mods page: folders to scan, what the scan found, and where a port goes.
    scan_roots: CollectionProperty(type=DMF_ScanRoot, description="Folders scanned for old packages")
    scan_root_index: IntProperty(name="Scan folder row", default=0)
    scan_since: StringProperty(name="Since", description="Only packages modified on or after this date", default="2024-01-01")
    scan_until: StringProperty(name="Until", description="Only packages modified on or before this date", default="")
    mods: CollectionProperty(type=DMF_ModRow, description="Old packages found by the last scan")
    mod_rows: CollectionProperty(type=DMF_ModRow, description="Visible packages after the type filter")
    mod_index: IntProperty(name="Package row", default=0, update=_mod_index_changed)
    mod_filter: EnumProperty(
        name="Package type",
        description="Show the scanned packages as folders, VPKs, blends or all of them",
        items=[
            ("ALL", "All", "Every scanned package"),
            ("FOLDER", "Folders", "Unpacked addon and project folders"),
            ("VPK", "VPKs", "Packed addon VPKs"),
            ("BLEND", "Blends", "Standalone Blender project files"),
        ],
        default="ALL",
        update=_mod_filter_changed,
    )
    mod_contents: CollectionProperty(type=DMF_ModContentRow, description="Files in the selected package")
    mod_content_rows: CollectionProperty(type=DMF_ModContentRow, description="Visible files after the content filter")
    mod_content_index: IntProperty(name="Content row", default=0)
    mod_content_filter: EnumProperty(
        name="Content type",
        description="Show the selected package's models, clips, materials, blends or other files",
        items=[
            ("ALL", "All", "Every file in the package"),
            ("MODELS", "Models", "Compiled .vmdl models"),
            ("CLIPS", "Clips", "Animation clip files"),
            ("MATERIALS", "Materials", "Material files and textures"),
            ("BLENDS", "Blends", "Blender project files"),
            ("OTHER", "Other", "Everything else"),
        ],
        default="ALL",
        update=_mod_content_filter_changed,
    )
    mod_report: StringProperty(name="Corpus receipt", subtype="FILE_PATH", default="")
    mod_note: StringProperty(name="Mods note", default="")
    mods_scanned: IntProperty(name="Packages scanned", default=0)
    mod_matches: CollectionProperty(type=DMF_ModMatchRow, description="Installed copies of scanned mod files")
    mod_match_rows: CollectionProperty(type=DMF_ModMatchRow, description="Installed copies of the selected package")
    mod_match_index: IntProperty(name="Match row", default=0)
    mod_nodes: CollectionProperty(type=DMF_ModNodeRow, description="Top-level nodes in the analyzed old model")
    mod_node_index: IntProperty(name="Node row", default=0)
    mod_diffs: CollectionProperty(type=DMF_ModDiffRow, description="Files that differ between the old and modern model")
    mod_diff_index: IntProperty(name="Diff row", default=0)
    mod_analysis_note: StringProperty(name="Analysis", default="")
    mod_analysis_old_vmdl: StringProperty(name="Old model", subtype="FILE_PATH", default="")
    mod_analysis_new_vmdl: StringProperty(name="Modern model", subtype="FILE_PATH", default="")
    mod_analysis_source: StringProperty(name="Old model source", default="")
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
    toolchain_index: IntProperty(name="Toolchain row", default=0)
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
        description="How much of the source tail motion reaches the hero tail bones",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    tail_manual: BoolProperty(
        name="Manual channel map",
        description="Show the per-bone pairing and single-clip writes; the automatic pass does not need them",
        default=False,
    )
    tail_note: StringProperty(name="Tail note", default="")
    tail_options: CollectionProperty(type=DMF_TailOption, description="Tail skeletons found in the hero, custom rig, extractions and clips")
    tail_option_index: IntProperty(name="Tail option", default=0)
    tail_bare_only: BoolProperty(
        name="Tail only (no clips, no skeleton doc)",
        description=(
            "Ship only the tail: its bones attached to the hero and the tail mesh, with no "
            "clips, no .vnmskel and no animation blending -- the haze_noskel shape without clips"
        ),
        default=False,
    )
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
            ("MAPPED", "Mapped groups", "Use only the mapped weights you painted; unweighted vertices use the nearest mapped bone envelope. No body surface sample"),
            ("HYBRID", "Surface + envelope", "Sample the hero body near the mesh; a sample can only add bones in the vertex's own mapped bone family"),
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
    job_stages: CollectionProperty(
        type=DMF_JobStage,
        description="Named stages of the running job, each with its own progress bar",
    )
    source_name_width: FloatProperty(
        name="Name width",
        description="Share of a model row given to the name; the rest holds the VPK folder",
        default=0.62,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    folder_name_width: FloatProperty(
        name="Name width",
        description="Share of a folder row given to the folder name; the rest holds the model count",
        default=0.68,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    scan_name_width: FloatProperty(
        name="Name width",
        description="Share of a scan-root row given to the folder; the rest holds the package count",
        default=0.66,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    mods_name_width: FloatProperty(
        name="Name width",
        description="Share of a package row given to the name; the rest holds kind, hero and date",
        default=0.52,
        min=0.3,
        max=0.85,
        subtype="FACTOR",
    )
    mod_contents_name_width: FloatProperty(
        name="Name width",
        description="Share of a contents row given to the file; the rest holds its type",
        default=0.7,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    mod_matches_name_width: FloatProperty(
        name="Name width",
        description="Share of a match row given to the installed build; the rest holds the file",
        default=0.42,
        min=0.25,
        max=0.85,
        subtype="FACTOR",
    )
    mod_nodes_name_width: FloatProperty(
        name="Name width",
        description="Share of a node row given to its name; the rest holds the state",
        default=0.62,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    mod_diffs_name_width: FloatProperty(
        name="Name width",
        description="Share of a differing-file row given to the file; the rest holds its state",
        default=0.64,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    clients_name_width: FloatProperty(
        name="Name width",
        description="Share of an install row given to the name; the rest holds kind and build",
        default=0.55,
        min=0.3,
        max=0.85,
        subtype="FACTOR",
    )
    components_name_width: FloatProperty(
        name="Name width",
        description="Share of a component row given to the name; the rest holds kind and size",
        default=0.55,
        min=0.3,
        max=0.85,
        subtype="FACTOR",
    )
    ik_name_width: FloatProperty(
        name="Name width",
        description="Share of an IK row given to the target; the rest holds the limb it follows",
        default=0.5,
        min=0.25,
        max=0.85,
        subtype="FACTOR",
    )
    tail_name_width: FloatProperty(
        name="Name width",
        description="Share of a tail row given to the hero bone; the rest holds the tail bone",
        default=0.5,
        min=0.25,
        max=0.85,
        subtype="FACTOR",
    )
    bone_name_width: FloatProperty(
        name="Name width",
        description="Share of a bone-map row given to the source bone; the rest holds target and state",
        default=0.45,
        min=0.25,
        max=0.85,
        subtype="FACTOR",
    )
    hierarchy_name_width: FloatProperty(
        name="Name width",
        description="Share of a hierarchy row given to the bone; the rest holds parent and children",
        default=0.5,
        min=0.25,
        max=0.85,
        subtype="FACTOR",
    )
    parts_name_width: FloatProperty(
        name="Name width",
        description="Share of a part row given to the object; the rest holds vertices and materials",
        default=0.55,
        min=0.3,
        max=0.85,
        subtype="FACTOR",
    )
    collection_name_width: FloatProperty(
        name="Name width",
        description="Share of a collection row given to its name; the rest holds mesh and object counts",
        default=0.58,
        min=0.3,
        max=0.85,
        subtype="FACTOR",
    )
    source_materials_name_width: FloatProperty(
        name="Name width",
        description="Share of a source-slot row given to the material; the rest holds its slot",
        default=0.72,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    part_materials_name_width: FloatProperty(
        name="Name width",
        description="Share of a part-slot row given to the material; the rest holds its slot",
        default=0.72,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    hero_parts_name_width: FloatProperty(
        name="Name width",
        description="Share of a hero-part row given to the object; the rest holds type and vertices",
        default=0.55,
        min=0.3,
        max=0.85,
        subtype="FACTOR",
    )
    cloth_name_width: FloatProperty(
        name="Name width",
        description="Share of a chain row given to the chain; the rest holds type and bone count",
        default=0.55,
        min=0.3,
        max=0.85,
        subtype="FACTOR",
    )
    rules_name_width: FloatProperty(
        name="Name width",
        description="Share of a rule row given to the pattern; the rest holds its state",
        default=0.65,
        min=0.3,
        max=0.9,
        subtype="FACTOR",
    )
    clips_name_width: FloatProperty(
        name="Name width",
        description="Share of a clip row given to the clip; the rest holds graph, file type and marks",
        default=0.52,
        min=0.3,
        max=0.85,
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
        description="Project build folder for the migrated addon; blank uses <workspace>/updates. The CSDK content copy is made separately by Stage update in CSDK",
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
        name="Copy old materials",
        description="Copy the old addon's vmat and texture assets into the update content tree; Stage update in CSDK puts them in the selected CSDK for editing",
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
    DMF_JobStage,
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
    DMF_ModContentRow,
    DMF_ModNodeRow,
    DMF_ModDiffRow,
    DMF_ModMatchRow,
    DMF_ClientRow,
    DMF_ComponentRow,
    DMF_HeroRow,
    DMF_FolderRow,
    DMF_Settings,
)


def _refresh_after_load(*_args) -> None:
    """A project saved with packages opens with its visible collection filled."""
    scene = getattr(bpy.context, "scene", None)
    settings = getattr(scene, "dmf", None) if scene is not None else None
    if settings is not None and settings.mods and not settings.mod_rows:
        refresh_mod_rows(settings)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dmf = PointerProperty(type=DMF_Settings)
    if _refresh_after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_refresh_after_load)


def unregister() -> None:
    if _refresh_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_refresh_after_load)
    del bpy.types.Scene.dmf
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
