"""Experimental tail-armature blending for imported hero clips.

The hero clip already contains the tail's animation.  A custom model can carry
that tail on a separate armature, so this section samples each imported hero
action and writes the mapped tail channels onto the selected tail armature.  It
is deliberately separate from the body action and from the Cloth page: a tail
chain can be simulated as cloth while its animation is copied here.

This is a local-space transfer.  It is exact when the tail bones share the
hero's rest orientation and is labelled experimental for every other rig.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import bpy
from bpy.types import Operator
from mathutils import Matrix

from forge import live, tails as tailscan
from forge import tailimage

from . import core, jobs, source2


def _rigs(settings):
    hero = settings.target_armature
    tail = settings.tail_armature
    if hero is None:
        raise RuntimeError("tail-needs-hero: import the hero skeleton first")
    if tail is None:
        raise RuntimeError("tail-needs-armature: choose the custom tail armature first")
    if tail == hero:
        raise RuntimeError("tail-is-hero: choose the separate tail armature, not the hero skeleton")
    return hero, tail


def scan(settings) -> int:
    hero, tail = _rigs(settings)
    rows = tailscan.candidates(
        [bone.name for bone in hero.data.bones],
        [bone.name for bone in tail.data.bones],
    )
    old = {row.source: row.target for row in settings.tail_bones if row.source and row.target}
    settings.tail_bones.clear()
    for item in rows:
        row = settings.tail_bones.add()
        row.source = item.source
        row.target = old.get(item.source, item.target)
        row.state = "MATCHED" if row.target and tail.data.bones.get(row.target) else (
            "CHOOSE" if not row.target else "MISSING"
        )
    settings.tail_index = 0
    settings.tail_scanned = len(rows)
    settings.tail_note = (
        f"{len(rows)} tail channels on {hero.name}; {sum(1 for row in settings.tail_bones if row.target)} "
        f"are paired with {tail.name}"
    )
    return len(rows)


def _chains(armature) -> list[tailscan.TailChain]:
    return tailscan.chains([bone.name for bone in armature.data.bones])


def _points(armature, chain: tailscan.TailChain) -> list[tuple[float, float, float]]:
    points = []
    for name in chain.bones:
        bone = armature.data.bones.get(name)
        if bone is None:
            continue
        points.append(tuple(bone.head_local))
    if chain.bones:
        last = armature.data.bones.get(chain.bones[-1])
        if last is not None:
            points.append(tuple(last.tail_local))
    return points


def _points_text(points) -> str:
    return ";".join(",".join(f"{value:.5f}" for value in point) for point in points)


def _add_option(settings, *, label, source, path, chain, points, armature=None) -> None:
    if not points:
        return
    bones = ",".join(chain.bones)
    source_path = str(path or "")
    for existing in settings.tail_options:
        same_chain = existing.chain == chain.name and existing.bones == bones
        same_label = existing.label.strip().lower() == label.strip().lower()
        if same_chain and same_label:
            return
        if (
            same_chain
            and existing.path
            and source_path
            and Path(bpy.path.abspath(existing.path)).resolve() == Path(bpy.path.abspath(source_path)).resolve()
        ):
            return
    safe = "".join(character if character.isalnum() else "_" for character in label)[:48]
    digest = hashlib.sha1(f"{label}|{source}|{chain.name}|{path}".encode("utf-8")).hexdigest()[:10]
    preview = core.project_root(settings) / "artifacts" / "tail-previews" / f"{safe}-{digest}.png"
    tailimage.write_tail_png(preview, [points])
    option = settings.tail_options.add()
    option.label = label
    option.source = source
    option.path = str(path or "")
    option.chain = chain.name
    option.bones = bones
    option.points = _points_text(points)
    option.preview = str(preview) if preview.is_file() else ""
    option.count = len(chain.bones)
    option.rig = armature


def _hero_key(root: Path, path: Path) -> str:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    for index, part in enumerate(parts):
        if part.lower() in ("heroes_wip", "heroes_staging") and index + 1 < len(parts):
            return parts[index + 1]
    return path.parent.name


def _candidate_roots(settings) -> list[Path]:
    roots: list[Path] = []
    extraction = Path(bpy.path.abspath(settings.extraction_dir)) if settings.extraction_dir else None
    if extraction and extraction.is_dir():
        roots.append(extraction)
        # Every sibling with a models/ tree is another hero extraction.  Do not
        # require the parent folder to be literally named "extractions"; the
        # owner's Source page can point anywhere, and the first scanner missed
        # every sibling in a differently named workspace folder because of it.
        for parent in (extraction.parent, extraction.parent.parent):
            if parent.is_dir():
                roots.extend(
                    child for child in parent.iterdir()
                    if child.is_dir() and (child / "models").is_dir()
                )
    extra = Path(bpy.path.abspath(settings.tail_scan_dir)) if settings.tail_scan_dir else None
    if extra and extra.is_dir():
        roots.append(extra)
    project = core.project_root(settings)
    if project:
        roots.append(project / "artifacts" / "extractions")
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _import_candidate(path: Path):
    """Import one skeleton for its rest positions, then remove it again."""
    before_objects = {obj.name for obj in bpy.context.scene.objects}
    before_actions = {action.name for action in bpy.data.actions}
    try:
        source2.import_dmx(path, append="NEW_ARMATURE")
        armatures = [
            obj for obj in bpy.context.scene.objects
            if obj.name not in before_objects and obj.type == "ARMATURE"
        ]
        if not armatures:
            return None
        armature = max(armatures, key=lambda item: len(item.data.bones))
        result = (armature, _chains(armature), {
            chain.name: _points(armature, chain) for chain in _chains(armature)
        })
        return result
    except Exception:
        return None
    finally:
        for obj in [obj for obj in bpy.context.scene.objects if obj.name not in before_objects]:
            kind = obj.type
            data = obj.data if kind in ("MESH", "ARMATURE") else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and getattr(data, "users", 0) == 0:
                if kind == "MESH":
                    bpy.data.meshes.remove(data)
                else:
                    bpy.data.armatures.remove(data)
        for action in [action for action in bpy.data.actions if action.name not in before_actions]:
            bpy.data.actions.remove(action)


def _candidate_rank(path: Path, names: list[str]) -> tuple[int, int]:
    """Prefer the declared body over a clip when both describe the same tail."""
    return (1 if live.looks_like_body(path) else 0, len(names))


def _live_root(settings) -> Path:
    return core.project_root(settings) / "artifacts" / "tail-skeletons"


def _live_titles(settings) -> dict[str, str]:
    """Map the Source page's hero folder to its display title."""
    titles: dict[str, str] = {}
    try:
        from .properties import HERO_ITEMS
    except Exception:
        return titles
    for _slug, title, model in HERO_ITEMS:
        parts = Path(model or "").parts
        for index, part in enumerate(parts):
            if part.lower() in ("heroes_wip", "heroes_staging") and index + 1 < len(parts):
                titles.setdefault(parts[index + 1].lower(), title)
                break
    return titles


