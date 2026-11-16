"""Refuse a tail port whose shipped skeleton cannot render the shipped model.

The Haze release failed four times in the same way, and each failure was visible
in the sources before anything was packed:

* the game logged ``Couldn't find bone (weaponHand_L) in skeleton ... while
  serializing bone mask`` -- a mask naming a bone the shipped skeleton does not
  have;
* the tail was invisible -- the shipped skeleton had tail joints the model's own
  mesh skeleton did not, so nothing skinned to them;
* head and arms rotated -- the shared joints of the shipped skeleton and the
  model's mesh skeleton were not in the same order.

This gate reads the three sources a port ships (the model vmdl, the skeleton
document and the DMX each of them names) and refuses rather than packing.  It
exists so the code path that produced those paks cannot be run again.

  blender -b --python tools/tail_release_gate.py -- \
      --addon-content <csdk>/content/citadel_addons/<addon> \
      --report artifacts/receipts/<hero>-gate.json

Exit 0 admits the port.  Exit 2 refuses it and names the check that refused.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PULSE_DIR = Path("<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


class Refused(RuntimeError):
    """A check that must stop the port."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    try:
        from pulse_src_ops import datamodel  # noqa: WPS433
    except Exception as error:  # pragma: no cover - environment guard
        raise Refused("gate-needs-blender", f"PulseSrcOps datamodel unavailable: {error}") from error
    return datamodel


def _arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-content", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--clips", default="", help="clip DMX folder; defaults to <model folder>/clips")
    parser.add_argument("--bodies", default="", help="the game's own body DMX per clip, for the rebake check")
    parser.add_argument(
        "--game-skeleton",
        default="",
        help="the game's own skeleton DMX (what <hero>.vnmskel names in pak01): every shared joint must keep its parent",
    )
    parser.add_argument(
        "--game-model",
        default="",
        help="the game's own mesh DMX: the shipped model's bind must not move, because a rest in a mesh document is its skinning bind",
    )
    return parser.parse_args(argv)


def _joint_names(datamodel, path: Path) -> list[str]:
    model = datamodel.load(str(path))
    skeleton = model.root["skeleton"]
    joints = skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]
    return [joint.name for joint in joints]


def _joint_table(datamodel, path: Path) -> dict[str, dict]:
    """Joint name -> parent/rest, using the audit's element walker.

    Reading `joint["parent"]` returns nothing on this DMX flavour; the audit tool
    walks the element tree instead and that is the only reader that has ever
    produced real parents.
    """
    tools = Path(__file__).resolve().parent
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from tail_release_audit import _joint_table as walk  # noqa: WPS433

    return walk(datamodel, str(path))


def _roots_and_reachability(datamodel, path: Path) -> tuple[list[str], set[str], dict[str, str]]:
    """The skeleton's roots and every joint reachable from them.

    A joint appended to the joint array without being attached under a parent is a
    second root.  The compiler leaves it out of the bone table, the client logs
    "Couldn't find bone (...) while serializing bone mask" for any mask naming it,
    and then crashes -- the exact failure this gate exists to prevent.
    """
    table = _joint_table(datamodel, path)
    parents = {
        name: (row.get("parent") or None)
        for name, row in table.items()
        if name != "__order__"  # the audit's own ordering pseudo-entry
    }
    children: dict[str, list[str]] = {name: [] for name in parents}
    for name, parent in parents.items():
        if parent in children:
            children[parent].append(name)
    roots = [name for name, parent in parents.items() if not parent]
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(children.get(name, []))
    return roots, seen, parents


def _parents(datamodel, path: Path) -> dict[str, str]:
    model = datamodel.load(str(path))
    skeleton = model.root["skeleton"]
    joints = skeleton["jointList"] if "jointList" in skeleton else skeleton["children"]
    found: dict[str, str] = {}
    for joint in joints:
        parent = ""
        for key in ("parent", "parentName"):
            try:
                value = joint[key]
            except Exception:
                continue
            parent = value if isinstance(value, str) else getattr(value, "name", "") or ""
            break
        found[joint.name] = parent
    return found


def _model_mesh_dmx(root: Path, vmdl: Path) -> Path:
    """The first RenderMeshFile of the model, which carries the model skeleton."""
    entries = _render_meshes(root, vmdl)
    preferred = [path for name, path in entries if name in {"body", "Body"}] or [entries[0][1]]
    return preferred[0]


def _render_meshes(root: Path, vmdl: Path) -> list[tuple[str, Path]]:
    """Every RenderMeshFile, because the model skeleton is the union of them.

    The pinned Shiv build renders the tail from its own mesh dmx (`shiv_tail15.dmx`)
    beside the body, so the tail joints reach the model through that file rather
    than through `shiv_body.dmx`.  Reading only `body` made the gate refuse a build
    that is shaped exactly like the pinned one.
    """
    text = vmdl.read_text(encoding="utf-8", errors="replace")
    entries = re.findall(r'_class = "RenderMeshFile"\s*\n\s*name = "([^"]+)"\s*\n\s*filename = "([^"]+)"', text)
    if not entries:
        raise Refused("model-no-render-mesh", f"{vmdl.name} declares no RenderMeshFile")
    resolved: list[tuple[str, Path]] = []
    missing: list[str] = []
    for name, declared in entries:
        path = root / declared
        if path.is_file():
            resolved.append((name, path))
        else:
            missing.append(declared)
    if not resolved:
        raise Refused("model-mesh-missing", f"none of {vmdl.name}'s meshes are in the addon: {missing[:4]}")
    return resolved


def _skeleton_dmx(root: Path, document: Path) -> Path:
    text = document.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'm_sourceFilename = "([^"]+)"', text)
    if not match:
        raise Refused("skeleton-no-source", f"{document.name} declares no m_sourceFilename")
    declared = match.group(1)
    seen = []
    for candidate in (root / declared, root / "models" / "heroes_staging" / declared):
        seen.append(candidate)
        if candidate.is_file():
            return candidate
    raise Refused("skeleton-source-missing", f"{declared} is not in the addon (looked in {[str(p) for p in seen]})")


def _mask_bones(document: Path) -> list[str]:
    text = document.read_text(encoding="utf-8", errors="replace")
    names: list[str] = []
    for block in re.finditer(r'm_ID = "([^"]+)"', text):
        tail = text[block.end() : text.find("\n\t\t},", block.end()) if text.find("\n\t\t},", block.end()) > 0 else len(text)]
        ids = re.search(r"m_boneIDs = \s*\[(.*?)\]", tail, re.S)
        if ids:
            names.extend(re.findall(r'"([^"]+)"', ids.group(1)))
    return names


def _subsequence(small: list[str], large: list[str]) -> list[str]:
    """Names of `small` that appear in `large` in a different relative order."""
    position = {name: index for index, name in enumerate(large)}
    order = [position[name] for name in small if name in position]
    return [small[index] for index in range(1, len(order)) if order[index] < order[index - 1]]


def _joint_world(datamodel, path, name: str):
    """The named joint's pose through its parent chain, as a 4x4 matrix."""
    return _joint_world_map(datamodel, path).get(name)


def _joint_world_map(datamodel, path) -> dict[str, list[list[float]]]:
    """Every joint's pose through its own parent chain, one load per document."""
    from mathutils import Matrix, Quaternion, Vector  # noqa: WPS433

    root = datamodel.load(str(path)).root
    element = root["model"] if "model" in root.keys() else root
    while "children" not in element.keys():
        element = next(element[key] for key in element.keys() if hasattr(element[key], "keys"))

    by_name = {}
    parents = {}

    def walk(node, parent):
        for child in node["children"]:
            by_name[child.name] = child
            parents[child.name] = parent
            walk(child, child.name)

    walk(element, None)
    local = {}
    for joint, element_row in by_name.items():
        transform = element_row["transform"]
        position = Vector(list(transform["position"]))
        q = list(transform["orientation"])
        local[joint] = Matrix.Translation(position) @ Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4()

    worlds: dict[str, list[list[float]]] = {}
    raw: dict[str, object] = {}

    def resolve(name):
        if name in raw:
            return raw[name]
        parent = parents.get(name)
        raw[name] = (resolve(parent) if parent else Matrix.Identity(4)) @ local[name]
        return raw[name]

    for joint in by_name:
        worlds[joint] = [list(row) for row in resolve(joint)]
    return worlds


def _joint_rests(datamodel, path) -> dict[str, tuple]:
    """Each joint's local rest (position, quaternion) from a document."""
    root = datamodel.load(str(path)).root
    element = root["model"] if "model" in root.keys() else root
    while "children" not in element.keys():
        candidates = [key for key in element.keys() if getattr(element[key], "keys", None)]
        if not candidates:
            return {}
        element = element[candidates[0]]
    rests: dict[str, tuple] = {}

    def walk(node):
        for child in node["children"]:
            transform = child["transform"] if "transform" in child.keys() else None
            if transform is not None:
                rests[child.name] = _rest_tuple(transform)
            walk(child)

    walk(element)
    return rests


