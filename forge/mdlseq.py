"""Decode a Source 1 model's own sequence descriptors and the anim descriptions they name.

The Scout source (`F:/Documents/scout.mdl` and its animations companion
`F:/Documents/scout_animations.mdl`, both decompiled by Crowbar 0.74) does not use `studio.h`'s
`mstudioseqdesc_t` byte-for-byte: every field sits 4 bytes later than the published layout, which is
why re-reading the documented offsets returned zeros and string garbage. Measured against the files:

- header: sequence count @ 188, sequence table @ 192; anim description count @ 180, table @ 184;
- sequence entry stride **212** (entry 0's +28 field carries `count × 212` in both files), with
  label offset @ +4, activity-name offset @ +8, flags @ +12, numblends @ +56, and the `short`
  anim-index block @ +60 (both offsets desc-relative);
- anim description stride **100**, with name offset @ +4, fps @ +8 (float), frame count @ +16.

The labels cross-check against the QC's `$sequence` names, and the anim names cross-check against the
SMD filenames the decompiler wrote, so the frame counts are the model's own declaration rather than the
SMD's length.

`scout.mdl` itself declares the four names but carries no animation for them (numblends 0, flags 2048,
2 anim descriptions for the whole file); the animation data and its descriptors are in the companion
model, which is also the file Crowbar decompiled into `scout_animations.qc` + `scout_animations_anims/`.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from pathlib import Path

HEADER_ANIM_COUNT = 180
HEADER_ANIM_INDEX = 184
HEADER_SEQ_COUNT = 188
HEADER_SEQ_INDEX = 192
SEQ_STRIDE = 212
SEQ_LABEL = 4
SEQ_ACTIVITY = 8
SEQ_FLAGS = 12
SEQ_NUMBLENDS = 56
SEQ_ANIM_BLOCK = 60
ANIM_STRIDE = 100
ANIM_NAME = 4
ANIM_FPS = 8
ANIM_FRAMES = 16


@dataclass
class Anim:
    index: int
    name: str
    fps: float
    frames: int


@dataclass
class Sequence:
    index: int
    descriptor: int
    label: str
    activity: str
    flags: int
    numblends: int
    anims: list[Anim] = field(default_factory=list)

    @property
    def declared_frames(self) -> int:
        """The sequence's own frame count: the longest anim it blends."""
        return max((anim.frames for anim in self.anims), default=0)

    @property
    def single_pose(self) -> bool:
        """True when every blend cell is one frame, so the sequence cannot move."""
        return bool(self.anims) and all(anim.frames <= 1 for anim in self.anims)


@dataclass
class Model:
    path: Path
    size: int
    md5: str
    seq_base: int
    seq_count: int
    anim_base: int
    anim_count: int
    sequences: list[Sequence]

    def find(self, label: str) -> Sequence | None:
        return next((sequence for sequence in self.sequences if sequence.label == label), None)


def _i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def _f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def _cstring(data: bytes, offset: int) -> str:
    if not (0 <= offset < len(data)):
        return ""
    end = data.find(b"\x00", offset)
    if end < 0 or end == offset or end - offset > 96:
        return ""
    text = data[offset:end].decode("latin-1", errors="replace")
    return text if all(32 <= ord(char) < 127 for char in text) else ""