def _live_label(settings, path: Path, chain: tailscan.TailChain) -> str:
    root = _live_root(settings)
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    hero = ""
    rest: tuple[str, ...] = ()
    for index, part in enumerate(parts):
        if part.lower() in ("heroes_wip", "heroes_staging") and index + 2 < len(parts):
            hero = parts[index + 1]
            rest = parts[index + 2:-1]
            break
    title = _live_titles(settings).get(hero.lower(), hero or path.parent.name)
    rest = tuple(part for part in rest if part.lower() not in ("dmx", "mesh"))
    variant = " ".join(rest[:1])
    return f"{title}{(' ' + variant) if variant else ''} / {chain.name}"


def _add_live_skeletons(settings, files: list[Path]) -> int:
    """Add every live hero skeleton's tail chains without importing its mesh.

    The skeleton cache is produced by Source 2 Viewer from the live VPK, so this
    path covers heroes that were never extracted by hand.  Names are read from
    the DMX header; the chosen tile is imported only when the owner clicks it.
    """
    found = 0
    for path in files:
        names = tailscan.dmx_bone_names(path)
        for chain in tailscan.chains(names):
            label = _live_label(settings, path, chain)
            if any(option.label.lower() == label.lower() for option in settings.tail_options):
                continue
            _add_option(
                settings,
                label=label,
                source="LIVE",
                path=path,
                chain=chain,
                points=[(0.0, 0.0, 0.0), (0.0, 0.0, 0.2 + 0.05 * len(chain.bones))],
            )
            found += 1
    return found


