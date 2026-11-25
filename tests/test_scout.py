from pathlib import Path

import pytest

from forge import live, scout

ROSTER = """
{
\thero_base =
\t{
\t\tm_strModelName = resource_name:"models/heroes_staging/base/base.vmdl"
\t}
\thero_haze =
\t{
\t\tm_nComplexity = 2
\t\tm_strModelName = resource_name:"models/heroes_staging/haze/haze.vmdl"
\t}
\thero_frank =
\t{
\t\tm_strModelName = resource_name:"models/heroes_wip/frank/frank.vmdl"
\t}
}
"""

GRAPH = """<!-- kv3 -->
{
\tm_variationID = "Biped"
\tm_skeleton = resource:"models/biped/biped.vnmskel"
\tm_persistentNodeIndices =
\t[
\t\t0, 1, 2,
\t\t3,
\t]
\tm_nRootNodeIdx = 4
\tm_nodes =
\t[
\t\t{ m_sequence = resource:"models/biped/idle.dmx" }
\t\t{ m_sequence = resource:"models/biped/run.dmx" }
\t]
}
"""


def test_hero_table_scans_entries_and_digest(tmp_path):
    path = tmp_path / "heroes.vdata"
    path.write_text(ROSTER, encoding="utf-8")
    table = scout.read_hero_table(path)
    assert [hero.slug for hero in table.heroes] == ["frank", "haze"]
    assert table.heroes[0].model_path.endswith("frank.vmdl_c")
    assert table.bytes == path.stat().st_size
    assert table.blake3 == scout.blake3_file(path)


def test_hero_table_refuses_an_empty_document(tmp_path):
    path = tmp_path / "heroes.vdata"
    path.write_text("{\n}\n", encoding="utf-8")
    with pytest.raises(scout.ScoutError) as error:
        scout.read_hero_table(path)
    assert str(error.value).startswith("hero-table-empty")


def test_drift_names_added_removed_and_moved():
    mod = tuple(live.parse_hero_roster(ROSTER))
    live_text = ROSTER.replace(
        'models/heroes_staging/haze/haze.vmdl', 'models/heroes_staging/haze/haze_v2.vmdl'
    ).replace("hero_frank", "hero_ivy")
    current = tuple(live.parse_hero_roster(live_text))
    row = scout.drift(mod, current)
    assert row.added == ("ivy",)
    assert row.removed == ("frank",)
    assert row.moved[0]["slug"] == "haze"
    assert row.moved[0]["live"].endswith("haze_v2.vmdl_c")


def test_scan_sources_counts_mesh_and_animation_smd(tmp_path):
    (tmp_path / "scout.qc").write_text("$modelname \"player/scout.mdl\"\n", encoding="utf-8")
    (tmp_path / "scout.mdl").write_bytes(b"\0")
    (tmp_path / "scout_anims").mkdir()
    (tmp_path / "scout_anims" / "ref.smd").write_text("", encoding="utf-8")
    (tmp_path / "scout_anims" / "run.smd").write_text("", encoding="utf-8")
    (tmp_path / "scout_body.smd").write_text("", encoding="utf-8")
    (tmp_path / "scout.blend").write_bytes(b"\0")
    sources = scout.scan_sources(tmp_path)
    assert sources.qc == "scout.qc"
    assert sources.mdl == "scout.mdl"
    assert sources.smd == 1
    assert sources.anim_smd == 2
    assert sources.anim_dirs == ("scout_anims",)
    assert sources.blends == ("scout.blend",)


def test_scan_sources_refuses_a_missing_workspace(tmp_path):
    with pytest.raises(scout.ScoutError) as error:
        scout.scan_sources(tmp_path / "absent")
    assert str(error.value).startswith("workspace-missing")


