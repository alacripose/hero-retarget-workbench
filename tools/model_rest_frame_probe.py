"""Decide whether a vmdl bone's `angles` are local to its parent or absolute in the model.

Two documents describe the same skeleton and disagree about `pelvis` by 54.4 units and 60 deg:
the render mesh's bind (`haze_body.dmx`) and the NM skeleton (`haze_skel.dmx`).  A vmdl carries
`origin`/`angles` per bone and no quaternion, so which frame those angles are in decides whether
a model can be rebuilt from either document at all.  This probe answers it with the game's own
pair — its compiled model's decompiled `Skeleton` and its own `haze_skel.dmx` — by comparing
each declared angle triple against the local rotation and against the world rotation composed
through the parent chain, over every quaternion component order and Euler order.

    blender -b --python tools/model_rest_frame_probe.py -- \
        --vmdl <game>.vmdl --skeleton <game>_skel.dmx --report artifacts/receipts/x.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

PULSE_DIR = Path("C:/Users/ala/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")


def datamodel():
    if str(PULSE_DIR) not in sys.path:
        sys.path.insert(0, str(PULSE_DIR))
    from pulse_src_ops import datamodel as module  # noqa: WPS433

    return module


def declared(vmdl: Path) -> dict[str, list[float]]:
    """Each bone's `angles` triple, from the vmdl's Skeleton section."""
    from forge import modeldoc  # noqa: WPS433
    from skeleton_model_order_probe import model_bone_tree  # noqa: WPS433

    names, _parents = model_bone_tree(vmdl)
    text = vmdl.read_text(encoding="utf-8", errors="replace")
    blocks = modeldoc.skeleton_bone_blocks(text)
    out: dict[str, list[float]] = {}
    for name in names:
        line = next((row for row in blocks.get(name, []) if row.startswith("angles =")), None)
        if line is None:
            continue
        out[name] = [float(value) for value in line.split("[")[1].split("]")[0].split(",")]
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--vmdl", required=True)
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    from math import degrees  # noqa: WPS433
    from mathutils import Matrix, Quaternion, Vector  # noqa: WPS433

    module = datamodel()
    root = module.load(args.skeleton).root
    element = root["model"] if "model" in root.keys() else root
    while "children" not in element.keys():
        element = next(element[key] for key in element.keys() if hasattr(element[key], "keys"))

    local: dict[str, tuple] = {}
    parent: dict[str, str | None] = {}

    def walk(node, up):
        for child in node["children"]:
            transform = child["transform"]
            local[child.name] = (Vector(list(transform["position"])), list(transform["orientation"]))
            parent[child.name] = up
            walk(child, child.name)

    walk(element, None)

    def world_of(name: str):
        chain = []
        current = name
        while current:
            chain.append(current)
            current = parent.get(current)
        matrix = Matrix.Identity(4)
        for joint in reversed(chain):
            position, q = local[joint]
            matrix = (
                matrix
                @ Matrix.Translation(position)
                @ Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4()
            )
        return matrix.to_quaternion()

    angles = declared(Path(args.vmdl))
    report = {}
    for name in ("root_motion", "pelvis", "spine_0", "clavicle_L", "head"):
        if name not in angles or name not in local:
            continue
        target = angles[name]
        best = None
        position, q = local[name]
        readings = {
            "local": Quaternion((q[3], q[0], q[1], q[2])),
            "world": world_of(name),
        }
        for label, quaternion in readings.items():
            for order in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"):
                candidate = [degrees(value) for value in quaternion.to_euler(order)]
                error = max(abs(a - b) for a, b in zip(target, candidate))
                if best is None or error < best[0]:
                    best = (error, label, order, candidate)
        report[name] = {
            "declared": target,
            "best": best[1],
            "order": best[2],
            "error": round(best[0], 3),
            "candidate": [round(value, 3) for value in best[3]],
        }
        print(
            f"REST-FRAME {name}: declared {target} -> closest {best[1]}/{best[2]} at "
            f"{best[0]:.2f} deg {[round(v, 2) for v in best[3]]}",
            flush=True,
        )
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