def read_sequences(data: bytes) -> tuple[list[Sequence], dict]:
    """Every sequence descriptor in the model, plus the header facts used to validate the stride."""
    seq_base = _i32(data, HEADER_SEQ_INDEX)
    seq_count = _i32(data, HEADER_SEQ_COUNT)
    anim_base = _i32(data, HEADER_ANIM_INDEX)
    anim_count = _i32(data, HEADER_ANIM_COUNT)
    table_end = seq_base + seq_count * SEQ_STRIDE
    header = {
        "seq_base": seq_base,
        "seq_count": seq_count,
        "seq_stride": SEQ_STRIDE,
        "seq_table_end": table_end,
        "anim_base": anim_base,
        "anim_count": anim_count,
        "stride_matches_header": seq_count > 0 and _i32(data, seq_base + 28) == seq_count * SEQ_STRIDE,
        "table_inside_file": 0 <= seq_base and table_end <= len(data),
    }
    sequences = []
    for index in range(seq_count):
        descriptor = seq_base + index * SEQ_STRIDE
        label = _cstring(data, descriptor + _i32(data, descriptor + SEQ_LABEL))
        activity = _cstring(data, descriptor + _i32(data, descriptor + SEQ_ACTIVITY))
        flags = _i32(data, descriptor + SEQ_FLAGS)
        numblends = _i32(data, descriptor + SEQ_NUMBLENDS)
        block = descriptor + _i32(data, descriptor + SEQ_ANIM_BLOCK)
        anims = []
        if 0 < numblends <= 64 and 0 <= block and block + 2 * numblends <= len(data):
            for blend in range(numblends):
                anim_index = _i16(data, block + 2 * blend)
                anim_offset = anim_base + anim_index * ANIM_STRIDE
                if not (0 <= anim_index < anim_count and anim_offset + ANIM_STRIDE <= len(data)):
                    continue
                anims.append(
                    Anim(
                        index=anim_index,
                        name=_cstring(data, anim_offset + _i32(data, anim_offset + ANIM_NAME)),
                        fps=round(_f32(data, anim_offset + ANIM_FPS), 4),
                        frames=_i32(data, anim_offset + ANIM_FRAMES),
                    )
                )
        sequences.append(
            Sequence(
                index=index,
                descriptor=descriptor,
                label=label,
                activity=activity,
                flags=flags,
                numblends=numblends,
                anims=anims,
            )
        )
    return sequences, header


_CACHE: dict[str, Model] = {}


def load(path: str | Path) -> Model:
    """Read a model once; the decoder is pure over the file's bytes."""
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    source = Path(path)
    data = source.read_bytes()
    sequences, header = read_sequences(data)
    model = Model(
        path=source,
        size=len(data),
        md5=hashlib.md5(data).hexdigest(),
        seq_base=header["seq_base"],
        seq_count=header["seq_count"],
        anim_base=header["anim_base"],
        anim_count=header["anim_count"],
        sequences=sequences,
    )
    _CACHE[key] = model
    return model


def self_check(path: str | Path) -> dict:
    """The layout claims, each answerable from the decoded table rather than asserted."""
    model = load(path)
    data = model.path.read_bytes()
    printable = sum(1 for sequence in model.sequences if sequence.label)
    unique = len({sequence.label for sequence in model.sequences if sequence.label})
    anims_named = sum(1 for sequence in model.sequences for anim in sequence.anims if anim.name)
    anims_total = sum(len(sequence.anims) for sequence in model.sequences)
    header = read_sequences(data)[1]
    return {
        "path": str(model.path),
        "bytes": model.size,
        "md5": model.md5,
        "descriptors": model.seq_count,
        "labels_printable": printable,
        "labels_unique": unique,
        "anim_descriptions": model.anim_count,
        "anims_named": anims_named,
        "anims_referenced": anims_total,
        "stride_matches_header": header["stride_matches_header"],
        "table_inside_file": header["table_inside_file"],
    }


def describe(sequence: Sequence) -> dict:
    """JSON-ready facts for one sequence, with the numbers a reader can re-check by offset."""
    return {
        "sequence": sequence.label,
        "descriptor": sequence.descriptor,
        "activity": sequence.activity,
        "flags": sequence.flags,
        "numblends": sequence.numblends,
        "anims": [{"index": anim.index, "name": anim.name, "frames": anim.frames, "fps": anim.fps} for anim in sequence.anims],
        "declared_frames": sequence.declared_frames,
        "single_pose": sequence.single_pose,
        "cells": len(sequence.anims),
    }