def discover(settings, *, live_files: list[Path] | None = None) -> int:
    """Find tail skeletons in the hero, custom rig, sibling extracts and clips."""
    settings.tail_options.clear()
    settings.tail_option_index = 0
    found = 0

    hero = settings.target_armature
    if hero is not None and hero.type == "ARMATURE":
        for chain in _chains(hero):
            _add_option(
                settings,
                label=f"{hero.name} / {chain.name}",
                source="HERO",
                path=settings.body_dmx,
                chain=chain,
                points=_points(hero, chain),
                armature=None,
            )
            found += 1

    custom = settings.custom_armature
    if custom is not None and custom.type == "ARMATURE" and custom != hero:
        for chain in _chains(custom):
            _add_option(
                settings,
                label=f"{custom.name} / {chain.name}",
                source="CUSTOM",
                path="",
                chain=chain,
                points=_points(custom, chain),
                armature=custom,
            )
            found += 1

    live_files = live_files if live_files is not None else live.tail_skeleton_files(_live_root(settings))
    live_found = _add_live_skeletons(settings, live_files) if live_files else 0
    found += live_found

    scanned = 0
    imported = 0
    for root in _candidate_roots(settings):
        best: dict[str, tuple[Path, list[str]]] = {}
        for path in root.rglob("*.dmx"):
            if path.name.startswith("_."):
                continue
            names = tailscan.dmx_bone_names(path)
            if len(names) < 2:
                continue
            key = _hero_key(root, path)
            if key not in best or _candidate_rank(path, names) > _candidate_rank(*best[key]):
                best[key] = (path, names)
        for key, (path, names) in sorted(best.items()):
            scanned += 1
            loaded = _import_candidate(path)
            if loaded is None:
                # The names still describe a real tail; draw the tile from the
                # names alone so a failed import is visible rather than silent.
                for chain in tailscan.chains(names):
                    _add_option(
                        settings,
                        label=f"{key} / {chain.name}",
                        source="CLIP",
                        path=path,
                        chain=chain,
                        points=[(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)],
                    )
                    found += 1
                continue
            armature, chains, points = loaded
            imported += 1
            for chain in chains:
                _add_option(
                    settings,
                    label=f"{key} / {chain.name}",
                    source="BODY" if live.looks_like_body(path) else "CLIP",
                    path=path,
                    chain=chain,
                    points=points.get(chain.name, []),
                )
                found += 1

    settings.tail_option_index = 0
    found = len(settings.tail_options)
    roots = len(_candidate_roots(settings))
    settings.tail_option_note = (
        f"{found} tail chain(s): {live_found} from the live roster, {imported}/{scanned} "
        f"extracted skeletons opened across {roots} folder(s)"
    )
    return found


