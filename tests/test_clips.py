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
