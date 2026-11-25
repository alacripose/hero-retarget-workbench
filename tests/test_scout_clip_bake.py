import struct
import zlib

from forge import clipbake, oldmods
from tools import scout_clip_bake

FILES = {
    "animgraphs/hero_aim_scout.vnmgraph+scout.vnmgraph_c": b"variation",
    "animgraphs/scout_loco.vanmgrph_c": b"loco",
    "models/heroes_wip/frank/frank.vnmskel_c": b"skeleton",
    "models/heroes_wip/frank/clips/aim_weapon_crouch.vnmclip_c": b"clip",
}


def test_write_vpk_round_trips_through_the_repo_reader(tmp_path):
    destination = scout_clip_bake.write_vpk(FILES, tmp_path / "scout_animgraph_dir.vpk")

    tree = oldmods.read_vpk(destination)

    assert tree.version == 2
    assert not tree.split
    assert {entry.path for entry in tree.entries} == set(FILES)


def test_write_vpk_data_section_matches_each_entry_crc_and_length(tmp_path):
    destination = scout_clip_bake.write_vpk(FILES, tmp_path / "scout_animgraph_dir.vpk")
    data = destination.read_bytes()
    tree_size = struct.unpack_from("<I", data, 8)[0]
    body = data[28 + tree_size :]

    for entry in oldmods.read_vpk(destination).entries:
        payload = body[entry.offset : entry.offset + entry.length]
        assert payload == FILES[entry.path]
        assert entry.crc == zlib.crc32(payload) & 0xFFFFFFFF


def test_write_vnmclip_names_the_skeleton_and_the_dmx_it_samples(tmp_path):
    document = tmp_path / "aim_weapon_idle.vnmclip"

    clipbake.write_vnmclip(
        document,
        clip_name="aim_weapon_idle",
        skeleton="models/heroes_wip/frank/frank.vnmskel",
        source_dmx="models/heroes_wip/frank/dmx/animation/aim_weapon_idle.dmx",
    )

    text = document.read_text(encoding="utf-8")
    assert "format:generic" in text
    assert '_class = "CNmClipDocument"' in text
    assert 'm_animationSkeletonName = "models/heroes_wip/frank/frank.vnmskel"' in text
    assert 'm_sourceFilename = "models/heroes_wip/frank/dmx/animation/aim_weapon_idle.dmx"' in text


def test_rewrite_array_keeps_no_trailing_comma():
    lines = ['\t\t\t"values"\n', "\t\t\t[\n", '\t\t\t\t"old"\n', "\t\t\t]\n"]

    rewritten = clipbake._rewrite_array(lines, 1, 3, ['"1"', '"2"'])

    body = "".join(rewritten)
    assert '\t\t\t\t"1",\n' in body
    assert '\t\t\t\t"2"\n' in body
    assert '",\n\t\t\t]' not in body


def test_rewrite_array_empties_cleanly_and_leaves_the_brackets():
    lines = ["[\n", '"old"\n', "]\n"]

    rewritten = clipbake._rewrite_array(lines, 0, 2, [])

    assert "".join(rewritten) == "[\n]\n"


def test_plan_rows_counts_loco_slots_and_aim_clips_and_names_the_shortfall():
    rows, missing = clipbake.plan_rows(
        loco_slots=["idle", "no_such_slot"],
        aim_clips=[
            "models/heroes_wip/frank/clips/aim_weapon_idle.vnmclip",
            "models/heroes_wip/frank/clips/unmapped_clip.vnmclip",
        ],
        sequences={
            "idle": "scout_animations_anims/idle.smd",
            "PRIMARY_aimmatrix_idle": "scout_animations_anims/primary_aimmatrix_idle.smd",
        },
    )

    assert [row["name"] for row in rows] == ["idle", "aim_weapon_idle"]
    assert [row["name"] for row in missing] == ["no_such_slot", "unmapped_clip"]
    assert missing[0]["reason"] == "no-source-smd"
    assert missing[1]["reason"] == "no-semantic-source"
    assert rows[1]["source_sequence"] == "PRIMARY_aimmatrix_idle"


def test_summarise_counts_references_apart_from_distinct_clips_and_sources():
    rows = [
        {"name": "aim_weapon_idle", "source_sequence": "PRIMARY_aimmatrix_idle"},
        {"name": "aim_weapon_idle_up", "source_sequence": "PRIMARY_aimmatrix_idle"},
        {"name": "idle", "source_sequence": "PRIMARY_aimmatrix_idle"},
    ]

    summary = clipbake.summarise(rows)

    assert summary["references"] == 3
    assert summary["distinct_clips"] == 3
    assert summary["distinct_sources"] == 1
