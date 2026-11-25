"""The port's own skeleton, its clip template, and the binding that makes them one rig."""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import portskel  # noqa: E402

SMD = """version 1
nodes
  0 "pelvis" -1
  1 "spine" 0
  2 "head" 1
end
skeleton
  time 0
    0 0.000000 47.000000 0.000000 0.000000 0.000000 0.000000
    1 0.000000 5.000000 0.000000 0.000000 0.000000 0.000000
    2 0.000000 10.000000 0.000000 0.000000 0.000000 1.570796
end
"""


def _joints(tmp_path: Path) -> list[portskel.Joint]:
    path = tmp_path / "ref.smd"
    path.write_text(SMD, encoding="utf-8")
    return portskel.read_reference(path)


def test_reference_reads_nodes_parents_and_children(tmp_path):
    joints = _joints(tmp_path)
    assert [joint.name for joint in joints] == ["pelvis", "spine", "head"]
    assert [joint.parent for joint in joints] == [-1, 0, 1]
    assert joints[0].children == (1,)
    assert joints[1].children == (2,)
    assert joints[2].children == ()
    assert joints[1].position == (0.0, 5.0, 0.0)


def test_quaternion_matches_the_matrix_the_port_authored():
    # A quarter turn about Z is `(0, 0, sin(pi/4), cos(pi/4))`; the SMD stores radians.
    x, y, z, w = portskel.euler_to_quat(0.0, 0.0, math.pi / 2)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(0.0, abs=1e-9)
    assert z == pytest.approx(math.sqrt(0.5), abs=1e-6)
    assert w == pytest.approx(math.sqrt(0.5), abs=1e-6)


def test_skeleton_dmx_has_one_joint_each_and_one_root(tmp_path):
    joints = _joints(tmp_path)
    path = portskel.write_skeleton_dmx(joints, tmp_path / "skel.dmx")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<!-- dmx encoding keyvalues2 4 format model 22 -->")
    assert text.count('"DmeJoint"') == 3
    assert '"name" "string" "pelvis"' in text
    assert '"upAxis" "int" "3"' in text
    joint_list = text.split('"jointList" "element_array"')[1].split("]")[0]
    assert joint_list.count('"element"') == 3
    assert not re.search(r",\s*$", joint_list.split("[")[-1].rstrip()), "no trailing comma in an element array"
    children = text.split('"children" "element_array"')[1].split("]")[0]
    assert children.count('"element"') == 1, f"one root, got {children!r}"


def test_clip_template_carries_orientation_and_position_channels_per_joint(tmp_path):
    joints = _joints(tmp_path)
    path = portskel.write_clip_template(joints, tmp_path / "template.dmx")
    text = path.read_text(encoding="utf-8")
    for joint in joints:
        assert f'"{joint.name}_o"' in text
        assert f'"{joint.name}_p"' in text
    assert text.count('"toAttribute" "string" "orientation"') == len(joints)
    assert text.count('"toAttribute" "string" "position"') == len(joints)
    assert text.count('"DmeChannel"') == 2 * len(joints)
    assert text.count('"DmeVector3Log"') == len(joints), "a position channel needs a vector log"
    # dmxconvert rejects a trailing comma before the array close, which is how this was found.
    body = text.split('"channels" "element_array"')[1]
    assert not re.search(r"\},\s*\]", body), "channel array must not end with a comma"


def test_vnmskel_names_its_source_root_and_every_bone(tmp_path):
    joints = _joints(tmp_path)
    path = portskel.write_vnmskel(
        tmp_path / "scout.vnmskel",
        source="models/heroes_wip/scout/dmx/mesh/scout_skel.dmx",
        root=joints[0].name,
        bones=[joint.name for joint in joints],
    )
    text = path.read_text(encoding="utf-8")
    assert '_class = "CNmSkeletonDocument"' in text
    assert 'm_sourceFilename = "models/heroes_wip/scout/dmx/mesh/scout_skel.dmx"' in text
    assert 'm_rootBoneName = "pelvis"' in text
    assert text.count('"spine"') >= 2  # high-LOD list and a body mask
    assert 'm_ID = "FullBody"' in text
