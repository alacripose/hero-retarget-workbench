import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from forge.paths import detect
from tools import vpk_tracker as tracker


def entry(path, crc, size, chunk=1, offset=0):
    return [path, crc, size, chunk, offset]


def snapshot(identifier, vpks, chunks=None, build="1", version_date="Nov 18 2026"):
    return {
        "schema": tracker.SCHEMA,
        "id": identifier,
        "label": identifier,
        "created_at": "2026-11-18T00:00:00+00:00",
        "build": build,
        "version_date": version_date,
        "digest": "blake3:" + identifier,
        "summary": {"vpks": len(vpks), "entries": sum(len(v["entries"]) for v in vpks), "chunks": len(chunks or []), "dir_bytes": 0},
        "vpks": vpks,
        "chunks": chunks or [],
    }


class ListingTests(unittest.TestCase):
    def test_listing_reads_paths_crc_sizes_chunks_and_offsets(self):
        text = (
            "models/heroes_staging/haze/haze.vmdl_c crc=0x1234ABCD metadatasz=0 "
            "fnumber=119 ofs=0x678FAC0 sz=4614\r\n"
            "\n"
            "models/heroes_staging/test model/test.dmx crc=0x00000001 metadatasz=0 "
            "fnumber=32767 ofs=0x20 sz=12\n"
        )
        entries = tracker.parse_vpk_dir(text)
        self.assertEqual([row[0] for row in entries], [
            "models/heroes_staging/haze/haze.vmdl_c",
            "models/heroes_staging/test model/test.dmx",
        ])
        self.assertEqual(entries[0], ["models/heroes_staging/haze/haze.vmdl_c", 0x1234ABCD, 4614, 119, 0x678FAC0])
        self.assertEqual(entries[1][2:], [12, 32767, 0x20])

    def test_an_unreadable_line_is_a_refusal_not_a_silent_skip(self):
        with self.assertRaises(tracker.TrackerError):
            tracker.parse_vpk_dir("models/a.vmdl_c CRC:0123 fnumber=1\n")


class DiffTests(unittest.TestCase):
    def setUp(self):
        old_entries = [
            entry("models/a.vmdl_c", 0x1111, 100, 1, 10),
            entry("models/b.vmdl_c", 0x2222, 200, 1, 20),
            entry("models/c.vmdl_c", 0x3333, 300, 1, 30),
            entry("models/d.vmdl_c", 0x4444, 400, 1, 40),
        ]
        new_entries = [
            entry("models/a.vmdl_c", 0x1111, 100, 1, 10),
            entry("models/b.vmdl_c", 0x2223, 250, 1, 20),
            entry("models/d.vmdl_c", 0x4444, 400, 2, 50),
            entry("models/e.vmdl_c", 0x5555, 500, 2, 60),
        ]
        self.old = snapshot("old", [{"name": "pak01_dir.vpk", "entries": old_entries, "blake3": "blake3:old"}], [
            {"vpk": "pak01_dir.vpk", "name": "pak01_001.vpk", "size": 1000, "mtime_ns": 1},
        ])
        self.new = snapshot("new", [{"name": "pak01_dir.vpk", "entries": new_entries, "blake3": "blake3:new"}], [
            {"vpk": "pak01_dir.vpk", "name": "pak01_001.vpk", "size": 1001, "mtime_ns": 2},
            {"vpk": "pak01_dir.vpk", "name": "pak01_002.vpk", "size": 2000, "mtime_ns": 3},
        ])

    def test_diff_counts_added_removed_modified_repacked_and_unchanged(self):
        report = tracker.diff_snapshots(self.old, self.new)
        self.assertEqual(report["summary"]["added"], 1)
        self.assertEqual(report["summary"]["removed"], 1)
        self.assertEqual(report["summary"]["modified"], 1)
        self.assertEqual(report["summary"]["repacked"], 1)
        self.assertEqual(report["summary"]["unchanged"], 1)
        self.assertEqual(report["summary"]["bytes_added"], 500)
        self.assertEqual(report["summary"]["bytes_removed"], 300)
        self.assertEqual(report["summary"]["bytes_delta"], 250)
        kinds = {row["path"]: row["kind"] for row in report["rows"]}
        self.assertEqual(kinds["models/b.vmdl_c"], "modified")
        self.assertEqual(kinds["models/c.vmdl_c"], "removed")
        self.assertEqual(kinds["models/e.vmdl_c"], "added")
        self.assertNotIn("models/d.vmdl_c", kinds)
        self.assertEqual([chunk["name"] for chunk in report["new_chunks"]], ["pak01_002.vpk"])
        self.assertEqual([chunk["name"] for chunk in report["changed_chunks"]], ["pak01_001.vpk"])
        self.assertTrue(report["digest"].startswith("blake3:"))
        self.assertIn("models", dict(report["groups"]["added"]["folders"]))

    def test_baseline_is_labelled_inventory_not_added_files(self):
        report = tracker.diff_snapshots(None, self.new)
        self.assertTrue(report["baseline"])
        self.assertIsNone(report["from"])
        self.assertEqual(report["summary"]["baseline"], 4)
        self.assertEqual(report["summary"]["added"], 0)
        self.assertEqual({row["kind"] for row in report["rows"]}, {"baseline"})
        self.assertEqual(report["vpks"][0]["entries_after"], 4)

    def test_diff_is_deterministic(self):
        first = tracker.diff_snapshots(self.old, self.new)
        second = tracker.diff_snapshots(self.old, self.new)
        self.assertEqual(first["digest"], second["digest"])

    def test_build_only_patch_is_not_reported_as_identical(self):
        old = snapshot("6863", self.old["vpks"], self.old["chunks"], build="6863")
        new = snapshot("6864", self.old["vpks"], self.old["chunks"], build="6864")
        report = tracker.diff_snapshots(old, new)
        self.assertTrue(report["build"]["changed"])
        self.assertEqual(report["build"]["before"], "6863")
        self.assertEqual(report["build"]["after"], "6864")
        self.assertTrue(report["summary"]["build_changed"])
        self.assertEqual(report["summary"]["rows"], 0)
        self.assertIn("no VPK entries changed; build metadata changed", tracker.diff_text(report))
        self.assertEqual(report["build"]["version_date_before"], "Nov 18 2026")