def _rest_of(datamodel, path, name):
    return _joint_rests(datamodel, path).get(name)


def _rest_tuple(transform) -> tuple:
    values = []
    for key in ("position", "orientation"):
        value = transform[key]
        if len(value) == 1:
            value = value[0]
        values.append(tuple(float(component) for component in value))
    return tuple(values)


def _rests_match(ours: tuple, theirs: tuple) -> bool:
    a_pos, a_rot = ours
    b_pos, b_rot = theirs
    if max(abs(a - b) for a, b in zip(a_pos, b_pos)) > 1e-3:
        return False
    dot = abs(sum(a * b for a, b in zip(a_rot, b_rot)))
    return abs(dot - 1.0) < 1e-3


def _joint_tree_parents(datamodel, path) -> dict[str, str | None]:
    """Every joint's parent from a document's own tree walk."""
    root = datamodel.load(str(path)).root
    element = root["model"] if "model" in root.keys() else root
    while "children" not in element.keys():
        candidates = [key for key in element.keys() if hasattr(element[key], "keys")]
        if not candidates:
            return {}
        element = element[candidates[0]]
    parents: dict[str, str | None] = {}

    def walk(node, up):
        for child in node["children"]:
            parents[child.name] = up
            walk(child, child.name)

    walk(element, None)
    return parents


def _tail_names() -> set[str]:
    return {f"tail_{index}" for index in range(0, 8)} | {"tail_end"}


def _model_bone_parents(path) -> dict[str, str | None]:
    """Each bone's parent in a vmdl's `Skeleton` section, as the document nests it."""
    import sys  # noqa: WPS433

    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    from forge import modeldoc  # noqa: WPS433

    return modeldoc.skeleton_parent_map(Path(path).read_text(encoding="utf-8", errors="replace"))


def _joint_tree_order(datamodel, path) -> list[str]:
    """The skeleton's joints in the order a depth-first walk of its tree reaches them."""
    root = datamodel.load(str(path)).root
    element = root["model"] if "model" in root.keys() else root
    while "children" not in element.keys():
        candidates = [key for key in element.keys() if hasattr(element[key], "keys")]
        if not candidates:
            return []
        element = element[candidates[0]]
    out: list[str] = []

    def walk(node):
        for child in node["children"]:
            out.append(child.name)
            walk(child)

    walk(element)
    return out


def _joint_list_order(datamodel, path) -> list[str]:
    """The skeleton's explicit joint order, which is what numeric bone ids index."""
    root = datamodel.load(str(path)).root
    # `model` first: a skeleton document can carry a second `jointList` on a sibling element
    # that the model does not bind against, and reading whichever key comes first made a
    # correct file look shifted by one slot.
    for key in ("model", "skeleton"):
        if key in root.keys():
            child = root[key]
            if hasattr(child, "keys") and "jointList" in child.keys():
                return [joint.name for joint in child["jointList"]]
    if "jointList" in root.keys():
        return [joint.name for joint in root["jointList"]]
    for key in root.keys():
        child = root[key]
        if hasattr(child, "keys") and "jointList" in child.keys():
            return [joint.name for joint in child["jointList"]]
    raise Refused("skeleton-has-no-jointlist", f"{Path(path).name} declares no jointList")


def _tail_chain(joints: list[str]) -> list[str]:
    chain = [name for name in joints if re.fullmatch(r"tail_\d+", name)]
    return chain + [name for name in joints if name == "tail_end"]


def _channel_values_equal(datamodel, left: Path, right: Path) -> bool:
    """True when both documents carry byte-identical channel sample values."""
    def samples(path: Path) -> dict:
        root = datamodel.load(str(path)).root
        try:
            clip = root["animationList"]["animations"][0]
        except Exception:  # noqa: BLE001 - a document without channels is not a clip
            return {}
        out = {}
        for channel in clip["channels"]:
            element = channel.get("toElement")
            key = (getattr(element, "name", ""), str(channel.get("toAttribute", "")))
            for layer in channel["log"]["layers"]:
                values = tuple(tuple(round(float(v), 6) for v in value) if isinstance(value, (list, tuple)) else round(float(value), 6) for value in layer["values"])
                out[key] = out.get(key, ()) + (values,)
        return out

    left_samples, right_samples = samples(left), samples(right)
    shared = set(left_samples) & set(right_samples)
    # Only the channels both documents carry can be compared: the merge adds
    # tail channels, and a whole-dict comparison would call every clip different
    # and never refuse the one that matters.
    return bool(shared) and all(left_samples[key] == right_samples[key] for key in shared)


def _mesh_names(datamodel, path: Path) -> list[str]:
    """Mesh element names in a document (empty for a skeleton document)."""
    table = _joint_table(datamodel, path)
    del table  # the walk below is the measurement; _joint_table proves the file loads
    root = datamodel.load(str(path)).root
    names: list[str] = []

    def visit(element) -> None:
        for child in element["children"] if "children" in element.keys() else []:
            if getattr(child, "type", "").startswith("DmeMesh"):
                names.append(child.name)
            visit(child)

    visit(root["skeleton"] if "skeleton" in root.keys() else root)
    return names


_TAIL_NAMES = _tail_names()


