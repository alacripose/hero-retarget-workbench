"""Content identities for the forge.

BLAKE3 is the current identity. SHA-256 stays behind a named legacy function
because older stage manifests and ledger rows carry it as evidence; new proof
and stage identities never fall back to it.

blake3 is imported on first use, not at module import: the Windows extension is a
.pyd, and a loaded .pyd cannot be overwritten. Enabling the add-on used to load
it, so Blender's Install answered CANCELLED over an enabled copy and kept the old
code. Lazy loading leaves the file unlocked until a hash is actually computed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_BLAKE3 = None


def _blake3():
    global _BLAKE3
    if _BLAKE3 is None:
        try:
            import blake3
        except ModuleNotFoundError as error:  # pragma: no cover - addon bundle path
            raise RuntimeError(
                "blake3-missing: install blake3 1.0.11 or use the bundled addon zip; "
                "the forge does not downgrade to SHA-256"
            ) from error
        _BLAKE3 = blake3
    return _BLAKE3


def blake3_hex(data: bytes) -> str:
    return _blake3().blake3(data).hexdigest()


def blake3_file(path: Path, block_size: int = 1024 * 1024) -> str:
    hasher = _blake3().blake3()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            hasher.update(block)
    return hasher.hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            hasher.update(block)
    return hasher.hexdigest()