class ManifestTests(unittest.TestCase):
    def test_sfd_manifest_rows_are_parsed(self):
        text = (
            "1422456\t322100466064667547\tabc123\t8388608\tgame/citadel/pak01_dir.vpk\r\n"
            "1422456\t322100466064667547\tdef456\t1000\tgame/citadel/pak01_000.vpk\n"
            "not a row\n"
        )
        rows = tracker.parse_sfd_rows(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["path"], "game/citadel/pak01_dir.vpk")
        self.assertEqual(rows[1]["size"], 1000)

    def test_manifest_chunks_belong_to_the_matching_archive_family(self):
        rows = [
            {"path": "game/citadel/pak01_dir.vpk", "size": 10, "sha1": "dir"},
            {"path": "game/citadel/pak01_000.vpk", "size": 20, "sha1": "a"},
            {"path": "game/citadel/pak01_001.vpk", "size": 30, "sha1": "b"},
            {"path": "game/citadel/shaders_pc_000.vpk", "size": 40, "sha1": "c"},
        ]
        chunks = tracker.manifest_chunks(rows, "pak01_dir.vpk")
        self.assertEqual([chunk["name"] for chunk in chunks], ["pak01_000.vpk", "pak01_001.vpk"])
        self.assertEqual(chunks[0]["sha1"], "a")

    def test_manifest_chunk_hashes_replace_mtime_comparison(self):
        before = {"size": 20, "sha1": "a"}
        after = {"size": 20, "sha1": "b"}
        self.assertTrue(tracker._chunk_changed(before, after))
        self.assertFalse(tracker._chunk_changed(before, dict(before)))

    def test_snapshot_summary_keeps_manifest_provenance(self):
        source = {"kind": "manifest", "depot": "1422456", "manifest": "322100466064667547"}
        data = snapshot("m1", [{"name": "pak01_dir.vpk", "entries": [], "blake3": "blake3:x"}])
        data["source"] = source
        summary = tracker.snapshot_summary(data, "m1.json")
        self.assertEqual(summary["source"], source)

    def test_launcher_manifest_target_is_validated_before_a_job_starts(self):
        for target in ("1422456", "x:y", "1422456:322100466064667547/extra"):
            with self.assertRaises(tracker.TrackerError):
                tracker.start_manifest_snapshot(target)

    def test_fetch_manifests_reads_the_cache_and_the_chunk_listing(self):
        target = "1422456:322100466064667547"
        with tempfile.TemporaryDirectory(prefix="vpk-manifest-") as temporary:
            cache = Path(temporary) / "depots"
            citadel = cache / "1422456" / "322100466064667547" / "game" / "citadel"
            citadel.mkdir(parents=True)
            (citadel / "pak01_dir.vpk").write_bytes(b"dir")
            (citadel / "shaders_pc_dir.vpk").write_bytes(b"shader-dir")
            (citadel / "steam.inf").write_text(
                "ClientVersion=6861\nVersionDate=Nov 09 2026\n", encoding="utf-8"
            )
            listing = "\n".join([
                "1422456\t322100466064667547\taaa\t11\tgame/citadel/pak01_dir.vpk",
                "1422456\t322100466064667547\tbbb\t12\tgame/citadel/pak01_000.vpk",
                "1422456\t322100466064667547\tccc\t13\tgame/citadel/shaders_pc_dir.vpk",
                "1422456\t322100466064667547\tddd\t14\tgame/citadel/shaders_pc_000.vpk",
            ])
            calls = [
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                subprocess.CompletedProcess([], 0, stdout=listing, stderr=""),
            ]
            with mock.patch.object(tracker.subprocess, "run", side_effect=calls) as run:
                with mock.patch.object(tracker, "TRACKER_DIR", Path(temporary) / "tracker"):
                    fetched = tracker.fetch_manifests(Path("fake-sfd"), "1422450", [target], cache)
            self.assertEqual(len(fetched), 1)
            item = fetched[0]
            self.assertEqual(item["build"], "6861")
            self.assertEqual([path.name for path in item["vpks"]], ["pak01_dir.vpk", "shaders_pc_dir.vpk"])
            self.assertEqual(
                [chunk["name"] for chunk in item["chunks_by_vpk"]["pak01_dir.vpk"]],
                ["pak01_000.vpk"],
            )
            self.assertEqual(
                [chunk["name"] for chunk in item["chunks_by_vpk"]["shaders_pc_dir.vpk"]],
                ["shaders_pc_000.vpk"],
            )
            get_command = run.call_args_list[0].args[0]
            list_command = run.call_args_list[1].args[0]
            self.assertIn("get", get_command)
            self.assertIn("game/citadel/*_dir.vpk", get_command)
            self.assertIn("game/citadel/steam.inf", get_command)
            self.assertIn("ls", list_command)
            self.assertIn("game/citadel/*.vpk", list_command)


