"""Clip discovery: the DMX half is editable, the vnmclip half is opaque."""
from __future__ import annotations

from pathlib import Path

from forge import clips


def _write(folder: Path, name: str, size: int = 16) -> Path:
    path = folder / name
    path.write_bytes(b"\0" * size)
    return path


def test_classify_reads_the_kind_and_the_compiled_marker():
    assert clips.classify(Path("walk.dmx")) == ("dmx", False)
    assert clips.classify(Path("walk.vnmclip")) == ("vnmclip", False)
    assert clips.classify(Path("walk.vnmclip_c")) == ("vnmclip", True)
    assert clips.classify(Path("hero.vnmskel_c")) == ("vnmskel", True)
    assert clips.classify(Path("notes.txt")) is None


def test_scan_pairs_dmx_and_vnmclip_and_reports_the_counts(tmp_path: Path):
    _write(tmp_path, "walk_lower_L.dmx")
    _write(tmp_path, "walk_lower_L.vnmclip")
    _write(tmp_path, "idle.dmx")
    _write(tmp_path, "idle.vnmclip_c")
    _write(tmp_path, "hero.vnmskel_c")
    _write(tmp_path, "readme.txt")

    rows = clips.scan(tmp_path)
    assert [row.name for row in rows] == [
        "hero.vnmskel_c",
        "idle.dmx",
        "idle.vnmclip_c",
        "walk_lower_L.dmx",
        "walk_lower_L.vnmclip",
    ]
    counts = clips.summary(rows)
    assert counts["total"] == 5
    assert counts["dmx"] == 2
    assert counts["vnmclip"] == 2
    assert counts["compiled"] == 2
    assert counts["editable"] == 2
    assert counts["paired"] == 2
    assert counts["dmx_only"] == 0


def test_scan_reads_subfolders_and_sorts_by_label(tmp_path: Path):
    nested = tmp_path / "anims" / "hero"
    nested.mkdir(parents=True)
    _write(nested, "jump.dmx")
    _write(tmp_path, "attack.dmx")
    assert [row.label for row in clips.scan(tmp_path)] == ["attack", "jump"]


def test_a_missing_folder_is_empty_not_an_error(tmp_path: Path):
    assert clips.scan(tmp_path / "nope") == []
    assert clips.summary([])["total"] == 0


def test_compiled_clip_keeps_the_label_of_its_source():
    clip = clips.Clip(
        name="walk.vnmclip_c",
        path=Path("walk.vnmclip_c"),
        kind="vnmclip",
        compiled=True,
        size=10,
    )
    assert clip.label == "walk"
    assert not clip.editable


def test_editable_lists_only_decompiled_dmx(tmp_path: Path):
    _write(tmp_path, "a.dmx")
    _write(tmp_path, "a.vnmclip_c")
    _write(tmp_path, "b.dmx")
    names = [row.name for row in clips.editable(clips.scan(tmp_path))]
    assert names == ["a.dmx", "b.dmx"]


def test_pairs_puts_the_dmx_beside_the_vnmclip_it_replaces(tmp_path: Path):
    _write(tmp_path, "idle.dmx")
    _write(tmp_path, "idle.vnmclip_c")
    paired = clips.pairs(clips.scan(tmp_path))
    assert set(paired["idle"]) == {"dmx", "vnmclip"}
    assert paired["idle"]["vnmclip"].compiled


def test_the_real_extraction_corpus_scans_without_a_vnmclip_reader():
    """The owner's own corpus: many pairs, and no file is parsed to count them."""
    folder = Path(__file__).resolve().parents[1] / "artifacts"
    rows = clips.scan(folder, recursive=False)
    if not rows:
        return  # the corpus is evidence, not a fixture; absent is not a failure
    counts = clips.summary(rows)
    assert counts["dmx"] > 0 and counts["vnmclip"] > 0
    assert counts["editable"] == counts["dmx"]


def test_export_folder_never_writes_over_the_extraction(tmp_path: Path):
    assert clips.export_folder(tmp_path) == tmp_path / "edited"
    assert clips.export_folder(tmp_path, "D:/written") == Path("D:/written")
    assert clips.export_folder(None) is None
    assert clips.export_folder(None, tmp_path) == tmp_path


def test_written_path_is_the_anims_layout_a_clip_is_compiled_from(tmp_path: Path):
    assert clips.written_path(tmp_path, "walk_lower_L") == tmp_path / "anims" / "walk_lower_L.dmx"
    assert clips.written_path(tmp_path, "walk_lower_L", "AG2") == tmp_path / "clips" / "walk_lower_L.dmx"


def test_animgraph_reads_the_folder_without_parsing_a_clip(tmp_path: Path):
    ag2 = tmp_path / "hero" / "clips" / "walk.dmx"
    ag1 = tmp_path / "hero" / "anims" / "walk.dmx"
    compiled = tmp_path / "hero" / "walk.vnmclip_c"
    for path in (ag2, ag1, compiled):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\0")
    skeleton = tmp_path / "hero" / "hero.vnmskel"
    skeleton.write_bytes(b"\0")
    assert clips.animgraph(ag2, [tmp_path], skeleton) == "AG2"
    assert clips.animgraph(ag2, [tmp_path], None) == "AG2"
    assert clips.animgraph(ag1, [tmp_path], skeleton) == "AG1"
    assert clips.animgraph(compiled, [tmp_path], skeleton) == "AG2"
    assert clips.animgraph(tmp_path / "loose.dmx", [tmp_path], None) == "UNKNOWN"


def test_clip_roots_find_the_clips_and_anims_folders(tmp_path: Path):
    clips_dir = tmp_path / "models" / "hero" / "clips"
    anims_dir = tmp_path / "models" / "hero" / "anims"
    clips_dir.mkdir(parents=True)
    anims_dir.mkdir(parents=True)
    assert set(clips.clip_roots(tmp_path)) == {clips_dir, anims_dir}
    skeleton = tmp_path / "models" / "hero" / "hero.vnmskel"
    skeleton.write_bytes(b"\0")
    assert clips.find_vnmskel([tmp_path]) == skeleton


def test_glob_escape_matches_one_action_name_and_no_others():
    from fnmatch import fnmatch

    assert clips.glob_escape("walk_lower_L") == "walk_lower_L"
    escaped = clips.glob_escape("walk*")
    assert escaped == "walk[*]"
    assert fnmatch("walk*", escaped)
    assert not fnmatch("walk_lower_L", escaped)
    assert not fnmatch("idle", clips.glob_escape("idle?")[:4] + "[?]")
    assert fnmatch("a[b", clips.glob_escape("a[b"))
