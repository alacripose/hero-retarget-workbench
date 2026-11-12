import json
import tempfile
import unittest
from pathlib import Path

from forge.hashes import blake3_hex
from forge.proof import (
    PROOF_SCHEMA,
    WEIGHTS_SCHEMA,
    Check,
    Proof,
    ProofError,
    ProofWindow,
    admit,
    artifact_digest,
    canonical_bytes,
    read_proof,
    verify_bytes,
    weights_payload,
    write_artifact,
    write_proof,
)


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def mint(self, token="pass", presenter="ala", ticket="TICKET-0002"):
        payload = weights_payload(
            mesh="port",
            armature="hero",
            mode="HYBRID",
            mapping={"spine": "spine_01"},
            extras={"tail_01": "tail_01"},
            options={"max_influences": 4},
            vertices=[{"p": [0, 0, 0], "w": [["spine_01", 1.0]]}],
        )
        path, digest = write_artifact(self.root, "artifacts/proofs/port.json", payload)
        proof = Proof(
            artifact="artifacts/proofs/port.json",
            artifact_digest=digest,
            claim="vertex weights for port on hero",
            origin="executed",
            evidence="1 vertex, 1 weighted",
            tick_span=(4, 4),
            world_digest="blake3:" + "0" * 64,
            presenter=presenter,
            ticket=ticket,
            checks=(
                Check("weight-coverage", token, "1 of 1 weighted"),
                Check("normalization", "pass", "max error 0"),
            ),
        )
        write_proof(self.root, "artifacts/proofs/port.proof.json", proof)
        return proof, path

    def test_blake3_identity_is_not_sha256(self):
        self.assertEqual(blake3_hex(b"x"), "3ae7d805f6789a6402acb70ad4096a85a56bf6804eaf25c0493ac697548d30b5")
        self.assertNotEqual(blake3_hex(b"x"), "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881")

    def test_schema_ids_are_hash_pinned_and_not_numeric(self):
        self.assertTrue(PROOF_SCHEMA.startswith("dmf.retarget.proof/"))
        self.assertTrue(WEIGHTS_SCHEMA.startswith("dmf.retarget.weights/"))
        self.assertNotIn("/1", PROOF_SCHEMA + WEIGHTS_SCHEMA)
        self.assertEqual(len(PROOF_SCHEMA.rsplit("/", 1)[1]), 32)

    def test_artifact_digest_is_blake3_and_byte_stable(self):
        first = artifact_digest(canonical_bytes({"b": 2, "a": 1}))
        second = artifact_digest(canonical_bytes({"a": 1, "b": 2}))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("blake3:"))
        self.assertEqual(len(first), len("blake3:") + 64)

    def test_proof_round_trip_and_admission(self):
        proof, _ = self.mint()
        read = read_proof(self.root / "artifacts/proofs/port.proof.json")
        self.assertEqual(read.as_dict(), proof.as_dict())
        admission = admit(read, self.root, ProofWindow(current_tick=4, max_age_ticks=0))
        self.assertTrue(admission.ok, admission.reasons())
        self.assertEqual(admission.tokens["weight-coverage"], "pass")

    def test_stale_proof_is_refused(self):
        proof, _ = self.mint()
        admission = admit(proof, self.root, ProofWindow(current_tick=5, max_age_ticks=0))
        self.assertFalse(admission.ok)
        self.assertIn("1 ticks old", admission.reasons()[0])

    def test_changed_bytes_are_refused(self):
        proof, path = self.mint()
        path.write_bytes(path.read_bytes() + b" ")
        refusal = verify_bytes(self.root, proof)
        self.assertIsNotNone(refusal)
        self.assertEqual(refusal.kind, "stale")

    def test_missing_presenter_or_ticket_is_refused(self):
        proof, _ = self.mint(presenter="", ticket="")
        admission = admit(proof, self.root, ProofWindow(current_tick=4))
        details = " ".join(admission.reasons())
        self.assertIn("no presenter", details)
        self.assertIn("no ticket", details)

    def test_unchecked_check_is_not_a_pass(self):
        proof, _ = self.mint(token="unchecked")
        admission = admit(proof, self.root, ProofWindow(current_tick=4))
        self.assertFalse(admission.ok)
        self.assertIn("weight-coverage did not run", " ".join(admission.reasons()))

    def test_path_escape_is_refused(self):
        with self.assertRaises(ProofError):
            write_artifact(self.root, "../escape.json", {"a": 1})
        with self.assertRaises(ProofError):
            write_artifact(self.root, "C:/escape.json", {"a": 1})

    def test_malformed_tick_span_is_refused(self):
        with self.assertRaises(ProofError):
            Proof.from_dict(
                {
                    "artifact": "a",
                    "artifact_digest": "blake3:" + "0" * 64,
                    "tick_span": [1],
                }
            )


if __name__ == "__main__":
    unittest.main()