def test_retarget_graph_replaces_two_fields_and_keeps_structure(tmp_path):
    path = tmp_path / "hero.vnmgraph"
    path.write_text(GRAPH, encoding="utf-8")
    before = scout.graph_summary(path)
    body = scout.retarget_graph(
        GRAPH,
        variation="Scout",
        skeleton="models/heroes_wip/frank/dmx/mesh/frank_skel.dmx",
        label="unit",
    )
    out = tmp_path / "hero.vnmgraph+scout.vnmgraph"
    out.write_text(body, encoding="utf-8")
    after = scout.graph_summary(out)
    assert after.variation == "Scout"
    assert after.skeleton.endswith("frank_skel.dmx")
    assert after.nodes == before.nodes == 5
    assert after.clips == before.clips
    assert out.read_text(encoding="utf-8").startswith("// retargeted by deadlock-model-forge: unit")


def test_retarget_graph_refuses_an_ambiguous_field():
    doubled = GRAPH.replace('m_variationID = "Biped"', 'm_variationID = "Biped"\n\tm_variationID = "Other"')
    with pytest.raises(scout.ScoutError) as error:
        scout.retarget_graph(doubled, variation="Scout", skeleton="models/x.vnmskel")
    assert str(error.value).startswith("graph-variation-field-ambiguous")


def test_retarget_graph_refuses_empty_values():
    with pytest.raises(scout.ScoutError) as error:
        scout.retarget_graph(GRAPH, variation="  ", skeleton="models/x.vnmskel")
    assert str(error.value).startswith("graph-variation-empty")
    with pytest.raises(scout.ScoutError) as error:
        scout.retarget_graph(GRAPH, variation="Scout", skeleton="")
    assert str(error.value).startswith("graph-skeleton-empty")


def test_dota_tools_reads_compiler_and_graphs(tmp_path):
    (tmp_path / "game/bin/win64").mkdir(parents=True)
    (tmp_path / "game/bin/win64/resourcecompiler.exe").write_bytes(b"\0")
    graphs = tmp_path / "content/dota_addons/animgraph/animgraphs"
    graphs.mkdir(parents=True)
    (graphs / "biped_standard.vanmgrph").write_text(GRAPH, encoding="utf-8")
    tools = scout.dota_tools(tmp_path)
    assert tools.compiler.is_file()
    assert [path.name for path in tools.graphs] == ["biped_standard.vanmgrph"]


def test_dota_tools_refuses_a_tree_without_a_compiler(tmp_path):
    with pytest.raises(scout.ScoutError) as error:
        scout.dota_tools(tmp_path)
    assert str(error.value).startswith("dota-tools-no-compiler")


def _dota19(sequences, model="models/biped_standard/biped_standard.vmdl"):
    nodes = "".join(
        "\t\t\t{\n\t\t\t\tkey =\n\t\t\t\t{\n\t\t\t\t\tm_id = " + str(index) + "\n\t\t\t\t}\n"
        "\t\t\t\tvalue =\n\t\t\t\t{\n\t\t\t\t\tm_sequenceName = \"" + name + "\"\n\t\t\t\t}\n\t\t\t}\n"
        for index, name in enumerate(sequences, start=1)
    )
    return (
        '<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} format:animgraph19:version{0adb35b7} -->\n'
        "{\n\t_class = \"CAnimationGraph\"\n\tm_nodeManager =\n\t{\n\t\tm_nodes =\n\t\t[\n"
        + nodes
        + "\t\t]\n\t}\n\tm_modelName = \"" + model + "\"\n}\n"
    )


def test_retarget_sequences_fills_the_graph_slots_from_the_port():
    text = _dota19(["walkn", "walkn", "idle", "turn_left_90"])
    body, plan = scout.retarget_sequences(
        text, model="models/heroes_wip/frank/frank.vmdl", sequences=("PRIMARY_aimmatrix_run", "PRIMARY_aimmatrix_idle", "AttackStand_PRIMARY")
    )
    assert plan["slots"] == 3
    assert plan["occurrences"] == 4  # the repeat keeps its slot's name
    assert plan["mapping"] == {
        "walkn": "PRIMARY_aimmatrix_run",
        "idle": "PRIMARY_aimmatrix_idle",
        "turn_left_90": "AttackStand_PRIMARY",
    }
    assert body.count('m_sequenceName = "walkn"') == 0
    assert body.count('m_sequenceName = "PRIMARY_aimmatrix_run"') == 2
    assert 'm_modelName = "models/heroes_wip/frank/frank.vmdl"' in body
    assert scout.sequence_names(body) == ("AttackStand_PRIMARY", "PRIMARY_aimmatrix_idle", "PRIMARY_aimmatrix_run")


