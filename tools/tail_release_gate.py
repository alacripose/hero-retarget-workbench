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
    invented = [name for name in roots if name not in set(model_roots)]
    if invented:
        raise Refused(
            "skeleton-invented-root",
            f"{skeleton_dmx.name} adds root joints {invented} that {model_dmx.name} does not have; "
            "they hang off nothing, are dropped by the compiler, and every mask naming one crashes the client",
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
    mesh_absent = [name for name in model_view if name not in set(shipped_order)]

    if mesh_absent:
        raise Refused(
            "mesh-joint-not-in-skeleton",
            f"{len(mesh_absent)} joints of {model_dmx.name} are absent from {skeleton_dmx.name} "
            f"({mesh_absent[:4]}); the mesh is skinned to bones the shipped skeleton does not carry",
        )
    # The frames are compared in WORLD space, not joint-by-joint local ones, and that is measured:
    # our skeleton writes `pelvis` under `root_motion` while the model document writes it at the
    # root, and the two spellings have identical world transforms (both `[-0.482, 0, 53.909]` with
    # the same rotation).  Comparing the local decompositions reported one shifted joint on a
    # correct pair; what must agree is where each joint actually ends up, since that is what the
    # mesh vertices were bound to.
    shipped_world = _joint_world_map(datamodel, skeleton_dmx)
    model_world = _joint_world_map(datamodel, model_dmx)
    frame_shift = []
    for name in model_view:
        here, there = shipped_world.get(name), model_world.get(name)
        if not here or not there:
            continue
        delta = max(abs(a - b) for row_a, row_b in zip(here, there) for a, b in zip(row_a, row_b))
        if delta > 0.01:
            frame_shift.append((name, round(delta, 4)))
    # 2c-3. `pelvis` must not inherit a rotated root.  Measured on the 2026-11-16 v8 build: the
    #      skeleton was rebuilt in the game's list order and its hierarchy was taken from the
    #      game as well, which parented `pelvis` under `root_motion` — and the model's
    #      `root_motion` carries the authored 90 deg, so the body applied it twice and collapsed
    #      in on itself while the head, arms and tail were finally right.  AGENTS.md records the
    #      same failure from the 2026-11-15 pelvis re-parent; the gate did not refuse it then and
    #      no check covered it until now.
    # The pose, not the parent: a parent and a rest are one fact, and the same world transform can
    # be spelled either way (our rest compensating a missing parent, or the game's rest under the
    # game's parent).  What must hold is that `pelvis` lands where the game puts it.  v8 parented
    # it under a rotated root while keeping our compensating rest: the two offsets composed and
    # the body collapsed in on itself.
    if game_skeleton is not None and game_skeleton.is_file():
        ours_world = _joint_world(datamodel, skeleton_dmx, "pelvis")
        game_world = _joint_world(datamodel, game_skeleton, "pelvis")
        if ours_world is not None and game_world is not None:
            delta = max(abs(a - b) for row_a, row_b in zip(ours_world, game_world) for a, b in zip(row_a, row_b))
            if delta > 0.01:
                raise Refused(
                    "pelvis-world-differs-from-game",
                    f"pelvis lands {delta:.3f} from the game's own pose in {skeleton_dmx.name} "
                    f"(parent {parents.get('pelvis')!r}); a parent and a compensating rest "
                    "compose, and the body is read rotated or folded",
                )
    if frame_shift:
        raise Refused(
            "skeleton-rest-differs-from-model",
            f"{len(frame_shift)} joints of {skeleton_dmx.name} sit in a different frame than the model "
            f"(e.g. {frame_shift[:3]}); the clips are sampled against the skeleton's poses while the "
            "mesh vertices are bound to the model's, so the body is read rotated or lying down",
        )
    stock_table = None
    if game_skeleton is not None and game_skeleton.is_file():
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
        tree_order = [name for name in skeleton_joints if not object_like(name)]
        # Compare the tree walk against the GAME'S OWN tree walk, not its `jointList`.  Measured on
        # 2026-11-16: the game's own `haze_skel.dmx` walks 4 of its joints (`clavicle_R`,
        # `leg_upper_L`, `leg_upper_R`, `attachWorld`) in an order its `jointList` does not share, so
        # "walk is a subsequence of the list" refuses the game's own file.  The list indexes masks;
        # the tree is what the client walks; each is checked against the same document it came from.
        wants = list(dict.fromkeys(_joint_tree_order(datamodel, game_skeleton)))
        stocks_own = _subsequence(
            [name for name in wants if not object_like(name)],
            list(dict.fromkeys(_joint_list_order(datamodel, game_skeleton))),
        )
        report.update({"game_walk_vs_list_inversions": len(stocks_own)})
        # Relative order, not absolute slots: `pelvis` is deliberately promoted to a root (see
        # 2c-3), which moves its whole subtree earlier in the walk without changing how the
        # game's joints sit relative to each other.  What rotates the body is a game joint
        # appearing before one the game puts later — the v9 build walked `weaponHand_L` at 21
        # and `arm_R_IKTARGET` at 6, and the head, arms and tail rotated again.
        tree_inversions = _subsequence([name for name in tree_order if name in set(wants)], wants)
        if tree_inversions:
            raise Refused(
                "skeleton-tree-shifts-game-joint",
                f"{len(tree_inversions)} joints of {game_skeleton.name} are walked out of order in "
                f"{skeleton_dmx.name} (e.g. {tree_inversions[:3]}); the model's bones are numbered "
                "by the tree the client walks, so a bone inserted before another rotates the "
                "head, arms and tail",
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
        if shifted:
            raise Refused(
                "skeleton-shifts-game-joint",
                f"{len(shifted)} joints of {game_skeleton.name} sit at a different slot in "
                f"{skeleton_dmx.name} (e.g. {shifted[:3]}); the game's masks and clips index its own "
                "skeleton, so every joint after the first insertion is driven by the wrong bone",
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
    absent = [name for name in skeleton_game if name not in declared_set]
    if absent:
        raise Refused(
            "model-vmdl-missing-skeleton-joint",
            f"{Path(report['model']).name} declares {len(declared)} bones and the shipped skeleton "
            f"carries {len(skeleton_game)}; {len(absent)} skeleton joints are absent from the model "
            f"({absent[:6]}). The client cannot bind a bone the model does not declare.",
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
        wanted = set(skeleton_names)
        for clip in sorted(clip_dir.glob("*.dmx")):
            table = _joint_table(datamodel, clip)
            names = [name for name in dict.fromkeys(table["__order__"]["order"]) if not object_like(name)]
            if not names:
                continue
            if set(names) != wanted or len(names) != len(wanted):
                missing = sorted(wanted - set(names))
                extra = sorted(set(names) - wanted)
                raise Refused(
                    "clip-joint-list-differs",
                    f"{clip.name} declares {len(names)} joints against the {len(wanted)}-joint skeleton "
                    f"(missing {missing[:4]}, extra {extra[:4]}); the client binds a clip by index, so the pose is wrong and the tail drops",
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
