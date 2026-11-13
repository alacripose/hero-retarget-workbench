"""Render the bone map into a PNG so the drawing can be looked at.

Headless, with an initialised GPU and an offscreen buffer:

  blender -b --factory-startup --python tools/blender_bone_map_render.py

It writes ``artifacts/hierarchy-diag/bone-map.png`` and prints what it drew. This
is the only way to see the map without a window; the in-viewport handler uses the
same ``_draw`` path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy
import gpu
import numpy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "blender"))
import hero_retarget_workbench as dmf  # noqa: E402
from hero_retarget_workbench import hierarchy_view  # noqa: E402

OUT = REPO / "artifacts" / "hierarchy-diag" / "bone-map.png"
WIDTH, HEIGHT = 720, 900


class _Region:
    x = 0
    y = 0
    width = WIDTH
    height = HEIGHT


class _Context:
    def __init__(self, scene):
        self.scene = scene
        self.region = _Region()


BONES = [
    ("root", None, (0.0, 0.0, 0.0), (0.0, 0.0, 6.0)),
    ("spine_0", "root", (0.0, 0.0, 6.0), (0.0, 0.0, 14.0)),
    ("spine_1", "spine_0", (0.0, 0.0, 14.0), (0.0, 0.0, 22.0)),
    ("neck_0", "spine_1", (0.0, 0.0, 22.0), (0.0, 0.0, 26.0)),
    ("head", "neck_0", (0.0, 0.0, 26.0), (0.0, 0.0, 33.0)),
    ("clavicle_l", "spine_1", (2.0, 0.0, 22.0), (7.0, 0.0, 22.0)),
    ("arm_l", "clavicle_l", (7.0, 0.0, 22.0), (16.0, 0.0, 18.0)),
    ("hand_l", "arm_l", (16.0, 0.0, 18.0), (21.0, 0.0, 15.0)),
    ("clavicle_r", "spine_1", (-2.0, 0.0, 22.0), (-7.0, 0.0, 22.0)),
    ("arm_r", "clavicle_r", (-7.0, 0.0, 22.0), (-16.0, 0.0, 18.0)),
    ("hand_r", "arm_r", (-16.0, 0.0, 18.0), (-21.0, 0.0, 15.0)),
    ("thigh_l", "root", (4.0, 0.0, 0.0), (4.0, 0.0, -18.0)),
    ("calf_l", "thigh_l", (4.0, 0.0, -18.0), (4.0, 0.0, -34.0)),
    ("thigh_r", "root", (-4.0, 0.0, 0.0), (-4.0, 0.0, -18.0)),
    ("calf_r", "thigh_r", (-4.0, 0.0, -18.0), (-4.0, 0.0, -34.0)),
]


def _rig() -> bpy.types.Object:
    bpy.ops.object.armature_add(enter_editmode=True)
    armature = bpy.context.object
    armature.name = "map_rig"
    edit = armature.data.edit_bones
    for name, parent, head, tail in BONES:
        bone = edit.get(name) or edit.new(name)
        bone.head = head
        bone.tail = tail
        bone.parent = edit.get(parent) if parent else None
    for stale in [bone for bone in edit if bone.name not in {item[0] for item in BONES}]:
        edit.remove(stale)
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def main() -> int:
    dmf.register()
    armature = _rig()
    settings = bpy.context.scene.dmf
    settings.target_armature = armature
    settings.show_bone_map = True
    settings.bone_map_plane = "FRONT"
    settings.bone_map_labels = True
    count = dmf.workbench.build_hierarchy(settings)
    settings.hierarchy_index = dmf.workbench.hierarchy_index(settings, "head")

    context = _Context(bpy.context.scene)
    placed = hierarchy_view.placed_for(context, settings, context.region)
    if not placed:
        raise RuntimeError("the map placed no bones")

    gpu.init()
    offscreen = gpu.types.GPUOffScreen(WIDTH, HEIGHT)
    with offscreen.bind():
        gpu.state.viewport_set(0, 0, WIDTH, HEIGHT)
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        hierarchy_view._fill(
            [(0.0, 0.0), (WIDTH, 0.0), (WIDTH, HEIGHT), (0.0, HEIGHT)],
            (0.09, 0.10, 0.12, 1.0),
        )
        hierarchy_view._draw(context)
        pixels = offscreen.texture_color.read()
    offscreen.free()

    # texture_color.read() hands back a row-strided buffer; image.pixels wants flat RGBA.
    image = bpy.data.images.new("bone_map_probe", WIDTH, HEIGHT, alpha=True)
    image.pixels.foreach_set(numpy.asarray(pixels, dtype=numpy.float32).ravel())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.filepath_raw = str(OUT)
    image.file_format = "PNG"
    image.save()

    print(f"MAP_RENDER bones={count} placed={len(placed)} out={OUT}")
    print(f"MAP_RENDER draw_error={settings.bone_map_error!r}")
    print(f"MAP_RENDER head_head={placed['head'].head} neck=head ")
    print(f"MAP_RENDER selected={settings.hierarchy[settings.hierarchy_index].name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