def test_retarget_sequences_refuses_a_port_with_too_few_names():
    text = _dota19(["walkn", "idle"])
    with pytest.raises(scout.ScoutError) as error:
        scout.retarget_sequences(text, sequences=("only_one",))
    assert str(error.value).startswith("animgraph-sequences-short")


def test_retarget_sequences_refuses_a_document_that_is_not_animgraph19():
    with pytest.raises(scout.ScoutError) as error:
        scout.retarget_sequences("{\n\tm_variationID = \"Kelvin\"\n}\n", sequences=("a",))
    assert str(error.value).startswith("graph-schema-not-animgraph19")


def _fused_doc():
    return (
        '<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} format:generic:version{7412167c} -->\n'
        "{\n\tm_pRootGraph =\n\t{\n\t\tm_nodes =\n\t\t[\n\t\t\t{\n\t\t\t\tm_pDefaultVariationData =\n\t\t\t\t{\n"
        '\t\t\t\t\tm_clip = "models/heroes_staging/kelvin_v2/clip/aim_idle.vnmclip"\n\t\t\t\t}\n'
        "\t\t\t\tm_overrides =\n\t\t\t\t[\n\t\t\t\t\t{\n"
        '\t\t\t\t\t\tm_variationID = "abrams"\n\t\t\t\t\t\tm_pData =\n\t\t\t\t\t\t{\n'
        '\t\t\t\t\t\t\tm_clip = "models/heroes_wip/abrams/clips/aim_weapon_idle.vnmclip"\n'
        "\t\t\t\t\t\t}\n\t\t\t\t\t},\n\t\t\t\t]\n\t\t\t},\n\t\t]\n\t}\n"
        "\tm_variationHierarchy =\n\t{\n\t\tm_variations =\n\t\t[\n\t\t\t{\n\t\t\t\tm_ID = \"Default\"\n"
        '\t\t\t\tm_parentID = ""\n\t\t\t\tm_skeleton = "models/heroes_staging/kelvin_v2/maya/kelvin.vnmskel"\n\t\t\t},\n'
        "\t\t\t{\n\t\t\t\tm_ID = \"abrams\"\n\t\t\t\tm_parentID = \"Default\"\n"
        '\t\t\t\tm_skeleton = "models/heroes_wip/abrams/abrams.vnmskel"\n\t\t\t},\n\t\t]\n\t}\n}\n'
    )


def test_add_variation_overrides_clones_each_pose_node_and_the_hierarchy():
    body, plan = scout.add_variation_overrides(
        _fused_doc(),
        target="Scout",
        skeleton="models/heroes_wip/frank/frank.vnmskel",
        clip_to="models/heroes_wip/frank/clips",
    )
    assert plan["nodes"] == 1 and plan["inserted"] == 1
    assert plan["nodes_without_overrides"] == 0
    assert 'm_variationID = "Scout"' in body
    assert 'm_clip = "models/heroes_wip/frank/clips/aim_weapon_idle.vnmclip"' in body
    assert 'm_ID = "Scout"' in body
    assert 'm_skeleton = "models/heroes_wip/frank/frank.vnmskel"' in body
    # The default data keeps the base hero's clip; only the override moves.
    assert 'm_clip = "models/heroes_staging/kelvin_v2/clip/aim_idle.vnmclip"' in body
    assert body.count("m_overrides") == 1 and body.count("m_variations") == 1


def test_add_variation_overrides_refuses_a_hero_that_is_already_there():
    with pytest.raises(scout.ScoutError) as error:
        scout.add_variation_overrides(_fused_doc(), target="abrams")
    assert str(error.value).startswith("variation-already-present")


