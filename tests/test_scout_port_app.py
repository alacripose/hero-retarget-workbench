"""The Scout Port application's mesh step: converted, partial, and unconverted, read from real files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "popit_apps" / "scout_port"
for entry in (str(APP), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import server  # noqa: E402
from forge import meshbuild  # noqa: E402
from forge.portskel import Joint, write_skeleton_dmx  # noqa: E402

OBJ = """# synthetic port mesh
o scout_body
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 0.0 1.0 0.0
v 0.0 0.0 1.0
f 1 2 3
f 1 2 4
"""


def _port(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "scout.mdl").write_bytes(b"IDST" + b"\0" * 64)
    (tmp_path / "scout.vvd").write_bytes(b"IDSV" + b"\0" * 32)
    (tmp_path / "scout.dx90.vtx").write_bytes(b"IDSV" + b"\0" * 16)
    (tmp_path / "scout.obj").write_text(OBJ, encoding="utf-8")
    textures = tmp_path / "scout"
    textures.mkdir()
    (textures / "scout_blue.vtf").write_bytes(b"VTF\0")
    (textures / "scout_head.vtf").write_bytes(b"VTF\0")
    return tmp_path


def _converted(tmp_path: Path) -> Path:
    """A produced mesh tree built by the converter itself, then read back by the app."""
    skeleton_path = tmp_path / "skel" / "scout_skel.dmx"
    joints = [
        Joint(name="bip_pelvis", parent=-1, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), children=(1,)),
        Joint(name="bip_spine_0", parent=0, position=(0.0, 0.0, 10.0), rotation=(0.0, 0.0, 0.0), children=()),
    ]
    write_skeleton_dmx(joints, skeleton_path)
    mesh = meshbuild.ObjMesh(
        positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        normals=[],
        texcoords=[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
        faces=[("scout_red", [(0, 0, -1), (1, 1, -1), (2, 2, -1)])],
    )
    loaded = meshbuild.read_skeleton(skeleton_path)
    world = meshbuild.world_positions(loaded)
    weights = meshbuild.solve_weights(mesh.positions, loaded, world)
    produced = tmp_path / "produced"
    meshbuild.write_mesh_dmx(produced / meshbuild.MESH_DMX, mesh, loaded, weights)
    meshbuild.write_model(produced / meshbuild.MODEL_VMDL)
    materials = produced / meshbuild.MODEL_ROOT / "materials"
    materials.mkdir(parents=True, exist_ok=True)
    for index in range(15):
        (materials / f"scout_{index}.vmt").write_text('"VertexLitGeneric" { }\n', encoding="utf-8")
        (materials / f"scout_{index}.vmat").write_text('Layer0 { shader "pbr.vfx" }\n', encoding="utf-8")
    return produced


def test_converted_state_reads_counts_from_the_produced_files(tmp_path):
    produced = _converted(tmp_path)
    state = server.mesh_state(workspace=_port(tmp_path / "port"), root=produced)
    assert state["state"] == "converted"
    assert state["refusal"] == ""
    assert state["counts"]["vertices"] == 3
    assert state["counts"]["faces"] == 1
    assert state["counts"]["joints"] == 2
    assert state["counts"]["vmt"] == 15 and state["counts"]["vmat"] == 15
    assert state["counts"]["dmx_bytes"] == Path(state["path"]).stat().st_size


def test_partial_state_names_what_is_missing(tmp_path):
    produced = _converted(tmp_path)
    materials = produced / meshbuild.MODEL_ROOT / "materials"
    (materials / "scout_0.vmt").unlink()
    (materials / "scout_1.vmt").unlink()
    state = server.mesh_state(workspace=_port(tmp_path / "port"), root=produced)
    assert state["state"] == "partial"
    assert state["refusal"] == "mesh-partial"
    assert "2 .vmt" in state["detail"]
    assert state["counts"]["vertices"] == 3


def test_sources_without_conversion_still_refuse_by_name(tmp_path):
    state = server.mesh_state(workspace=_port(tmp_path), root=tmp_path / "nothing")
    assert state["state"] == "ready"
    assert state["refusal"] == "mesh-not-converted"
    assert state["counts"]["vertices"] == 0
    assert state["counts"]["mdl_bytes"] > 0


def test_empty_workspace_refuses_mesh_not_built(tmp_path):
    state = server.mesh_state(workspace=tmp_path, root=tmp_path / "nothing")
    assert state["state"] == "blocked"
    assert state["refusal"] == "mesh-not-built"


def _clip_row(frames: int, channels: int = 156) -> dict:
    return {
        "ok": True,
        "channels": channels,
        "suffixes": {"_p": channels // 2, "_o": channels // 2},
        "track_joints": 78,
        "skeleton_joints": 78,
        "frames": frames,
        "duration": frames / 30.0,
    }


def test_clips_converted_reads_each_parsed_row(tmp_path):
    for name, frames in zip(server.ANIM_CLIPS, (21, 20, 2, 2)):
        (tmp_path / f"{name}.json").write_text(json.dumps(_clip_row(frames)), encoding="utf-8")
    state = server.clips_state(tmp_path)
    assert state["state"] == "pass"
    assert state["refusal"] == ""
    assert state["counts"] == {"clips": 4, "channels": 156, "joints": 78, "frames": "21/20/2/2"}


def test_clips_partial_names_the_missing_clip(tmp_path):
    for name, frames in zip(server.ANIM_CLIPS[:3], (21, 20, 2)):
        (tmp_path / f"{name}.json").write_text(json.dumps(_clip_row(frames)), encoding="utf-8")
    state = server.clips_state(tmp_path)
    assert state["state"] == "partial"
    assert state["refusal"] == "clips-partial"
    assert "Scout_AimRun" in state["detail"]
    assert state["counts"]["clips"] == 3


def test_clips_absent_refuses_by_name(tmp_path):
    state = server.clips_state(tmp_path)
    assert state["state"] == "ready"
    assert state["refusal"] == "clips-not-converted"
    assert state["counts"]["clips"] == 0


def test_live_mesh_step_is_converted_and_downstream_stays_refused():
    steps = {step["id"]: step for step in server.state()["steps"]}
    mesh = steps["mesh"]
    assert mesh["state"] == "converted"
    assert mesh["refusal"] == ""
    assert mesh["counts"]["vertices"] == 8261
    assert mesh["counts"]["faces"] == 7814
    assert mesh["counts"]["joints"] == 78
    pack = steps["pack"]
    assert pack["state"] == "pass", pack["detail"]
    assert pack["counts"]["files"] > 0
    assert pack["counts"]["vpk_entries"] > 0
    assert pack["counts"]["dmx"] == 4
    hero = steps["hero"]
    assert hero["state"] == "pass", hero["detail"]
    assert hero["refusal"] == ""
    assert hero["counts"]["paths"] > 0
    assert hero["counts"]["resolved"] == hero["counts"]["paths"]
    assert hero["counts"]["ui_paths"] >= 3
    assert hero["counts"]["ui_resolved"] == hero["counts"]["ui_paths"]
    assert hero["counts"]["maps"] == 3
    assert hero["counts"]["graph_matches_compiled"] is True
    assert hero["binding"]["form"] == "standalone"
    assert hero["binding"]["refusal"] == "ag2-hero-variation-required"
    assert steps["in_game"]["refusal"] == "not-observed"


def test_live_clips_and_graph_read_parsed_counts():
    steps = {step["id"]: step for step in server.state()["steps"]}
    clips = steps["clips"]
    assert clips["state"] == "pass", clips["detail"]
    assert clips["counts"] == {"clips": 4, "channels": 156, "joints": 78, "frames": "21/20/2/2"}
    graph = steps["graph"]
    assert graph["state"] == "pass", graph["detail"]
    assert graph["counts"]["clips"] == 4
    assert graph["counts"]["motion_states"] == 2
    assert graph["counts"]["aim_poses"] == 2
