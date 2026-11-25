"""The model's own descriptors are decoded, not guessed: stride, labels, frame counts, single poses."""
from __future__ import annotations

import struct

from forge import mdlseq


def _put32(buf: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<i", buf, offset, value)


def _put16(buf: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<h", buf, offset, value)


def _putf(buf: bytearray, offset: int, value: float) -> None:
    struct.pack_into("<f", buf, offset, value)


def _string(buf: bytearray, offset: int, text: str) -> int:
    raw = text.encode("latin-1") + b"\x00"
    buf[offset : offset + len(raw)] = raw
    return offset


def _model(entries: list[dict]) -> bytes:
    """A miniature model in the measured layout: animdesc table 200, sequence table 400, strings 1000."""
    anim_base, seq_base, block_base, string_base = 200, 400, 900, 1000
    buf = bytearray(2000)
    _put32(buf, mdlseq.HEADER_ANIM_COUNT, len(entries))
    _put32(buf, mdlseq.HEADER_ANIM_INDEX, anim_base)
    _put32(buf, mdlseq.HEADER_SEQ_COUNT, len(entries))
    _put32(buf, mdlseq.HEADER_SEQ_INDEX, seq_base)
    next_string = string_base
    for index, entry in enumerate(entries):
        anim_offset = anim_base + index * mdlseq.ANIM_STRIDE
        _put32(buf, anim_offset + mdlseq.ANIM_NAME, _string(buf, next_string, entry["anim"]) - anim_offset)
        next_string += len(entry["anim"]) + 1
        _putf(buf, anim_offset + mdlseq.ANIM_FPS, 30.0)
        _put32(buf, anim_offset + mdlseq.ANIM_FRAMES, entry["frames"])
        descriptor = seq_base + index * mdlseq.SEQ_STRIDE
        if index == 0:
            _put32(buf, descriptor + 28, len(entries) * mdlseq.SEQ_STRIDE)
        _put32(buf, descriptor + mdlseq.SEQ_LABEL, _string(buf, next_string, entry["label"]) - descriptor)
        next_string += len(entry["label"]) + 1
        _put32(buf, descriptor + mdlseq.SEQ_ACTIVITY, _string(buf, next_string, entry["activity"]) - descriptor)
        next_string += len(entry["activity"]) + 1
        _put32(buf, descriptor + mdlseq.SEQ_FLAGS, entry.get("flags", 0))
        _put32(buf, descriptor + mdlseq.SEQ_NUMBLENDS, entry["blends"])
        _put32(buf, descriptor + mdlseq.SEQ_ANIM_BLOCK, block_base + 8 * index - descriptor)
        for blend in range(entry["blends"]):
            _put16(buf, block_base + 8 * index + 2 * blend, index)
    return bytes(buf)


def test_frames_and_single_pose_come_from_the_descriptor(tmp_path):
    path = tmp_path / "model.mdl"
    path.write_bytes(
        _model(
            [
                {"label": "AttackStand_PRIMARY", "activity": "ACT_MP_ATTACK_STAND_PRIMARY", "anim": "@AttackStand_PRIMARY", "frames": 21, "blends": 1, "flags": 22},
                {"label": "PRIMARY_aimmatrix_idle", "activity": "", "anim": "a_PRIMARY_aimmatrix_idle_straight_up", "frames": 1, "blends": 2, "flags": 1044},
            ]
        )
    )
    model = mdlseq.load(path)
    attack = model.find("AttackStand_PRIMARY")
    aim = model.find("PRIMARY_aimmatrix_idle")
    assert attack is not None and aim is not None
    assert (attack.declared_frames, attack.single_pose, attack.activity, attack.flags) == (21, False, "ACT_MP_ATTACK_STAND_PRIMARY", 22)
    assert (aim.declared_frames, aim.single_pose, aim.numblends) == (1, True, 2)
    assert mdlseq.self_check(path)["stride_matches_header"] is True
    assert mdlseq.self_check(path)["labels_printable"] == 2


def test_a_name_only_descriptor_declares_no_frames():
    sequences, header = mdlseq.read_sequences(
        _model([{"label": "PRIMARY_reload_loop", "activity": "", "anim": "unused", "frames": 20, "blends": 0}])
    )
    assert header["table_inside_file"] is True
    assert sequences[0].label == "PRIMARY_reload_loop"
    assert sequences[0].declared_frames == 0 and sequences[0].anims == []