def test_port_sequences_are_read_from_the_qc(tmp_path):
    (tmp_path / "scout_animations.qc").write_text(
        '$modelname "player/scout_animations.mdl"\n'
        '$sequence "PRIMARY_aimmatrix_idle" {\n\t"a.smd"\n}\n'
        '$sequence "PRIMARY_aimmatrix_run" {\n\t"b.smd"\n}\n'
        '$sequence "PRIMARY_aimmatrix_idle" {\n\t"c.smd"\n}\n',
        encoding="utf-8",
    )
    assert scout.port_sequences(tmp_path) == ("PRIMARY_aimmatrix_idle", "PRIMARY_aimmatrix_run")


def test_graph_summary_reads_the_dota_authored_schema(tmp_path):
    dota = (
        '<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} format:animgraph19:version{0adb35b7} -->\n'
        "{\n\t_class = \"CAnimationGraph\"\n\tm_nodeManager =\n\t{\n\t\tm_nodes =\n\t\t[\n"
        "\t\t\t{\n\t\t\t\tkey =\n\t\t\t\t{\n\t\t\t\t\tm_id = 1\n\t\t\t\t}\n"
        "\t\t\t\tvalue =\n\t\t\t\t{\n\t\t\t\t\tm_sequenceName = \"walkn\"\n\t\t\t\t}\n\t\t\t}\n"
        "\t\t\t{\n\t\t\t\tkey =\n\t\t\t\t{\n\t\t\t\t\tm_id = 2\n\t\t\t\t}\n"
        "\t\t\t\tvalue =\n\t\t\t\t{\n\t\t\t\t\tm_sequenceName = \"idle\"\n\t\t\t\t}\n\t\t\t}\n"
        "\t\t]\n\t}\n}\n"
    )
    path = tmp_path / "biped_standard.vanmgrph"
    path.write_text(dota, encoding="utf-8")
    graph = scout.graph_summary(path)
    assert graph.schema == "animgraph19"
    assert graph.nodes == 2
    assert graph.variation == ""
    assert graph.sequences == ("idle", "walkn")
    with pytest.raises(scout.ScoutError) as error:
        scout.retarget_graph(dota, variation="Scout", skeleton="models/x.vnmskel")
    assert str(error.value).startswith("graph-schema-not-retargetable")


def test_sequence_names_are_read_from_the_graph():
    graph = GRAPH + '\n\t\t\t\t\tm_sequenceName = "walkn"\n\t\t\t\t\tm_sequenceName = "WalkN"\n'
    assert scout.sequence_names(graph) == ("WalkN", "walkn")


def test_bind_sequences_matches_through_case_and_prefix_noise():
    binding = scout.bind_sequences(
        ("walkn", "turn_left_90", "taunt_scout"),
        ("WalkN", "@turn_left_90_corrective_animation", "run_primary"),
    )
    assert binding["graph_sequences"] == 3
    assert binding["bound"] == 2
    assert binding["unbound"] == ["taunt_scout"]
    assert binding["rows"][0]["source"] == "WalkN"


def test_source_sequences_reads_only_animation_folders(tmp_path):
    (tmp_path / "scout_anims").mkdir()
    (tmp_path / "scout_anims" / "run_primary.smd").write_text("", encoding="utf-8")
    (tmp_path / "scout_body.smd").write_text("", encoding="utf-8")
    assert scout.source_sequences(tmp_path) == ("run_primary",)


def test_popit_surface_carries_its_contract():
    ui = Path(__file__).resolve().parents[1] / "tools" / "scout_ui"
    page = (ui / "index.html").read_text(encoding="utf-8")
    for needle in (
        'data-popit="scout-update"',
        'id="port-state"',
        'id="drift-table"',
        'id="graph-clips"',
        'id="sequence-coverage"',
    ):
        assert needle in page
    css = (ui / "popit.css").read_text(encoding="utf-8")
    assert "--ground: #0c0e11" in css
    assert "--attention: #f0c454" in css
    script = (ui / "popit.js").read_text(encoding="utf-8")
    assert 'fetch("/report.json"' in script
    assert "textContent" in script