def start_discover(settings) -> str:
    """Start a tail scan without running S2V on the main thread.

    The live skeleton cache is the only expensive step, and it is a subprocess,
    so it runs through the existing background job.  The scan itself is scheduled
    as a timer after it returns.  A cached roster is scanned immediately.
    """
    if jobs.is_running():
        raise RuntimeError("tail-scan-busy: another background job is already running")
    settings.tail_options.clear()
    settings.tail_option_index = 0
    settings.tail_option_note = "scanning tail sources"
    root = _live_root(settings)
    cached = live.tail_skeleton_files(root)
    try:
        env = core.detect_environment(settings, core.core(settings))
    except Exception:
        env = None
    if cached and (env is None or live.tail_skeleton_cache_fresh(env, root)):
        _schedule_scan(settings, cached)
        return f"Scanning {len(cached)} cached live hero skeletons"
    if env is not None and env.s2v is not None and env.vpk is not None:
        def work(progress):
            progress(0.1, "decompiling live hero skeletons")
            return live.extract_tail_skeletons(env, root)

        def done(files):
            settings.tail_option_note = f"reading {len(files)} live hero skeletons"
            _schedule_scan(settings, files)

        def failed(error):
            settings.tail_option_note = f"live skeleton scan failed: {error}"
            _schedule_scan(settings, [])

        message = jobs.start(settings, "Scanning live heroes for tails", work, done, failed)
        if message:
            raise RuntimeError(message)
        return "Decompiling all live hero skeletons; the viewport stays responsive"
    _schedule_scan(settings, [])
    return "Scanning extracted folders only; set the live game and S2V to include every hero"


def _schedule_scan(settings, files: list[Path]) -> None:
    def run():
        try:
            count = discover(settings, live_files=files)
            settings.tail_option_note = settings.tail_option_note or f"{count} tail chains"
        except Exception as error:
            settings.tail_option_note = f"Tail scan failed: {error}"
        return None
    bpy.app.timers.register(run, first_interval=0.05)


def load_option(settings, index: int) -> str:
    """Load the chosen tile as the tail armature and map the hero channels."""
    if not settings.tail_options:
        raise RuntimeError("tail-options-empty: scan for tails first")
    option = settings.tail_options[max(0, min(index, len(settings.tail_options) - 1))]
    if option.rig is not None:
        settings.tail_armature = option.rig
    elif option.source == "HERO" and settings.target_armature is not None:
        source = settings.target_armature
        rig = bpy.data.objects.new(f"DMF Tail {option.chain}", source.data.copy())
        bpy.context.scene.collection.objects.link(rig)
        option.rig = rig
        settings.tail_armature = rig
    elif option.source == "CUSTOM":
        settings.tail_armature = settings.custom_armature
    else:
        path = Path(bpy.path.abspath(option.path)) if option.path else None
        if path is None or not path.is_file():
            raise RuntimeError(f"tail-source-missing: {option.path}")
        before = {obj.name for obj in bpy.context.scene.objects}
        source2.import_dmx(path, append="NEW_ARMATURE")
        armatures = [
            obj for obj in bpy.context.scene.objects
            if obj.name not in before and obj.type == "ARMATURE"
        ]
        if not armatures:
            raise RuntimeError(f"tail-import-empty: {path.name} produced no armature")
        rig = max(armatures, key=lambda item: len(item.data.bones))
        for obj in [obj for obj in bpy.context.scene.objects if obj.name not in before]:
            if obj.type == "MESH":
                bpy.data.objects.remove(obj, do_unlink=True)
        rig.name = f"DMF Tail {option.chain}"
        option.rig = rig
        settings.tail_armature = rig
    if settings.tail_armature is None:
        raise RuntimeError("tail-no-rig: the chosen tail has no armature")
    if settings.target_armature is None:
        settings.tail_note = f"{option.label}: tail rig loaded; import the hero to map channels"
        return settings.tail_note
    count = scan(settings)
    return f"{option.label}: {count} hero channels on {settings.tail_armature.name}"


def preview(settings) -> None:
    armature = settings.tail_armature
    if armature is None:
        return
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    armature.hide_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    if bpy.context.area is not None and bpy.context.area.type == "VIEW_3D":
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
        except Exception:
            pass


