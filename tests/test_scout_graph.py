"""The authored Scout AnimGraph 2: structure from the live schema, content from the port only."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import scoutgraph  # noqa: E402

SKELETON = "models/heroes_wip/scout/scout.vnmskel"
CLIPS = {
    "Scout_Attack": "models/heroes_wip/scout/clips/Scout_Attack.vnmclip",
    "Scout_Reload": "models/heroes_wip/scout/clips/Scout_Reload.vnmclip",
    "Scout_AimIdle": "models/heroes_wip/scout/clips/Scout_AimIdle.vnmclip",
    "Scout_AimRun": "models/heroes_wip/scout/clips/Scout_AimRun.vnmclip",
}


def _graph() -> dict:
    return scoutgraph.build_scout_graph(
        variation="Default", skeleton=SKELETON, clips=CLIPS, states=["Scout_Attack", "Scout_Reload"]
    )


def test_graph_uses_only_port_clips_and_skeleton():
    text = scoutgraph.dump(_graph())
    assert "frank" not in text.lower()
    for clip in CLIPS.values():
        assert f'm_clip = "{clip}"' in text
    assert f'm_skeleton = "{SKELETON}"' in text
    assert text.count('m_clip = "') == 4


def test_motion_clips_are_states_and_aim_clips_are_named_poses():
    text = scoutgraph.dump(_graph())
    assert '"state_Scout_Attack"' in text and '"state_Scout_Reload"' in text
    assert '"aim_state_Scout_AimIdle"' in text and '"aim_state_Scout_AimRun"' in text
    # The pose nodes inside the aim states carry the aim names the compiled graph is verified against.
    assert text.count('"aim_Scout_AimIdle"') >= 1 and text.count('"aim_Scout_AimRun"') >= 1


def test_state_machine_carries_the_slots_the_loader_dereferences():
    machine = _graph()["m_pRootGraph"]["m_nodes"][0]
    child = machine["m_pChildGraph"]
    assert child["m_graphType"] == "StateMachine"
    assert child["m_entryStateID"] == child["m_nodes"][0]["m_ID"]
    classes = [node["_class"] for node in child["m_nodes"]]
    assert "CNmGraphDocEntryStateOverrideConduitNode" in classes
    # Without the global transition conduit the compiler access-violates instead of reporting.
    assert "CNmGraphDocGlobalTransitionConduitNode" in classes
    state = child["m_nodes"][0]
    assert state["m_pSecondaryGraph"]["m_nodes"][0]["_class"] == "CNmGraphDocStateLayerDataNode"
    assert state["m_type"] == "BlendTreeState"


def test_pose_node_carries_the_fields_the_loader_reads():
    machine = _graph()["m_pRootGraph"]["m_nodes"][0]
    state = machine["m_pChildGraph"]["m_nodes"][0]
    pose = state["m_pChildGraph"]["m_nodes"][0]
    assert pose["_class"] == "CNmGraphDocAnimationPoseNode"
    for key in ("m_defaultResourceName", "m_inputTimeRemapRange", "m_fixedTimeValue", "m_useFramesAsInput"):
        assert key in pose, f"pose node without {key} access-violates the compiler"


def test_kv3_writer_has_no_object_commas_and_no_trailing_array_comma():
    text = scoutgraph.dump({"a": 1.0, "b": {"c": "x"}, "d": [1.0, 2.0], "e": [{"f": 1}]})
    # Object members are newline separated; kv3 objects carry no commas between members.
    assert "1.0,\n" not in text
    assert "[ 1.0, 2.0 ]" in text
    assert not re.search(r"\},\s*\]", text)
    assert text.count("{") == text.count("}")


def test_missing_clip_and_empty_states_refuse_by_name():
    with pytest.raises(scoutgraph.GraphError) as missing:
        scoutgraph.build_scout_graph(
            variation="Default", skeleton=SKELETON, clips=CLIPS, states=["Scout_Missing"]
        )
    assert "graph-clip-missing" in str(missing.value)
    with pytest.raises(scoutgraph.GraphError) as empty:
        scoutgraph.build_scout_graph(variation="Default", skeleton=SKELETON, clips=CLIPS, states=[])
    assert "graph-states-empty" in str(empty.value)
