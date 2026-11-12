"""Axis-shaped proof records for retarget work.

A proof carries the artifact bytes, the claim those bytes support, the origin of
the reading, the evidence sentence, the tick span, the world digest, the
presenter and the ticket. A proof alone is not a pass: every declared check must
return `pass`, the artifact must hash to the proof, and the span must be current.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from .hashes import blake3_hex

PROOF_CONTRACT = (
    "dmf.retarget.proof: artifact, artifact_digest, claim, origin, evidence, "
    "tick_span, world_digest, presenter, ticket, checks"
)
PROOF_SCHEMA = "dmf.retarget.proof/" + blake3_hex(PROOF_CONTRACT.encode("utf-8"))[:32]
WEIGHTS_CONTRACT = (
    "dmf.retarget.weights: schema, mesh, armature, mode, mapping, extras, "
    "options, vertices"
)
WEIGHTS_SCHEMA = "dmf.retarget.weights/" + blake3_hex(WEIGHTS_CONTRACT.encode("utf-8"))[:32]

TOKEN_PASS = "pass"
TOKEN_FAIL = "fail"
TOKEN_UNCHECKED = "unchecked"
TOKEN_ABSENT = "absent"
TOKEN_STALE = "stale"
TOKEN_REFUSED = "refused"


class ProofError(ValueError):
    pass


@dataclass(frozen=True)
class Refusal:
    kind: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "detail": self.detail}


@dataclass(frozen=True)
class Check:
    name: str
    token: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "token": self.token, "detail": self.detail}


@dataclass(frozen=True)
class Proof:
    artifact: str
    artifact_digest: str
    claim: str
    origin: str
    evidence: str
    tick_span: tuple[int, int]
    world_digest: str
    presenter: str
    ticket: str
    checks: tuple[Check, ...] = field(default_factory=tuple)
    schema: str = PROOF_SCHEMA

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "artifact": self.artifact,
            "artifact_digest": self.artifact_digest,
            "claim": self.claim,
            "origin": self.origin,
            "evidence": self.evidence,
            "tick_span": list(self.tick_span),
            "world_digest": self.world_digest,
            "presenter": self.presenter,
            "ticket": self.ticket,
            "checks": [check.as_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "Proof":
        span = tuple(int(part) for part in value.get("tick_span", ()))  # type: ignore[arg-type]
        if len(span) != 2:
            raise ProofError("proof-tick-span-malformed: expected two ticks")
        checks = tuple(
            Check(str(item["name"]), str(item["token"]), str(item.get("detail", "")))
            for item in value.get("checks", [])  # type: ignore[union-attr]
        )
        return cls(
            artifact=str(value["artifact"]),
            artifact_digest=str(value["artifact_digest"]),
            claim=str(value.get("claim", "")),
            origin=str(value.get("origin", "")),
            evidence=str(value.get("evidence", "")),
            tick_span=span,  # type: ignore[arg-type]
            world_digest=str(value.get("world_digest", "")),
            presenter=str(value.get("presenter", "")),
            ticket=str(value.get("ticket", "")),
            checks=checks,
            schema=str(value.get("schema", PROOF_SCHEMA)),
        )


@dataclass(frozen=True)
class ProofWindow:
    current_tick: int
    max_age_ticks: int = 0

    def is_current(self, proof: Proof) -> Refusal | None:
        start, end = proof.tick_span
        if start > end:
            return Refusal(TOKEN_STALE, f"{proof.artifact}: tick span {start}..{end} is inverted")
        if end > self.current_tick:
            return Refusal(
                TOKEN_STALE,
                f"{proof.artifact}: span ends at {end}, world stands at {self.current_tick}",
            )
        age = self.current_tick - end
        if age > self.max_age_ticks:
            return Refusal(
                TOKEN_STALE,
                f"{proof.artifact}: proof is {age} ticks old and the window is {self.max_age_ticks}",
            )
        return None


@dataclass
class Admission:
    refusals: list[Refusal] = field(default_factory=list)
    tokens: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.refusals

    def reasons(self, limit: int = 6) -> list[str]:
        return [refusal.detail for refusal in self.refusals[:limit]]


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def artifact_digest(data: bytes) -> str:
    return "blake3:" + blake3_hex(b"dmf.retarget.artifact\0" + data)


def world_digest(value: object) -> str:
    return "blake3:" + blake3_hex(b"dmf.retarget.world\0" + canonical_bytes(value))


def weights_payload(
    *,
    mesh: str,
    armature: str,
    mode: str,
    mapping: Mapping[str, str],
    extras: Mapping[str, str],
    options: Mapping[str, object],
    vertices: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema": WEIGHTS_SCHEMA,
        "mesh": mesh,
        "armature": armature,
        "mode": mode,
        "mapping": dict(sorted(mapping.items())),
        "extras": dict(sorted(extras.items())),
        "options": dict(sorted(options.items())),
        "vertices": list(vertices),
    }


def _relative(root: Path, relative: str) -> Path:
    path = Path(relative.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ProofError(f"proof-path-refused: {relative!r} is not a relative artifact path")
    root = root.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ProofError(f"proof-path-refused: {relative!r} escapes {root}") from error
    return resolved


def write_artifact(root: Path, relative: str, payload: object) -> tuple[Path, str]:
    path = _relative(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(payload)
    path.write_bytes(data)
    return path, artifact_digest(data)


def write_proof(root: Path, relative: str, proof: Proof) -> Path:
    path = _relative(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(proof.as_dict()))
    return path


def read_proof(path: Path) -> Proof:
    return Proof.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def verify_bytes(root: Path, proof: Proof) -> Refusal | None:
    path = _relative(root, proof.artifact)
    if not path.is_file():
        return Refusal(TOKEN_UNCHECKED, f"{proof.artifact}: artifact is not on disk")
    data = path.read_bytes()
    if artifact_digest(data) != proof.artifact_digest:
        return Refusal(
            TOKEN_STALE,
            f"{proof.artifact}: bytes do not hash to the proof; refused rather than shown against changed bytes",
        )
    return None


def admit(
    proof: Proof,
    root: Path,
    window: ProofWindow,
    *,
    required_checks: Iterable[str] | None = None,
) -> Admission:
    refusals: list[Refusal] = []
    if proof.schema != PROOF_SCHEMA:
        refusals.append(Refusal(TOKEN_REFUSED, f"{proof.artifact}: schema is {proof.schema!r}"))
    if proof.origin not in ("executed", "read-back"):
        refusals.append(
            Refusal(TOKEN_UNCHECKED, f"{proof.artifact}: origin {proof.origin!r} is not a proof origin")
        )
    if not proof.presenter.strip():
        refusals.append(Refusal(TOKEN_UNCHECKED, f"{proof.artifact}: no presenter names who is acting"))
    if not proof.ticket.strip():
        refusals.append(Refusal(TOKEN_UNCHECKED, f"{proof.artifact}: no ticket names the work"))
    byte_refusal = verify_bytes(root, proof)
    if byte_refusal is not None:
        refusals.append(byte_refusal)
    window_refusal = window.is_current(proof)
    if window_refusal is not None:
        refusals.append(window_refusal)

    tokens = {check.name: check.token for check in proof.checks}
    required = list(required_checks) if required_checks is not None else [check.name for check in proof.checks]
    if not required:
        refusals.append(Refusal(TOKEN_UNCHECKED, f"{proof.artifact}: no checks were declared"))
    for name in required:
        token = tokens.get(name)
        if token is None or token == TOKEN_UNCHECKED:
            refusals.append(Refusal(TOKEN_UNCHECKED, f"{proof.artifact}: check {name} did not run"))
        elif token in (TOKEN_ABSENT, TOKEN_FAIL, TOKEN_STALE, TOKEN_REFUSED):
            refusals.append(Refusal(TOKEN_REFUSED, f"{proof.artifact}: check {name} returned {token}"))
    return Admission(refusals=refusals, tokens=tokens)