def _pairs(settings) -> list[tuple[str, str]]:
    hero, tail = _rigs(settings)
    rows = []
    for row in settings.tail_bones:
        if not row.source or not row.target:
            continue
        if hero.data.bones.get(row.source) is None or tail.data.bones.get(row.target) is None:
            row.state = "MISSING"
            continue
        rows.append((row.source, row.target))
    return rows


def _blend_matrix(matrix: Matrix, weight: float) -> Matrix:
    if weight >= 1.0:
        return matrix.copy()
    location, rotation, scale = matrix.decompose()
    location = location * weight
    rotation = rotation.__class__((1.0, 0.0, 0.0, 0.0)).slerp(rotation, weight)
    scale = (1.0 + (scale.x - 1.0) * weight, 1.0 + (scale.y - 1.0) * weight, 1.0 + (scale.z - 1.0) * weight)
    return Matrix.LocRotScale(location, rotation, scale)


def _clear_action(action) -> None:
    """Remove old tail curves from a layered Blender 5.4 action."""
    for layer in list(getattr(action, "layers", [])):
        for strip in list(getattr(layer, "strips", [])):
            for bag in list(getattr(strip, "channelbags", [])):
                for curve in list(getattr(bag, "fcurves", [])):
                    bag.fcurves.remove(curve)


def blend(settings, row) -> dict:
    """Write one imported hero clip onto the tail armature as a new action."""
    hero, tail = _rigs(settings)
    pairs = _pairs(settings)
    if not pairs:
        raise RuntimeError("tail-no-pairs: pair at least one hero tail bone with a tail bone")
    source_action = None
    if row is not None:
        source_action = bpy.data.actions.get(row.action) if row.action else None
    if source_action is None:
        source_action = hero.animation_data.action if hero.animation_data else None
    if source_action is None:
        raise RuntimeError("tail-no-action: import a hero clip before blending it")
    start, end = (int(round(value)) for value in source_action.frame_range)
    if end <= start:
        raise RuntimeError("tail-empty-range: the hero action has no frame range")

    data = tail.animation_data or tail.animation_data_create()
    name = (row.label if row is not None else source_action.name) + "_tail"
    target_action = bpy.data.actions.get(name)
    if target_action is None:
        target_action = bpy.data.actions.new(name)
    else:
        _clear_action(target_action)
    data.action = target_action
    if hasattr(data, "action_slot") and getattr(target_action, "slots", None):
        data.action_slot = target_action.slots[0]

    scene = bpy.context.scene
    old_action = hero.animation_data.action if hero.animation_data else None
    old_frame = scene.frame_current
    try:
        if hero.animation_data is not None:
            hero.animation_data.action = source_action
            if hasattr(hero.animation_data, "action_slot") and getattr(source_action, "slots", None):
                hero.animation_data.action_slot = source_action.slots[0]
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            for source_name, target_name in pairs:
                source_bone = hero.pose.bones.get(source_name)
                target_bone = tail.pose.bones.get(target_name)
                if source_bone is None or target_bone is None:
                    continue
                target_bone.rotation_mode = source_bone.rotation_mode
                target_bone.matrix_basis = _blend_matrix(source_bone.matrix_basis.copy(), settings.tail_weight)
                target_bone.keyframe_insert("location", frame=frame, group=target_name)
                if target_bone.rotation_mode == "QUATERNION":
                    target_bone.keyframe_insert("rotation_quaternion", frame=frame, group=target_name)
                elif target_bone.rotation_mode == "AXIS_ANGLE":
                    target_bone.keyframe_insert("rotation_axis_angle", frame=frame, group=target_name)
                else:
                    target_bone.keyframe_insert("rotation_euler", frame=frame, group=target_name)
                target_bone.keyframe_insert("scale", frame=frame, group=target_name)
    finally:
        if hero.animation_data is not None:
            hero.animation_data.action = old_action
        scene.frame_set(old_frame)
    if row is not None:
        row.tail_action = target_action.name
    settings.tail_note = (
        f"{target_action.name}: {end - start + 1} frames from {source_action.name} onto "
        f"{tail.name} ({len(pairs)} bones, blend {settings.tail_weight:.2f})"
    )
    return {
        "action": target_action.name,
        "frames": end - start + 1,
        "bones": len(pairs),
        "tail": tail.name,
    }


