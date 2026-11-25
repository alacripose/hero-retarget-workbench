"""Motion is measured, not assumed: channel spread from the document, translation carried by the bake."""
from __future__ import annotations

import math

from forge import clipbake, portskel
from tools.scout_variance import stats


def _joints():
    return [
        portskel.Joint(name="root", parent=-1, position=(0.0, 1.0, 0.0), rotation=(0.0, 0.0, 0.0), children=(1,)),
        portskel.Joint(name="spine", parent=0, position=(0.0, 2.0, 0.0), rotation=(0.0, 0.0, 0.0), children=()),
    ]


def test_stats_separates_a_moving_channel_from_a_held_one():
    moving = {
        "name": "spine_o",
        "joint": "spine",
        "suffix": "_o",
        "times": [0.0, 0.0333, 0.0666],
        "values": [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, math.sin(0.15), math.cos(0.15)), (0.0, 0.0, math.sin(0.3), math.cos(0.3))],
    }
    held = {**moving, "name": "root_o", "joint": "root", "values": [moving["values"][0]] * 3}
    moved = stats(moving)
    still = stats(held)
    assert moved["moving"] and moved["distinct"] == 3
    assert moved["spread"] > 1.0 and moved["unit"] == "deg"
    assert not still["moving"] and still["distinct"] == 1 and still["spread"] == 0.0


def test_bake_writes_the_position_series_and_holds_an_unbaked_joint(tmp_path):
    joints = _joints()
    template = portskel.write_clip_template(joints, tmp_path / "template.dmx").read_text(encoding="utf-8")
    positions = {"spine": [(0.0, 2.0, 0.0), (0.0, 2.5, 0.25), (0.0, 3.0, 0.5)]}
    body, report = clipbake.bake_kv2(
        template,
        samples={"spine": [(0.0, 0.0, 0.0, 1.0)] * 3},
        positions=positions,
        times=[0.0, 0.0333, 0.0666],
        duration=0.0666,
    )
    assert report["positions_baked"] == ["spine"]
    assert report["positions_held"] == ["root"]
    assert '"0.000000 2.500000 0.250000"' in body
    assert '"0 1 0"' in body, "root holds the template's rest position"
    assert body.count('"vector3_array"') == 2
