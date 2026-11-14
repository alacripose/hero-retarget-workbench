from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.components import ComponentFile, inventory, stage
from forge.migrate import add_component_mesh
from forge.modeldoc import body_groups, render_mesh_files


VMDL = """{
\trootNode =
\t{
\t\t_class = "RootNode"
\t\tchildren =
\t\t[
\t\t\t{
\t\t\t\t_class = "RenderMeshList"
\t\t\t\tchildren = 
\t\t\t\t[
\t\t\t\t\t{
\t\t\t\t\t\t_class = "RenderMeshFile"
\t\t\t\t\t\tname = "body"
\t\t\t\t\t\tfilename = "models/heroes_staging/haze/haze_body.dmx"
\t\t\t\t\t},
\t\t\t\t]
\t\t\t},
\t\t\t{
\t\t\t\t_class = "BoneMarkupList"
\t\t\t\tchildren = [  ]
\t\t\t},
\t\t]
\t}
}
"""


def test_inventory_finds_component_shaped_assets(tmp_path: Path) -> None:
    root = tmp_path / "extraction"
    (root / "models" / "heroes_staging" / "haze").mkdir(parents=True)
    for name in ("haze_body.dmx", "haze_gun1.dmx", "haze_hat.dmx"):
        (root / "models" / "heroes_staging" / "haze" / name).write_bytes(b"dmx")
    found = inventory(root)
    assert sorted(item.name for item in found) == ["haze_gun1.dmx", "haze_hat.dmx"]


def test_stage_copies_files_and_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "haze_hat.dmx"
    source.write_bytes(b"hat")
    file = ComponentFile(
        name=source.name,
        path=source,
        relative="models/heroes_staging/haze/haze_hat.dmx",
        kind="dmx",
        bytes=3,
    )
    manifest = stage([file], tmp_path / "out", addon="my_mod", hero="haze")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["vmdl_merge"] == "not-written"
    assert (tmp_path / "out" / "content" / "citadel_addons" / "my_mod" / file.relative).is_file()


def test_add_component_mesh_writes_render_file_and_bodygroup(tmp_path: Path) -> None:
    vmdl = tmp_path / "haze.vmdl"
    vmdl.write_text(VMDL, encoding="utf-8")
    result = add_component_mesh(
        vmdl,
        mesh_name="haze_hat",
        dmx_relative="models/heroes_staging/haze/haze_hat.dmx",
        bodygroup="headwear",
    )
    assert result["actions"] == {"RenderMeshList": "inserted", "BodyGroupList": "created"}
    assert result["choice"] == "0_#&haze_hat"
    text = vmdl.read_text(encoding="utf-8")
    assert [item.name for item in render_mesh_files(text)] == ["body", "haze_hat"]
    groups = {group.name: group for group in body_groups(text)}
    assert groups["headwear"].meshes == ("haze_hat",)


def test_stage_merges_vmdl_and_records_bodygroup(tmp_path: Path) -> None:
    source = tmp_path / "haze_gun.dmx"
    source.write_bytes(b"gun")
    file = ComponentFile(
        name=source.name,
        path=source,
        relative="models/heroes_staging/haze/haze_gun.dmx",
        kind="dmx",
        bytes=3,
    )
    vmdl = tmp_path / "haze.vmdl"
    vmdl.write_text(VMDL, encoding="utf-8")
    manifest = stage(
        [file],
        tmp_path / "out",
        addon="my_mod",
        hero="haze",
        vmdl=vmdl,
        bodygroup="weapon",
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["vmdl_merge"] == "written"
    assert data["merged"][0]["bodygroup"] == "weapon"
    staged = (tmp_path / "out" / "content" / "citadel_addons" / "my_mod" / file.relative)
    assert staged.read_bytes() == b"gun"
    text = vmdl.read_text(encoding="utf-8")
    assert "haze_gun" in [item.name for item in render_mesh_files(text)]
    assert "body" in [item.name for item in render_mesh_files(text)]


def test_add_component_mesh_refuses_missing_vmdl(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="component-vmdl-missing"):
        add_component_mesh(
            tmp_path / "nope.vmdl",
            mesh_name="gun",
            dmx_relative="models/gun.dmx",
            bodygroup="weapon",
        )