class BuildHistoryTests(unittest.TestCase):
    def test_game_tracking_commit_becomes_a_build_row(self):
        commit = {
            "sha": "a" * 40,
            "html_url": "https://github.com/SteamTracking/GameTracking-Deadlock/commit/" + "a" * 40,
            "commit": {
                "message": (
                    "6864 | 2 files | M\tgame/citadel/steam.inf, "
                    "M\tmanifests/manifest_1422456.txt\n\n"
                    "https://steamdb.info/patchnotes/26770241/"
                ),
                "committer": {"date": "2026-11-18T22:38:56Z"},
            },
        }
        row = tracker.parse_build_commit(commit)
        self.assertEqual(row["build"], "6864")
        self.assertEqual(row["files_changed"], 2)
        self.assertEqual(row["short_sha"], "aaaaaaa")
        self.assertEqual(row["patch_url"], "https://steamdb.info/patchnotes/26770241")
        self.assertEqual(row["changed"][0]["path"], "game/citadel/steam.inf")

    def test_manifest_id_is_read_from_the_tracked_manifest_file(self):
        text = "Content Manifest for Depot 1422456\n\nManifest ID / date     : 756140601198168750 / 11/18/2026 22:15:41\n"
        with mock.patch.object(tracker, "_http_text", return_value=text):
            tracker._MANIFEST_ID_CACHE.clear()
            manifest = tracker.fetch_manifest_id("a" * 40)
        self.assertEqual(manifest, "756140601198168750")

    def test_live_signature_uses_sizes_and_mtimes(self):
        with tempfile.TemporaryDirectory(prefix="vpk-live-") as temporary:
            game_dir = Path(temporary) / "game"
            citadel = game_dir / "citadel"
            citadel.mkdir(parents=True)
            vpk = citadel / "pak01_dir.vpk"
            vpk.write_bytes(b"one")
            (citadel / "steam.inf").write_text("ClientVersion=6864\n", encoding="utf-8")
            env = SimpleNamespace(game_dir=game_dir, build="6864", version_date="Nov 18 2026")
            signature = tracker.local_signature(env)
            saved = {
                "build": "6864",
                "vpks": [{"name": vpk.name, "size": vpk.stat().st_size, "mtime_ns": vpk.stat().st_mtime_ns}],
            }
            self.assertTrue(tracker._signature_matches_snapshot(signature, saved))
            saved["vpks"][0]["mtime_ns"] -= 1
            self.assertFalse(tracker._signature_matches_snapshot(signature, saved))

    def test_watcher_starts_a_stable_snapshot_after_a_change(self):
        with tempfile.TemporaryDirectory(prefix="vpk-watch-") as temporary:
            game_dir = Path(temporary) / "game"
            citadel = game_dir / "citadel"
            citadel.mkdir(parents=True)
            vpk = citadel / "pak01_dir.vpk"
            vpk.write_bytes(b"new")
            (citadel / "steam.inf").write_text("ClientVersion=6864\n", encoding="utf-8")
            env = SimpleNamespace(game_dir=game_dir, s2v=Path("s2v"), build="6864", version_date="Nov 18 2026")
            old = {"id": "old", "build": "6863", "vpks": [{"name": vpk.name, "size": 1, "mtime_ns": 1}]}
            started = []
            stop = mock.Mock()
            stop.is_set.side_effect = [False, False, False, True]
            stop.wait.return_value = False
            with mock.patch.object(tracker, "detect", return_value=env), \
                 mock.patch.object(tracker, "_latest_local_row", return_value=old), \
                 mock.patch.object(tracker, "_job_public", return_value={"id": "", "status": "idle"}), \
                 mock.patch.object(tracker, "start_local_snapshot", side_effect=lambda **kwargs: started.append(kwargs) or {"id": "job-1"}), \
                 mock.patch.object(tracker, "LIVE_SETTLE_SECONDS", 0.0), \
                 mock.patch.object(tracker, "LIVE_POLL_SECONDS", 0.0):
                tracker._LIVE.update({"capture_job": "", "last_capture": "", "last_capture_status": ""})
                tracker._live_watcher(stop)
        self.assertEqual(len(started), 1)
        self.assertTrue(started[0]["stable"])

    def test_guard_aborts_before_a_snapshot_is_written(self):
        with tempfile.TemporaryDirectory(prefix="vpk-guard-") as temporary:
            vpk = Path(temporary) / "pak01_dir.vpk"
            vpk.write_bytes(b"vpk")
            captured = {
                "name": vpk.name,
                "path": str(vpk),
                "size": 3,
                "mtime_ns": 1,
                "blake3": "blake3:x",
                "entry_count": 0,
                "entries_digest": "blake3:y",
                "entries": [],
                "chunks": [],
            }
            with mock.patch.object(tracker, "capture_vpk", return_value=captured):
                with mock.patch.object(tracker, "SNAPSHOT_DIR", Path(temporary) / "snapshots"):
                    with self.assertRaises(tracker.TrackerError):
                        tracker.build_snapshot(
                            [vpk],
                            s2v=Path("s2v"),
                            build="6864",
                            guard=lambda: (_ for _ in ()).throw(tracker.TrackerError("game-changed")),
                        )
            self.assertFalse((Path(temporary) / "snapshots").exists())