class DMF_OT_scan_tails(Operator):
    bl_idname = "dmf.scan_tails"
    bl_label = "Scan Tail Sources"
    bl_description = "Find tail chains on this hero, the custom rig, sibling extractions and AG1/AG2 clips"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            message = start_discover(settings)
        except Exception as error:
            self.report({"ERROR"}, f"Tail scan failed: {error}")
            settings.tail_option_note = f"Tail scan failed: {error}"
            return {"CANCELLED"}
        self.report({"INFO"}, message)
        return {"FINISHED"}


class DMF_OT_load_tail_option(Operator):
    bl_idname = "dmf.load_tail_option"
    bl_label = "Use Tail"
    bl_description = "Load this tail skeleton as the tail rig and pair its channels"

    index: bpy.props.IntProperty(name="Tail", default=-1)

    def execute(self, context):
        settings = context.scene.dmf
        if self.index >= 0:
            settings.tail_option_index = min(self.index, len(settings.tail_options) - 1)
        try:
            message = load_option(settings, settings.tail_option_index)
        except Exception as error:
            self.report({"ERROR"}, f"Tail load failed: {error}")
            settings.tail_note = f"Tail load failed: {error}"
            return {"CANCELLED"}
        self.report({"INFO"}, message)
        return {"FINISHED"}


class DMF_OT_preview_tail(Operator):
    bl_idname = "dmf.preview_tail"
    bl_label = "Frame Tail"
    bl_description = "Select and frame the chosen tail rig in the 3D view"

    def execute(self, context):
        preview(context.scene.dmf)
        return {"FINISHED"}


class DMF_OT_scan_tail(Operator):
    bl_idname = "dmf.scan_tail"
    bl_label = "Find Tail Bones"
    bl_description = "Pair the hero's tail channels with bones on the selected tail armature (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        try:
            count = scan(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, settings.tail_note or f"{count} tail channels", "OK" if count else "WARN")
        return {"FINISHED"}


class DMF_OT_blend_tail(Operator):
    bl_idname = "dmf.blend_tail"
    bl_label = "Blend Tail"
    bl_description = "Write the selected hero clip's tail channels onto the tail armature (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        row = settings.clips[settings.clip_index] if settings.clips else None
        try:
            result = blend(settings, row)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        core.set_status(settings, settings.tail_note, "OK")
        self.report({"INFO"}, f"Wrote {result['frames']} frames onto {result['tail']}")
        return {"FINISHED"}


class DMF_OT_blend_tail_all(Operator):
    bl_idname = "dmf.blend_tail_all"
    bl_label = "Blend All Tails"
    bl_description = "Write every imported hero clip's tail channels onto the tail armature (experimental)"

    def execute(self, context):
        settings = context.scene.dmf
        rows = [row for row in settings.clips if row.action and row.state in ("IMPORTED", "WRITTEN")]
        if not rows:
            core.set_status(settings, "Import a clip before blending tails", "WARN")
            return {"CANCELLED"}
        failed = 0
        written = 0
        for row in rows:
            try:
                blend(settings, row)
                written += 1
            except Exception as error:
                failed += 1
                settings.tail_note = f"{row.label}: {error}"
        core.set_status(
            settings,
            f"Wrote tail actions for {written} clips" + (f"; {failed} failed" if failed else ""),
            "OK" if not failed else "WARN",
        )
        return {"FINISHED"}


CLASSES = (
    DMF_OT_scan_tails,
    DMF_OT_load_tail_option,
    DMF_OT_preview_tail,
    DMF_OT_scan_tail,
    DMF_OT_blend_tail,
    DMF_OT_blend_tail_all,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)