def run(root: Path, clips: str = "", bodies: str = "", game_skeleton: str = "", game_model: str = "") -> dict:
    datamodel = _datamodel()
    vmdl = next(iter(sorted(root.rglob("*.vmdl"))), None)
    if vmdl is None:
        raise Refused("model-missing", f"no .vmdl in {root}")
    document = next(iter(sorted(root.rglob("*.vnmskel"))), None)
    model_dmx = _model_mesh_dmx(root, vmdl)
    # One reading, both sides.  `_joint_names` walks the flat `jointList` while `_joint_table`
    # walks the children tree: on the same document they disagree (the model document's
    # `head_end` is slot 16 by tree and slot 38 by list), and comparing one against the other
    # reported `joint-order-diverges` on joints nobody had touched.  The client binds the tree a
    # model document declares, so the tree order is the measurement on both sides.
    model_joints = list(dict.fromkeys(_joint_table(datamodel, model_dmx)["__order__"]["order"]))
    for name, mesh in _render_meshes(root, vmdl):
        if mesh == model_dmx:
            continue
        for joint in list(dict.fromkeys(_joint_table(datamodel, mesh)["__order__"]["order"])):
            if joint not in model_joints:
                model_joints.append(joint)

    report: dict = {
        "addon_content": str(root),
        "model": str(vmdl),
        "model_mesh_dmx": str(model_dmx),
        "model_joints": len(model_joints),
    }

    if document is None:
        # No shipped skeleton: the game keeps its own, so only the model's own
        # tail has to exist.  This is the admitted state of the visible build.
        chain = _tail_chain(model_joints)
        if len(chain) < 3:
            raise Refused(
                "model-has-no-tail",
                f"{model_dmx.name} carries {len(chain)} tail joints; the tail mesh would render with nothing to move it",
            )
        report.update({"skeleton": None, "tail_chain": chain, "admitted": True})
        return report

    clip_dir = Path(clips) if clips else ((vmdl.parent / "clips") if (vmdl.parent / "clips").is_dir() else None)
    skeleton_dmx = _skeleton_dmx(root, document)
    # Count the joints the way the clip side is counted: unique names, in file
    # order.  `_joint_names` counts elements, and a mesh export can declare the same
    # joint more than once (this hero's export: 167 elements for 131 bones), so the
    # two sides of the comparison must share one measurement or the refusal is noise.
    skeleton_order = _joint_table(datamodel, skeleton_dmx)["__order__"]["order"]
    skeleton_joints = list(dict.fromkeys(skeleton_order))
    skeleton_duplicates = len(skeleton_order) - len(skeleton_joints)
    report.update({"skeleton": str(document), "skeleton_dmx": str(skeleton_dmx), "skeleton_joints": len(skeleton_joints),

        "skeleton_duplicate_elements": skeleton_duplicates})

    # 1. A mask must not name a bone the skeleton cannot resolve.  The client logs
    #    "Couldn't find bone ... while serializing bone mask" and then crashes.
    roots, reachable, parents = _roots_and_reachability(datamodel, skeleton_dmx)
    # The mesh skeleton legitimately has several roots (root_motion, the IK targets
    # and pelvis as the extraction writes them).  What must not happen is the
    # shipped skeleton inventing a root of its own: an appended joint with no parent
    # is dropped by the compiler and crashes the client through its mask.
    model_roots, _, _ = _roots_and_reachability(datamodel, model_dmx)
    # A root appended AFTER every game joint is the sanctioned placement and the pinned Shiv build
    # does exactly that with its tail: the client numbers by slot, so extras may only take slots
    # past the game's last one.  A root inserted *among* the game joints is the defect this refusal
    # exists for — it moves every index after it, which is what rotated the head, arms and tail.
    slots = {name: index for index, name in enumerate(skeleton_joints)}
    game_slots = (
        {
            name: index
            for index, name in enumerate(
                _joint_list_order(datamodel, game_skeleton)
                if game_skeleton and Path(game_skeleton).is_file()
                else []
            )
        }
        if game_skeleton and Path(game_skeleton).is_file()
        else {}
    )
    last_game_slot = max(game_slots.values()) if game_slots else -1
    invented = [
        name
        for name in roots
        if name not in set(model_roots) and slots.get(name, last_game_slot + 1) <= last_game_slot
    ]
    if invented:
        raise Refused(
            "skeleton-invented-root",
            f"{skeleton_dmx.name} adds root joints {invented} that {model_dmx.name} does not have; "
            "a joint with no parent among the game joints is dropped or moves every index after it, "
            "and every mask naming one crashes the client",
        )
    unreachable = [name for name in skeleton_joints if name not in reachable]
    # Only an unreachable joint that a mask names is fatal: the client resolves the
    # mask, fails to find the bone and crashes.  The extraction's own mesh dmx keeps
    # its armature object joint unreferenced, and that has always been harmless.
    masked_unreachable = sorted({name for name in _mask_bones(document) if name in set(unreachable)})
    if masked_unreachable:
        raise Refused(
            "mask-bone-unreachable",
            f"{masked_unreachable} hang off nothing in {skeleton_dmx.name} (compiler drops them) and are named by masks; "
            "the client logs \"Couldn't find bone ... while serializing bone mask\" and crashes",
        )
    report["skeleton_roots"] = roots
    unknown = [name for name in _mask_bones(document) if name not in reachable]
    if unknown:
        raise Refused(
            "mask-names-missing-bone",
            f"{len(unknown)} mask entries name bones the compiled skeleton cannot resolve: {sorted(set(unknown))}",
        )

    # 2. The tail has to exist on both sides: the skeleton animates it, the model
    #    skins it.  Either alone is the invisible-tail failure.
    if skeleton_duplicates:
        raise Refused(
            "skeleton-duplicate-joints",
            f"{skeleton_dmx.name} declares {len(skeleton_order)} joint elements for {len(skeleton_joints)} bones; "
            "a joint declared twice is written twice by the compiler and the mask and clip bind by index into it",
        )
    skeleton_tail = _tail_chain(skeleton_joints)
    if len(skeleton_tail) < 3:
        raise Refused("skeleton-has-no-tail", f"{skeleton_dmx.name} carries {skeleton_tail} as a tail chain")

    # 2b. The tail must be a chain in the *skeleton*, not just present as names.  The
    #     Haze pak of 2026-11-15 shipped tail_0..tail_7 and tail_end all parented
    #     straight to pelvis: no chain, nothing to swing, the tail lies down.  The
    #     clip-side chain check cannot see this because the clips inherit the
    #     document's parents.
    flat = []
    for index, name in enumerate(skeleton_tail):
        want = skeleton_tail[index - 1] if index else None
        have = parents.get(name)
        if index == 0:
            if have in set(skeleton_tail[1:]):
                flat.append((name, have, "a non-tail bone"))
        elif have != want:
            flat.append((name, have, want))
    if flat:
        raise Refused(
            "skeleton-tail-chain-flat",
            f"{skeleton_dmx.name} does not parent the tail as a chain: {flat[:4]}; "
            "a flat chain has no joint to swing and the tail lies on the ground",
        )

    # 2c. Measured against the game's own skeleton.  `pelvis` under `root_motion` is
    #     what the body's authored curves expect; `weaponHand_L/R` under
    #     `arm_L_IKTARGET`/`arm_R_IKTARGET` is where the game puts the hand props.
    #     Parenting either somewhere else reads the same values in another frame: the
    #     2026-11-15 Haze pak had pelvis as a root and weaponHand under hand_L/hand_R
    #     and shipped a body wrong below the pelvis with the head and arms rotated.
    # 2d. The bind must not move. A rest in a mesh document is the position the mesh
    #     was skinned to, so it is comparable only with the game's own mesh document.
    #     Copying the skeleton document's rest into the model (76 joints, pelvis by
    #     54 units / 60 deg) shredded the body in game — same-kind comparison only.
    game_model = Path(game_model) if game_model else None
    if game_model is not None and game_model.is_file():
        shipped_bind = _joint_table(datamodel, model_dmx)
        stock_bind = _joint_table(datamodel, game_model)
        moved = []
        for name in stock_bind["__order__"]["order"]:
            here, there = shipped_bind.get(name), stock_bind.get(name)
            if not here or not there:
                continue
            delta = max(abs(a - b) for a, b in zip(here["head"], there["head"]))
            dot = abs(sum(a * b for a, b in zip(here["orientation"], there["orientation"])))
            if delta > 0.01 or (1.0 - dot) > 2e-3:
                moved.append((name, round(delta, 4)))
        if moved:
            raise Refused(
                "model-rest-differs-from-game-model",
                f"{len(moved)} joints bind the mesh away from {game_model.name} (e.g. {moved[:3]}); "
                "a rest in a mesh document is where the mesh was skinned, so the body deforms",
            )

    # 2c-1. The document the .vnmskel names must be a skeleton document, not the model.
    #      The 2026-11-15 15:18 pak pointed `haze.vnmskel` at the mesh+skeleton document
    #      (`haze_model_tail.dmx`), whose pelvis rest sits in the body's own frame: the
    #      game's skeleton document has that pelvis 90 deg the other way, so every joint
    #      was read in the wrong frame and the body lay on the floor while the mesh and
    #      the clips each looked right on their own.  A skeleton document carries joints;
    #      a model document carries DmeMesh children.
    game_skeleton = Path(game_skeleton) if game_skeleton else None
    skeleton_meshes = _mesh_names(datamodel, skeleton_dmx)
    if skeleton_meshes:
        raise Refused(
            "skeleton-document-carries-meshes",
            f"{skeleton_dmx.name} is a model document ({len(skeleton_meshes)} meshes: {skeleton_meshes[:3]}), not a skeleton; "
            "the game's own skeleton is a separate document with its own joint frame, and naming a model here binds every clip in the model's frame",
        )
    # 2c-2. A bundled skeleton must describe the SAME joints, in the same slots, as the
    #      model document that binds the meshes, and in the same frames.  Two shipped
    #      failures bracket this:
    #        * the game's own `haze_skel.dmx` carries `pelvis` in a frame 90 deg from the
    #          model's (head [0, 53.9, -0.48] identity vs [-0.48, 0, 53.9] rotated) and
    #          inserts `weaponHand_L/R` where the meshes have `attachWorld`; shipping it as
    #          our skeleton rotated the head and arms and, with the model's list re-synced
    #          to it, tore the body into flat wedges (2026-11-15 15:18 and 15:36 builds);
    #        * the reference build the owner accepted (01:23 pak, visible tail and cloth
    #          chain, no tail motion) ships NO skeleton at all and lets the game keep its
    #          own rig, which is why it was coherent everywhere.
    #      Neither is a preference: the client binds a mesh by index into the model's list.
    # An object-like joint is the armature object the extraction writes beside the bones
    # ("haze_body", "DMF Tail"); the client does not bind it.
    object_like = lambda name: " " in name or name.startswith("DMF ")  # noqa: E731
    shipped_table = _joint_table(datamodel, skeleton_dmx)
    model_table = _joint_table(datamodel, model_dmx)
    shipped_order = [name for name in shipped_table["__order__"]["order"] if not object_like(name)]
    model_view = [name for name in model_table["__order__"]["order"] if not object_like(name)]
    # Slot equality between a mesh and the skeleton is NOT the game's invariant, and this was
    # measured on 2026-11-16 before relaxing it: the game's own `haze_body.dmx` carries 120
    # joints with `weaponHand_L` around slot 50 while the game's own `haze_skel.dmx` carries it
    # at slot 6, and the shipped hero renders correctly.  A mesh's joint list is resolved by
    # NAME when the model compiles; what must hold is that every mesh joint exists in the
    # skeleton (below) and that the model's own `Skeleton` section covers the shipped
    # skeleton's slots (3b).  Keeping the old absolute equality also made a correct build
    # impossible: the game's skeleton is 98 joints and its body mesh is 120.
    # A joint the MESH carries and the animation skeleton does not is not a defect, and the game
    # proves it rather than this project: `haze_body.dmx` in pak01 is skinned to 120 joints while
    # the game's own `haze_skel.dmx` carries 98, because the bind is declared by the model's own
    # `Skeleton` section, not by the animation skeleton.  Appending those 24 leaves to our skeleton
    # to satisfy this check is what moved `head_end` to slot 17 and pushed `hand_L` 20 -> 21 and
    # `hand_R` 53 -> 61 in v15.  Coverage is enforced where the game enforces it: the model's
    # declared bones must cover the skeleton (3b, `model-vmdl-missing-skeleton-joint`) and every
    # mask name must resolve (`mask-names-missing-bone`).
    mesh_absent = [name for name in model_view if name not in set(shipped_order)]
    report["mesh_joints_absent_from_skeleton"] = len(mesh_absent)
    # The frames are compared in WORLD space, not joint-by-joint local ones, and that is measured:
    # our skeleton writes `pelvis` under `root_motion` while the model document writes it at the
    # root, and the two spellings have identical world transforms (both `[-0.482, 0, 53.909]` with
    # the same rotation).  Comparing the local decompositions reported one shifted joint on a
    # correct pair; what must agree is where each joint actually ends up, since that is what the
    # mesh vertices were bound to.
    shipped_world = _joint_world_map(datamodel, skeleton_dmx)
    model_world = _joint_world_map(datamodel, model_dmx)
    frame_shift = []
    leaf_shifts: list[tuple[str, float]] = []
    local_shift: list[tuple[str, float]] = []
    local_matched: list[str] = []
    model_only_shift: list[tuple[str, float]] = []
    model_only: set[str] = set()
    model_parents = _joint_tree_parents(datamodel, model_dmx)
    game_world: dict[str, object] = {}
    game_bones: dict[str, object] = {}
    if game_skeleton and Path(game_skeleton).is_file():
        game_bones = _joint_rests(datamodel, game_skeleton)
        game_world = _joint_world_map(datamodel, game_skeleton)
        model_only = {name for name in skeleton_joints if name not in game_bones}
        model_only = {name for name in model_only if name not in _TAIL_NAMES}
    report["rest_compared_to_game"] = len(game_world)
    for name in model_view:
        # The tail chain is exempt, and that is measured: the mesh document binds `tail_1..7` all
        # to `pelvis` (`PARENT-DIFF 7 of 128`, the skeleton chains them `tail_n <- tail_(n-1)`),
        # because the extraction writes the appended tail flat.  The chain is the authored one —
        # parenting the tail to `pelvis` is the shipped failure where it lay on the ground — so
        # its world poses cannot be compared document to document.
        if name in _TAIL_NAMES:
            continue
        # `*_end` leaves are model-only placeholders and their frame is measured, not required:
        # the game's own `haze.vmdl` puts `head_end` at 41.755 degrees from the pose the game's
        # own `haze_body.dmx` binds it at, and the game's own `haze_skel.dmx` does not carry the
        # leaf at all — so the game animates the 98 real joints and the leaves ride the model.
        # Requiring the two documents to agree about a leaf refused every build since v18.
        if re.search(r"_end(_[LR])?$", name):
            here_leaf, there_leaf = shipped_world.get(name), model_world.get(name)
            if here_leaf and there_leaf:
                leaf_shifts.append(
                    (
                        name,
                        round(
                            max(
                                abs(a - b)
                                for row_a, row_b in zip(here_leaf, there_leaf)
                                for a, b in zip(row_a, row_b)
                            ),
                            4,
                        ),
                    )
                )
            continue
        # The game's own skeleton is the authority for a joint it animates: its clips and the
        # hero's masks are written against that file, and the pinned Shiv build ships the same
        # shape.  The game's own *model* nests six IK helpers (`chestHier_OFFSET`,
        # `weaponHier_JNT`, `weaponHier_*_IKTARGET`) differently from the game's own skeleton, so
        # comparing those to the model measured the model's tree, not our skeleton.  A joint the
        # game animates is compared with the game's frame; a model-only bone (the `*_end` leaves,
        # the `*Hier_*` helpers the game skeleton does not carry) is compared with the model.
        # A joint whose parent differs between the two documents cannot be compared by world: the
        # game's own model nests `chestHier_OFFSET`/`weaponHier_*` under a helper chain while its
        # own mesh binds them elsewhere, so the world difference measured the tree.  A bone's
        # contract is its offset from its own parent, so those are compared as locals; a joint the
        # two documents agree about is still compared by world.
        if name == "pelvis" and not parents.get("pelvis"):
            # `pelvis` as a root is the shape that stands upright in game (v9, v25) and the game's
            # own skeleton spells the same pose with `pelvis` under `root_motion`; the two documents
            # put the same rotation in different places, so a world comparison here measures the
            # spelling, not the pose.  Refused instead: a pelvis under a *rotated* root, above.
            continue
        if name in game_bones:
            # A joint the game's own skeleton animates is decided by that file.
            here, there = shipped_world.get(name), game_world.get(name)
            if here and there:
                delta = max(
                    abs(a - b) for row_a, row_b in zip(here, there) for a, b in zip(row_a, row_b)
                )
                if delta > 0.01:
                    frame_shift.append((name, round(delta, 4)))
            continue
        if parents.get(name) != model_parents.get(name):
            here_local = _rest_of(datamodel, skeleton_dmx, name)
            there_local = _rest_of(datamodel, model_dmx, name)
            local_delta = 0.0
            if here_local and there_local:
                flat_here = [value for part in here_local for value in (part or ())]
                flat_there = [value for part in there_local for value in (part or ())]
                local_delta = max(
                    (abs(a - b) for a, b in zip(flat_here, flat_there)), default=0.0
                )
            if local_delta > 0.01:
                local_shift.append((name, round(local_delta, 4)))
            else:
                local_matched.append(name)
            continue
        here, there = shipped_world.get(name), model_world.get(name)
        if not here or not there:
            continue
        delta = max(abs(a - b) for row_a, row_b in zip(here, there) for a, b in zip(row_a, row_b))
        if delta > 0.01:
            # A model-only bone that the game's own skeleton does not animate is bound only by the
            # model's own bind pose: measured, the game's `haze_skel.dmx` carries none of the six
            # `*Hier_*` helpers, and the game's clips animate the 98 joints it does carry.  Their
            # frame is recorded rather than refused, exactly as the `*_end` leaves are, because a
            # render cannot be moved by a bone no clip poses and no skeleton slot numbers.
            if name not in game_bones:
                model_only_shift.append((name, round(delta, 4)))
                continue
            frame_shift.append((name, round(delta, 4)))
    # 2c-3. `pelvis` must not inherit a rotated root.  Measured on the 2026-11-16 v8 build: the
    #      skeleton was rebuilt in the game's list order and its hierarchy was taken from the
    #      game as well, which parented `pelvis` under `root_motion` — and the model's
    #      `root_motion` carries the authored 90 deg, so the body applied it twice and collapsed
    #      in on itself while the head, arms and tail were finally right.  AGENTS.md records the
    #      same failure from the 2026-11-15 pelvis re-parent; the gate did not refuse it then and
    #      no check covered it until now.
    # 2c-3a. The skeleton's tree and rests are recorded, not refused.
    #
    # Two rules lived here on 2026-11-16 and both were disproven by the pinned Shiv build
    # (`pak93_dir.vpk`, sha256 `01efc18e…`), which renders the head, arms and tail correctly:
    # its skeleton is the game's own animation skeleton with the tail appended, so it carries the
    # game's rests and the game's parents, and its `pelvis` sits under `root_motion`.  The builds
    # that folded (v10) did not fold because they copied those values; they folded while also
    # carrying a different joint order, and the rotation is what the slot refusal above catches.
    if game_skeleton and Path(game_skeleton).is_file():
        game_tree = _joint_tree_parents(datamodel, game_skeleton)
        if parents and game_tree:
            shared = [name for name in skeleton_joints if name in game_tree]
            matching_tree = [name for name in shared if parents.get(name) == game_tree[name]]
            report.update(
                {
                    "skeleton_tree_shared": len(shared),
                    "skeleton_tree_matching_game": len(matching_tree),
                }
            )
        game_bones = _joint_rests(datamodel, game_skeleton)
        copied = 0
        for joint in skeleton_joints:
            rest = game_bones.get(joint)
            if rest is None:
                continue
            ours = _rest_of(datamodel, skeleton_dmx, joint)
            if ours is not None and _rests_match(ours, rest):
                copied += 1
        report["skeleton_rests_copied_from_game"] = copied

    # 2c-3b. Nothing else is refused about `pelvis`.  Its world pose differs from the game's own
    #        skeleton by 54.4 units and 60 deg on the build that renders upright (v9), so "the
    #        pelvis must land where the game's does" is false: that build's pelvis is a root with
    #        our compensating rest, and the two documents spell one pose differently.  What is
    #        refused is the inherited rotation above and a model/skeleton tree disagreement below.

    # 2c-3. `pelvis` must not inherit a rotated root.  The game's own skeleton nests `pelvis` under
    #        `root_motion` and renders, but a Haze clip's `root_motion` carries the authored 90 deg
    #        (orientation [0.5, 0.5, 0.5, 0.5]) and our model's `root_motion` rest applies it too, so
    #        the body takes that rotation twice and folds on the floor.  Measured three times now:
    #        v8, the 2026-11-15 Shiv re-parent, and v35 on 2026-11-16 — she lies collapsed with the
    #        head, arms and tail correct.  A pelvis whose parent's world rotation is not identity is
    #        refused by name instead of being re-derived from the game's file each time.
    if parents.get("pelvis"):
        pelvis_parent = parents["pelvis"]
        parent_world = shipped_world.get(pelvis_parent)
        if parent_world:
            rotation = [row[:3] for row in parent_world[:3]]
            dot = abs(sum(a * b for a, b in zip(rotation[0], (1.0, 0.0, 0.0))))
            report["pelvis_parent"] = pelvis_parent
            report["pelvis_parent_rotation_x"] = round(dot, 6)
            if abs(dot - 1.0) > 1e-3:
                raise Refused(
                    "pelvis-parented-under-rotated-root",
                    f"`pelvis` is a child of `{pelvis_parent}`, whose world orientation turns X by "
                    f"{round(dot, 4)}; the clips and the model's own rest both carry that rotation, "
                    "so the body applies it twice and folds on the ground while the head and arms "
                    "look right. Write `pelvis` as a root (tools/skeleton_retree.py --parents with "
                    "pelvis: null)",
                )
    # ...and where the pelvis actually lands must be the game's own pose, whichever way the chain
    # spells it.  `pelvis-world-differs-from-game` refused v3 (54.39 units / 60 deg) and was then
    # deleted by `aaf6117` in favour of the parent-rotation check above; a compensating rest under
    # a rotated root passes that check and still folds the body, which is what v35 did on
    # 2026-11-16.  The world pose is the fact mesh vertices are bound to.
    if game_skeleton and Path(game_skeleton).is_file():
        ours_pelvis = shipped_world.get("pelvis")
        game_pelvis = game_world.get("pelvis")
        if ours_pelvis and game_pelvis:
            pelvis_delta = max(
                abs(a - b)
                for row_a, row_b in zip(ours_pelvis, game_pelvis)
                for a, b in zip(row_a, row_b)
            )
            report["pelvis_world_delta"] = round(pelvis_delta, 4)
            if pelvis_delta > 0.01:
                raise Refused(
                    "pelvis-world-differs-from-game",
                    f"pelvis lands {pelvis_delta:.3f} from the game's own pose in "
                    f"{skeleton_dmx.name} (parent {parents.get('pelvis')!r}); a parent and a "
                    "compensating rest compose, and the body is read rotated or folded",
                )

    report["skeleton_leaf_frame_shifts"] = leaf_shifts
    report["rest_compared_locally"] = len(local_matched)
    report["model_only_bone_frame_shifts"] = model_only_shift
    report["rest_local_shift"] = local_shift[:8]
    if local_shift:
        raise Refused(
            "skeleton-rest-differs-from-model",
            f"{len(local_shift)} joints sit at another offset from their own parent than the model "
            f"declares, and their parents differ between the documents so a world comparison cannot "
            f"decide it ({local_shift[:4]})",
        )
    if frame_shift:
        raise Refused(
            "skeleton-rest-differs-from-model",
            f"{len(frame_shift)} joints of {skeleton_dmx.name} sit in a different frame than the model "
            f"(e.g. {frame_shift[:3]}); the clips are sampled against the skeleton's poses while the "
            "mesh vertices are bound to the model's, so the body is read rotated or lying down",
        )
    stock_table = None
    if game_skeleton and Path(game_skeleton).is_file():
        stock_table = _joint_table(datamodel, game_skeleton)
        # `pelvis` is exempt on purpose, and this is measured, not a preference: the model's
        # `root_motion` carries the authored 90 deg (orientation [0.5, 0.5, 0.5, 0.5]) while the
        # game's own skeleton puts that rotation on the pelvis link instead (pelvis head
        # [0, 53.9, -0.48], identity).  Parenting our pelvis under `root_motion` applied the 90 deg
        # twice and laid the body flat (2026-11-15, the Shiv pelvis re-parent entry in this file).
        # Every other parent must still match the game's.
        # `weaponHand_L/R` are exempt for a different reason: they carry no vertex weights in
        # this port (the body and tail meshes have no such joints at all), they exist only so the
        # game's own bone masks resolve, and they are appended *after* the last mesh joint so they
        # cannot shift a slot.  Their parent is kept where the append put it (`hand_L/hand_R`)
        # because moving them into `arm_*_IKTARGET`'s children changes the walk order, which is the
        # slot order — the exact shift this file now refuses.
        exempt = {"pelvis", "weaponHand_L", "weaponHand_R"}
        stock_order = [name for name in stock_table["__order__"]["order"] if name in set(skeleton_joints) and name not in exempt]
        parent_differs = [
            (name, stock_table[name]["parent"], parents.get(name))
            for name in stock_order
            if stock_table[name]["parent"] != parents.get(name)
        ]
        if parent_differs:
            raise Refused(
                "skeleton-parent-differs-from-game",
                f"{len(parent_differs)} joints keep a different parent than {game_skeleton.name} "
                f"(e.g. {parent_differs[:3]}); a joint is read in its parent's frame, so the mesh is intact and the pose is wrong",
            )
        # Rest is deliberately NOT compared against the game's *skeleton* document.
        # Two shipped failures bracket that comparison: the Haze skeleton's own pelvis
        # head is 54 units from `haze_skel.dmx` while the game's own clips read fine,
        # and copying that rest into the mesh document shredded the body because a
        # rest here is the skinning bind. Parents and the chain are the comparable
        # facts. `--game-model` compares like with like for the bind, below.
    model_tail = _tail_chain(model_joints)
    orphaned = [name for name in skeleton_tail if name not in set(model_joints)]
    if orphaned:
        raise Refused(
            "tail-not-on-model",
            f"{orphaned} are animated but absent from {model_dmx.name}; the tail has no skinning",
        )

    # 3. Shared joints must keep their relative order, or the engine binds the
    #    model's skeleton by position and the head and arms rotate.
    # 6. Shared joints must keep their relative order between the model's own mesh
    #    skeleton and the shipped skeleton.  Exact equality is NOT required and was
    #    my invention: the accepted Shiv build ships a 171-joint skeleton over a
    #    168-joint model (see AGENTS.md 2026-11-14, "the bake is faithful, its track
    #    set is not").  What the client does bind by index is the clip against the
    #    skeleton, which 6b covers.
    # An object-like joint is the armature object the extraction writes beside the
    # bones ("haze_body", "DMF Tail"); the client does not bind it.
    object_like = lambda name: " " in name or name.startswith("DMF ")
    model_game = [name for name in model_joints if not object_like(name)]
    # The skeleton's slot order is its `jointList`, not its tree walk: the compiled skeleton
    # numbers bones from the list, and the tree is hierarchy only (the appended tail nests
    # under `pelvis`, so a depth-first read would place it between body joints).
    skeleton_game = [name for name in _joint_list_order(datamodel, skeleton_dmx) if not object_like(name)]
    shared = [name for name in model_game if name in set(skeleton_game)]

    # 3c. Slots are absolute, not relative, and this is the check that was missing on
    #     2026-11-15 (owner: *"how did this pass allow her head and arms and tail to be
    #     rotated wrong"*).  Every earlier ordering check compared our skeleton against our
    #     model, which one document cannot falsify about the other: the shipped v6 model and
    #     its skeleton agree 131/131 while the game's own skeleton is reordered underneath
    #     them.  Measured on the installed v6 pak: 88 of the 98 joints `haze_skel.dmx` carries
    #     sit at a different slot in the shipped skeleton, the first being `weaponHand_L`
    #     (game slot 6, shipped slot 22).  The game's bone masks and its clips are serialised
    #     against its own skeleton's indices, so a joint inserted before the end renames every
    #     bone after it — arms, head and tail read rotated while every document is internally
    #     consistent.  Extra joints may only be appended after the game's last joint.
    if stock_table is not None:
        # Both orders are checked, because they are different documents and only measurement
        # says which one the compiler numbers by.  3c compares `jointList`; 3d compares the tree
        # walk.  A build can pass one and fail the other — that is the 2026-11-16 v9 pak, whose
        # list kept the game prefix while its tree put the tail under `pelvis` mid-walk.
        # The numbering the client binds against comes from the compiled MODEL's `Skeleton` tree,
        # not from the skeleton document's tree, and that is measured on two in-game builds:
        # v9's model tree was ours and the head, arms and tail rotated; v10's model tree is the
        # game's own.  Both skeletons (v9 and v10) have world poses identical to the game's own
        # (`WORLD-DIFF 0 of 131`), so the pose data is not what rotates a limb — the tree the
        # model is compiled with is.  The skeleton's own walk is therefore NOT refused for the one
        # edge that must differ (`pelvis` as a root, see 2c-3a); the model's tree is refused when
        # it differs from the game's at all.
        # The model and the skeleton must present THE SAME tree.  Measured in game on 2026-11-16:
        # a model built on the game's own nesting while the skeleton kept ours rendered the body
        # flat (v11), and both on ours rendered it upright (v9).  Which nesting is right is the
        # bind's business — the extracted mesh binds our tree — but the two documents disagreeing
        # is a refusal, because the client poses the skeleton and skins with the model.
        model_tree = _model_bone_parents(vmdl)
        skeleton_tree = {name: parents.get(name) for name in skeleton_joints}
        # 3b-1. The `*_end` leaves may not be dropped and their hierarchy may not be broken.
        # Measured on 2026-11-16: the working Shiv pak (`pak93_dir.vpk`, sha256 01efc18e…) ships a
        # custom `shiv.vnmskel` that is the stock document plus 147 lines of `*_end` high-LOD bone
        # names, and its skeleton carries those 168 bones.  A Haze build assembled from the game's
        # 98-joint animation skeleton plus the tail dropped all 24 leaves (`head_end`,
        # `finger_*_end`, `ball_end_*`), and the owner saw the head, arms and tail rotate while the
        # body stood upright.  Dropping a leaf, re-parenting one, or moving its children changes the
        # frame every mesh skinned to it is posed in, so each is refused by name.
        END_LEAF = re.compile(r"_end(_[LR])?$")
        model_children: dict[str, set[str]] = {}
        skeleton_children: dict[str, set[str]] = {}
        for name, parent in model_tree.items():
            if parent:
                model_children.setdefault(parent, set()).add(name)
        for name, parent in skeleton_tree.items():
            if parent:
                skeleton_children.setdefault(parent, set()).add(name)
        model_end = {name for name in model_tree if END_LEAF.search(name)}
        skeleton_set = set(skeleton_joints)
        dropped_end = sorted(model_end - skeleton_set)
        report["end_bones_declared_by_model"] = len(model_end)
        report["end_bones_missing_from_skeleton"] = dropped_end
        if dropped_end:
            raise Refused(
                "end-bone-dropped",
                f"{skeleton_dmx.name} drops {len(dropped_end)} `*_end` bones the model declares "
                f"({dropped_end[:4]}). A mesh skinned to a leaf is posed by that leaf's frame; "
                "without it the bone falls back to its parent's pose and the head, arms or tail "
                "rotate. Append the leaves with tools/skeleton_append_leaves.py",
            )
        # 3b-0. Nothing the game animates may be dropped, for any convenience.  The game's own
        # `haze_skel.dmx` carries the two bones that point the arms (`weaponHand_L` slot 6,
        # `weaponHand_R` slot 8) and `attachWorld`; a build assembled without them is a build whose
        # hands are driven by whatever sits at those slots instead.
        dropped_game = [name for name in skeleton_game if name not in skeleton_set]
        report["game_joints_missing_from_skeleton"] = dropped_game
        if dropped_game:
            raise Refused(
                "game-joint-dropped",
                f"{skeleton_dmx.name} drops {len(dropped_game)} joints the game's own skeleton "
                f"animates ({dropped_game[:4]}). The game's clips and the hero's masks bind those "
                "slots; a skeleton without them poses the head and arms from the wrong bone",
            )

        shared_end = sorted(model_end & skeleton_set)
        parent_breaks = [
            (name, model_tree.get(name), skeleton_tree.get(name))
            for name in shared_end
            if model_tree.get(name) != skeleton_tree.get(name)
        ]
        child_breaks = [
            (
                name,
                sorted(model_children.get(name, set())),
                sorted(skeleton_children.get(name, set())),
            )
            for name in shared_end
            if model_children.get(name, set()) != skeleton_children.get(name, set())
        ]
        report["end_bone_parent_breaks"] = parent_breaks
        report["end_bone_child_breaks"] = child_breaks
        if parent_breaks or child_breaks:
            raise Refused(
                "end-bone-hierarchy-broken",
                f"{len(parent_breaks)} `*_end` bones sit under another parent and "
                f"{len(child_breaks)} carry another child set than the model declares "
                f"({(parent_breaks or child_breaks)[:3]}). The leaf's frame is its parent chain; "
                "a broken hierarchy poses the skinned vertices somewhere else",
            )

        # A joint the game's own skeleton animates follows the game skeleton's parent; a bone only
        # the model declares follows the model.  The game's own `haze.vmdl` puts `pelvis` at the
        # root while its own `haze_skel.dmx` nests it under `root_motion` (the 2c-3b note), and
        # `weaponHand_L/R` are absent from the model entirely.  Our skeleton was measured identical
        # to the game's (`skeleton_delta` moved=0), so what is refused here is our skeleton
        # inventing a third answer, not the pair the game ships.
        game_parents = (
            _joint_tree_parents(datamodel, game_skeleton)
            if game_skeleton and Path(game_skeleton).is_file()
            else {}
        )
        tree_moves = [
            (name, skeleton_tree.get(name), game_parents.get(name, model_tree.get(name)))
            for name in skeleton_tree
            if name in model_tree
            and skeleton_tree.get(name) != game_parents.get(name, model_tree.get(name))
            # `pelvis` as a root is the upright shape (2c-3, v9/v25/v31) and the game spells the
            # same pose with it under `root_motion`; `pelvis-parented-under-rotated-root` refuses
            # the failure that shape exists to avoid.
            and not (name == "pelvis" and skeleton_tree.get(name) is None)
        ]
        report.update({"model_tree_moves": len(tree_moves)})
        if tree_moves:
            raise Refused(
                "model-skeleton-trees-differ",
                f"{len(tree_moves)} bones of {model_dmx.name} sit under a different parent in "
                f"the model's `Skeleton` than in {skeleton_dmx.name} (e.g. {tree_moves[:4]}); the "
                "client poses one document and skins with the other, and the body is read folded",
            )
        # `jointList`, not the tree walk: the tree nests the appended tail under `pelvis`, so a
        # depth-first read puts tail joints between body joints while the compiled skeleton
        # still numbers them last.  Shiv ships exactly that shape and works; the index base is
        # the list, and the list is what a `.vnmskel`'s numeric `m_boneIDs` resolve against.
        stock_order_all = list(dict.fromkeys(_joint_list_order(datamodel, game_skeleton)))
        ours = list(dict.fromkeys(_joint_list_order(datamodel, skeleton_dmx)))
        our_slots = {name: index for index, name in enumerate(ours)}
        shifted = [
            (name, game_slot, our_slots[name])
            for game_slot, name in enumerate(stock_order_all)
            if name in our_slots and our_slots[name] != game_slot
        ]
        # The game's slot positions are recorded, not refused.  Refusing them forced the shipped
        # `jointList` to be the game's list, and the game's own list is NOT its own walk order
        # (`WALK-ORDER haze_skel.dmx ... inversions=4`: clavicle_R, leg_upper_L, leg_upper_R,
        # attachWorld), so the list and the walk could never agree — and a list that disagrees
        # with the walk is the state in which a clip bone index lands on another bone.
        report.update({"game_slot_shifts": len(shifted)})

    # 3a-2. THE refusal for a rotated head, arm or tail: a game joint may not change slot.
    #
    # Its statement is taken from the two skeletons that render the head, arms and tail correctly,
    # not from a rule of our own:
    #   * the game's own `haze_skel.dmx` lists `weaponHand_L` at 6, `head` at 15, `hand_L` at 20,
    #     `hand_R` at 53, `pelvis` at 9, and its clips bind to that numbering;
    #   * the pinned Shiv skeleton (`pak93_dir.vpk`, sha256 `01efc18e…`) is that animation skeleton
    #     with the tail appended after every stock joint, nothing re-ordered, and the owner reports
    #     its head, arms and tail correct (`WALK-ORDER shiv_tailbones.dmx ... inversions=5` — that
    #     document's list is NOT its own walk order and still renders correctly).
    #
    # The builds that rotated did move game joints: v6 put `weaponHand_L` at 50 and `weaponHand_R`
    # at 91; v9 kept the game's prefix in `jointList` while walking a different prefix; v15 nested
    # the `*_end` leaves beside their parents, moving `hand_L` 20 -> 21 and `hand_R` 53 -> 61.
    # Extras take slots after every game joint, which is what the pinned build does with its tail.
    list_order = [
        name for name in _joint_list_order(datamodel, skeleton_dmx) if not object_like(name)
    ]
    walk_order = [
        name for name in _joint_tree_order(datamodel, skeleton_dmx) if not object_like(name)
    ]
    game_order = [
        name for name in _joint_list_order(datamodel, game_skeleton) if not object_like(name)
    ] if game_skeleton and Path(game_skeleton).is_file() else []
    game_slots = {name: slot for slot, name in enumerate(game_order)}
    listed_slots = {name: slot for slot, name in enumerate(list_order)}
    walked_slots = {name: slot for slot, name in enumerate(walk_order)}
    shifted = [
        {"joint": name, "game": slot, "ours": listed_slots[name]}
        for name, slot in game_slots.items()
        if name in listed_slots and listed_slots[name] != slot
    ]
    shifted_in_walk = [
        {"joint": name, "game": slot, "ours": walked_slots[name]}
        for name, slot in game_slots.items()
        if name in walked_slots and walked_slots[name] != slot
    ]
    report.update(
        {
            "skeleton_list_vs_walk_inversions": len(_subsequence(walk_order, list_order)),
            "skeleton_list": list_order[:8],
            "skeleton_walk": walk_order[:8],
            "game_joints": len(game_slots),
            "game_slot_shifts": len(shifted),
            "game_slot_shifts_in_walk": len(shifted_in_walk),
            "first_shifted": shifted[:4],
        }
    )
    if shifted:
        raise Refused(
            "skeleton-shifts-game-joint",
            f"{skeleton_dmx.name} moves {len(shifted)} of the game's {len(game_slots)} joints to "
            f"another slot ({shifted[:4]}). A clip binds a bone by index, and this is the state in "
            "which the head, arms and tail rotate; every extra joint goes after the last game joint",
        )
    # The tree walk is refused too, and it was deleted once already.  `skeleton-tree-shifts-game-joint`
    # refused v9 (88 of 98 game joints at another walked slot, `weaponHand_L` 21 vs 6) and was then
    # removed by `aaf6117` on the reading that the game's own skeleton walks an order its own list
    # does not share.  That reading is about the game's file; it is not a licence for ours.  The
    # owner's verdict on the builds after v10 — *"every single version past the initial haze no skel
    # vk has made ZERO PROGRESS"* — is the measurement that the removal admitted them, so the walk
    # is refused again whenever it moves a joint the game numbers earlier.
    if shifted_in_walk:
        raise Refused(
            "skeleton-tree-shifts-game-joint",
            f"{skeleton_dmx.name} walks {len(shifted_in_walk)} of the game's {len(game_slots)} "
            f"joints at another slot ({shifted_in_walk[:4]}); the model's bones are numbered by the "
            "tree the client walks, so a bone inserted before the end rotates the head, arms and tail",
        )

    # 3b. The vmdl's own `Skeleton` section must declare every joint the shipped skeleton
    #     carries, in the same slot order.  This is the check that was missing on 2026-11-15:
    #     the pack compared the render mesh DMX (131 joints) against the skeleton and admitted,
    #     while the model the client actually loaded declared 120 bones with no tail at all, so
    #     70 of 120 shared joints sat at a different slot and the arms, head and tail rotated.
    #     The mesh DMX and the vmdl are not the same document and one does not vouch for the other.
    from skeleton_model_order_probe import model_bone_tree  # noqa: WPS433

    declared, _declared_parents = model_bone_tree(Path(report["model"]))
    declared_set = set(declared)
    # A joint the GAME'S OWN model also omits is the game's own answer, not our omission: the
    # game's `haze.vmdl` declares 120 bones and does not declare `weaponHand_L/R` (slots 6 and 8 of
    # its own skeleton) or `attachWorld` (slot 31), while its own `haze_skel.dmx` animates all
    # three.  Requiring the model to declare them refuses the game's own shape.
    game_model = Path("artifacts/probes/game-vnmskel-dump/models/heroes_staging/haze/haze.vmdl")
    game_model_declared: set[str] = set()
    if game_model.is_file():
        try:
            game_model_declared = set(model_bone_tree(game_model)[0])
        except SystemExit:
            game_model_declared = set()
    absent = [
        name
        for name in skeleton_game
        if name not in declared_set
        and (not game_model_declared or name in game_model_declared)
    ]
    report["skeleton_joints_absent_from_game_model"] = sorted(
        name for name in skeleton_game if name not in declared_set
    )
    if absent:
        raise Refused(
            "model-vmdl-missing-skeleton-joint",
            f"{Path(report['model']).name} declares {len(declared)} bones and the shipped skeleton "
            f"carries {len(skeleton_game)}; {len(absent)} skeleton joints are absent from the model "
            f"({absent[:6]}). The client cannot bind a bone the model does not declare.",
        )
    # 3b-2. THE model-side refusal for a rotated head, arm or tail: the model's own
    #       `m_modelSkeleton` order must give every skeleton joint the slot the skeleton gives it.
    #       This is what shipped rotated in v16 (2026-11-16): the skeleton was the game's own 98
    #       plus the tail at 97..105, and the model still declared `head_end` at 17, `hand_L` at
    #       21, `hand_R` at 61 and `tail_0` at 121, so the client bound the meshes and the clips to
    #       a different numbering than the one the gate had just proved.  The addon never wrote
    #       this section at all; `tools/model_skeleton_write.py` does, and this makes a model that
    #       skips it impossible to pack.
    model_slots = {name: slot for slot, name in enumerate(declared)}
    # The client binds by the model's own order, so the RELATIVE order of the skeleton's joints in
    # that order is what binds them to the clips.  Absolute slots may shift when the model also
    # declares joints the animation skeleton does not (the 24 `*_end` leaves, `attachWorld` at the
    # end) — the pinned Shiv build has 135 of 168 bones at another absolute slot than its list and
    # renders correctly.  What cannot happen is the skeleton's own joints appearing in another
    # relative order, which is what rotated the head, arms and tail in v16.
    projection = [name for name in declared if name in set(skeleton_joints)]
    expected = [name for name in skeleton_joints if name in set(declared)]
    report["model_projection_matches_skeleton"] = projection == expected
    if projection != expected:
        misplaced = [
            {"joint": a, "model": model_slots.get(a), "skeleton": index}
            for index, (a, b) in enumerate(zip(projection, expected))
            if a != b
        ]
        raise Refused(
            "model-slot-shifts-skeleton-joint",
            f"{Path(report['model']).name} declares {len(misplaced)} skeleton joints in another "
            f"relative order than {skeleton_dmx.name} ({misplaced[:4]}); the client binds the "
            "meshes and the clips through this list, so the head, arms and tail are driven by the "
            "wrong bones. Rebuild it with tools/model_skeleton_write.py",
        )

    # The vmdl's tree order is NOT compared with the skeleton's `jointList`, and this was
    # measured on 2026-11-16 rather than assumed: the build the owner accepted
    # (`pak93_dir.vpk`, sha256 01efc18e…) has 135 of its 168 declared bones at a different
    # position than its own skeleton's list, and it works.  A skeleton is a tree; its list can
    # order appended joints after every body joint, which no depth-first walk can reproduce.
    # The `.vnmskel` numbers bones by the list, so coverage is the contract (checked above) and
    # the tree is hierarchy only.

    # A mesh's joint order is not required to match the skeleton's, and the game itself proves
    # it: `haze_body.dmx` in pak01 carries 120 joints with `weaponHand_L` near slot 50 while
    # `haze_skel.dmx` carries it at slot 6, and the hero renders correctly.  A mesh's weights
    # name their joints; the numbered list that matters is the skeleton's.  Coverage of every
    # mesh joint by the skeleton is checked above (`mesh-joint-not-in-skeleton`).

    # 3a. A model document carries its skeleton twice: the DmeModel tree the client walks and
    #     a flat `jointList`.  When they hold different counts the document has been grafted
    #     twice — 2026-11-15's `haze_tailbones4.fixed.dmx` walked 131 joints while its
    #     `jointList` carried 260 elements, so slot indices and names disagreed and the
    #     ordering refusals fired on joints nobody had touched.  Count elements, not names.
    if True:
        def _counts(datamodel, path):
            root = datamodel.load(str(path)).root
            model = root["skeleton"] if "skeleton" in root.keys() else root
            walked = 0
            stack = [model]
            while stack:
                node = stack.pop()
                for child in node["children"] if "children" in node.keys() else []:
                    if getattr(child, "type", "") == "DmeJoint":
                        walked += 1
                    stack.append(child)
            listed = 0
            if "jointList" in model.keys():
                listed = sum(1 for child in model["jointList"] if getattr(child, "type", "") == "DmeJoint")
            return walked, listed

        walked, listed = _counts(datamodel, model_dmx)
        unique = len({name for name in _joint_table(datamodel, model_dmx)["__order__"]["order"]})
        if walked != unique:
            raise Refused(
                "model-duplicate-joint-elements",
                f"{model_dmx.name} carries {walked} joint elements for {unique} distinct joints "
                f"(jointList {listed}): the document was grafted more than once. The names dedupe, so the "
                "name-based checks stay quiet, but a mesh binds by element index and the extra elements shift "
                "every later slot",
            )
        if listed and listed != walked:
            raise Refused(
                "model-jointlist-differs-from-tree",
                f"{model_dmx.name} walks {walked} joints but its `jointList` holds {listed}: the document was "
                "grafted more than once, so a slot index and a joint name disagree and every binding after the "
                "first extra element is wrong",
            )

    # 3b. A mesh binds by index into the model document's joint list, so the two lists
    #     must agree slot by slot.  The 15:36 build's model document inserted
    #     `weaponHand_L/R` at indices 6 and 8 while every mesh (and the game's own body)
    #     has `attachWorld` at 6: every joint after that was read two slots off and the
    #     body tore into flat wedges lying on the floor.  This is not an order preference,
    #     it is the index the vertex weights name.
    model_order = _joint_table(datamodel, model_dmx)["__order__"]["order"]
    for mesh_name, mesh in _render_meshes(root, vmdl):
        mesh_order = _joint_table(datamodel, mesh)["__order__"]["order"]
        # Relative order of the joints the mesh actually shares with the model.  The absolute
        # slot cannot be compared across documents: the gun meshes carry their own prop bones
        # (`forearm_tie_0_L`) where the model has `weaponHand_L`, and the model must also hold the
        # tail and `weaponHand`, so two documents legitimately interleave them differently.  What
        # must hold is that a joint never moves past another joint it shares with the mesh — the
        # 15:36 model document inserted `weaponHand_L/R` *before* the body's `attachWorld`, which
        # reversed that order for 90 joints and tore the body into flat wedges.
        shared_order = [name for name in mesh_order if name in set(model_order)]
        in_model = [name for name in model_order if name in set(shared_order)]
        if shared_order != in_model:
            first = next(i for i, (a, b) in enumerate(zip(shared_order, in_model)) if a != b)
            raise Refused(
                "model-joint-order-differs-from-mesh",
                f"{model_dmx.name} and {Path(mesh).name} order their {len(shared_order)} shared joints differently "
                f"at shared slot {first} (mesh has {shared_order[first]!r}, model has {in_model[first]!r}); "
                "a mesh binds by index into the model's joint list, so a joint that moves past another is read from the wrong bone",
            )

    # 6b. Every shipped clip must carry the shipped skeleton's own track count.  A
    #     clip authored on another skeleton is bound by index, so the head and arms
    #     rotate and whatever the skeleton has and the clip lacks (the tail) drops
    #     out of the pose.  Measured in AGENTS.md (2026-11-15): the 10:06 pak ships
    #     147-track clips under a 171-joint skeleton and draws no tail, while every
    #     build accepted as tail-animating carries 168 tracks on a 168-joint rig.
    #     Track count is a binding fact, not a detail.
    if clip_dir is not None and clip_dir.is_dir():
        skeleton_table = _joint_table(datamodel, skeleton_dmx)
        skeleton_names = [name for name in dict.fromkeys(skeleton_table["__order__"]["order"]) if not object_like(name)]
        # The clips must drive every joint the game animates plus the tail.  A model-side bone —
        # the `*_end` leaves, the `*Hier_*` helpers, `back_waist_pack_*` — is not in the game's own
        # animation skeleton either: `haze_skel.dmx` carries 98 while the compiled model declares
        # 120, and the game's own clips ship 98.  Measured on the stock build, the client fills the
        # rest from the model's bind pose, so requiring them here refuses the game's own shape.
        game_names: set[str] = set()
        if game_skeleton and Path(game_skeleton).is_file():
            game_names = set(_joint_rests(datamodel, game_skeleton))
        wanted = {
            name
            for name in skeleton_names
            if not game_names or name in game_names or name in _TAIL_NAMES
        }
        report["clip_coverage_expected"] = len(wanted)
        for clip in sorted(clip_dir.glob("*.dmx")):
            table = _joint_table(datamodel, clip)
            names = [name for name in dict.fromkeys(table["__order__"]["order"]) if not object_like(name)]
            if not names:
                continue
            # Coverage, not equality: a clip body carries joints the animation skeleton does not
            # (the game's own `weapon_stand_idle` declares 140 against a 98-joint `haze_skel.dmx`,
            # and the pinned Shiv clips carry 168 against its 168-joint skeleton), so a body with
            # more joints than the skeleton is the game's own shape.  What cannot happen is a
            # skeleton joint the clip never declares.
            missing = sorted(wanted - set(names))
            if missing:
                raise Refused(
                    "clip-joint-list-differs",
                    f"{clip.name} declares {len(names)} joints and never names {len(missing)} of the "
                    f"skeleton's {len(wanted)} ({missing[:4]}); a clip that does not drive a bone "
                    "leaves it in whatever pose the previous clip gave it",
                )
            # The joint transform a clip declares is the rest its samples are read
            # against.  A clip whose rest differs from the shipped skeleton's reads
            # every bone through a different frame: in game that shows as many bone
            # orientations wrong, with the mesh intact.
            drifted = []
            for name in skeleton_names:
                here, there = table.get(name), skeleton_table.get(name)
                if not here or not there:
                    continue
                delta = max(abs(a - b) for a, b in zip(here["head"], there["head"]))
                dot = abs(sum(a * b for a, b in zip(here["orientation"], there["orientation"])))
                if delta > 0.01 or (1.0 - dot) > 2e-3:  # 2e-3 is ~3.6deg: 4dp-rounded unit quaternions read 1e-4 apart
                    drifted.append((name, round(delta, 4), round(1.0 - dot, 6)))
            # 6d. A clip may only disagree with the skeleton about a joint's rest if
            #     its channel data was re-expressed in that frame.  Rewriting the rest
            #     and leaving the game's own channel values in place reads every sample
            #     through a different frame: in game the body folds over (measured on
            #     the 03:54 Haze build).  The comparison is exact equality of values,
            #     because "approximately the same channels" is exactly the failure.
            if bodies:
                origin = Path(bodies) / clip.name
                if origin.is_file():
                    origin_table = _joint_table(datamodel, origin)
                    moved = []
                    for name in skeleton_names:
                        here, base = table.get(name), origin_table.get(name)
                        if not here or not base:
                            continue
                        if max(abs(a - b) for a, b in zip(here["head"], base["head"])) > 0.01:
                            moved.append(name)
                    if moved and _channel_values_equal(datamodel, origin, clip):
                        raise Refused(
                            "clip-rest-moved-without-rebake",
                            f"{clip.name} declares a rest moved for {len(moved)} joints ({moved[:4]}) but carries {origin.name}'s own channel values; "
                            "the samples are then read in a frame they were not authored in and the body folds over",
                        )
            # A clip's declared rest is authored data and legitimately differs from the
            # model's: the shipping Shiv pak — the build that animates in game — declares
            # rests up to 179.1 deg from its own skeleton (measured with
            # tools/skeleton_rest_diff_probe.py, artifacts/receipts/rest-shiv-clip-vs-skel.json),
            # and the stock Haze clips differ from their body by up to 164.8 deg
            # (rest-clip-vs-body.json). Refusing that comparison was an invented rule that
            # refused shipped data. What must not happen is a *tool* moving a rest while
            # leaving the authored channels in place; 6d above is that check and it stays.
            if drifted:
                report.setdefault("rest_drift_observed", {})[clip.name] = len(drifted)
    # A drift recorded but not explained is a check that did not fire.  The explanation
    # above needs the game's own body DMX per clip (``--bodies``); without it this loop
    # could only note the drift and admit the pak, which is exactly how the 2026-11-15
    # build shipped every clip with a moved rest and folded the body over in game.
    drifted_clips = report.get("rest_drift_observed") or {}
    if drifted_clips and not bodies:
        first = sorted(drifted_clips)[0]
        raise Refused(
            "clip-rest-drift-unverified",
            f"{len(drifted_clips)} clips declare a rest that differs from the skeleton "
            f"({first}: {drifted_clips[first]} joints) and no --bodies was passed, so the gate "
            "cannot tell an authored rebake from a moved rest with the game's channels left in "
            "place. Pass the per-clip game body DMX, or fix the clips; an observed drift is not "
            "a pass.",
        )
    report.update(
        {
            "tail_chain": skeleton_tail,
            "shared_joints": len(model_game),
            "admitted": True,
            # Recorded in the admitted report so a downstream check (the repository gate)
            # can refuse a release whose skeleton moved a game joint without re-deriving it.
            "skeleton_identity": {
                "game_joints": len(stock_order_all) if stock_table is not None else 0,
                "shipped_joints": len(skeleton_game),
                "shifted": len(shifted) if stock_table is not None else -1,
                # The walk, not the list.  v9 passed the list check and rotated in game.
                "tree_shifted": 0 if stock_table is not None else -1,
            },
        }
    )
    return report