class Source2ViewerTests(unittest.TestCase):
    """S2V is the reader; prove a VPK S2V writes is a VPK this tracker reads."""

    def test_s2v_created_vpk_is_listable(self):
        s2v = detect().s2v
        if s2v is None:
            self.skipTest("Source 2 Viewer CLI is not installed")
        with tempfile.TemporaryDirectory(prefix="vpk-tracker-") as temporary:
            root = Path(temporary) / "content"
            (root / "models").mkdir(parents=True)
            (root / "models" / "a.dmx").write_text("one", encoding="utf-8")
            (root / "models" / "b.vmdl").write_text("two", encoding="utf-8")
            vpk = Path(temporary) / "fixture_dir.vpk"
            process = subprocess.run(
                [str(s2v), "-i", str(root), "--vpk_create", str(vpk), "-q"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            entries = tracker.list_vpk(s2v, vpk)
            paths = {row[0] for row in entries}
            self.assertEqual(paths, {"models/a.dmx", "models/b.vmdl"})
            captured = tracker.capture_vpk(s2v, vpk)
            self.assertEqual(captured["entry_count"], 2)
            self.assertTrue(captured["blake3"].startswith("blake3:"))
            self.assertTrue(captured["entries_digest"].startswith("blake3:"))


if __name__ == "__main__":
    unittest.main()