def main() -> int:
    args = _arguments()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from work_record import finish, refuse_ephemeral_paths

    # A report written to a temp directory is work that vanishes; refuse it here so
    # the gate cannot be run in a way nobody can reproduce.
    refuse_ephemeral_paths([args.report])
    root = Path(args.addon_content)
    report: dict = {"addon_content": str(root)}
    try:
        if not root.is_dir():
            raise Refused("addon-missing", str(root))
        report.update(run(root, args.clips, args.bodies, args.game_skeleton, args.game_model))
        print(f"GATE ADMIT {root.name}: model {report['model_joints']} joints, "
              f"skeleton {report.get('skeleton_joints', 'game')}, tail {len(report['tail_chain'])}", flush=True)
        code = 0
    except Refused as refusal:
        report.update({"admitted": False, "refused": refusal.code, "detail": refusal.detail})
        print(f"GATE REFUSE {refusal.code}: {refusal.detail}", flush=True)
        code = 2
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    finish(
        "tail_release_gate",
        [args.report],
        f"GATE {'ADMIT' if code == 0 else 'REFUSE'} {root.name}: {report.get('refused') or 'admitted'}",
        "pass" if code == 0 else "refuse",
        {"verdict": report.get("refused"), "clips": args.clips, "bodies": args.bodies},
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
