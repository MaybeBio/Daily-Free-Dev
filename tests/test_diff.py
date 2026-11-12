import tempfile
import unittest
from pathlib import Path

from shovel import diff


class NormalizeLinesTest(unittest.TestCase):
    def test_collapses_whitespace_and_drops_volatile(self):
        lines = diff.normalize_lines("a   b\n\n统计时间: 2026\n  c  \n")
        self.assertEqual(lines, ["a b", "c"])


class DiffLinesTest(unittest.TestCase):
    def test_added_removed(self):
        result = diff.diff_lines(["a", "b"], ["b", "c"])
        self.assertEqual(result["added"], ["c"])
        self.assertEqual(result["removed"], ["a"])
        self.assertEqual(result["added_count"], 1)


class UpdateSnapshotTest(unittest.TestCase):
    def test_baseline_then_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            first = diff.update_snapshot("src", "a\nb\n", snapshot_dir=path)
            self.assertTrue(first["baseline"])
            second = diff.update_snapshot("src", "a\nb\n", snapshot_dir=path)
            self.assertFalse(second["baseline"])
            self.assertEqual(second["added_count"], 0)
            self.assertEqual(second["removed_count"], 0)

    def test_archive_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            archive = path / "daily"
            diff.update_snapshot("src", "a\n", snapshot_dir=path, archive_dir=archive)
            self.assertTrue((archive / "src.txt").exists())

    def test_anomaly_guard_keeps_old_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            old = "\n".join(f"line {index}" for index in range(25)) + "\n"
            diff.update_snapshot("src", old, snapshot_dir=path)
            result = diff.update_snapshot("src", "line 0\n", snapshot_dir=path)
            self.assertTrue(result["anomaly"])
            self.assertEqual((path / "src.txt").read_text(encoding="utf-8"), old)

    def test_small_sources_not_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            diff.update_snapshot("src", "a\nb\nc\n", snapshot_dir=path)
            result = diff.update_snapshot("src", "a\n", snapshot_dir=path)
            self.assertFalse(result.get("anomaly"))


class ChangesTest(unittest.TestCase):
    def test_no_change_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = diff.append_changes(
                Path(tmp) / "changes.jsonl", "src", "Src", {"added": [], "removed": []}
            )
            self.assertIsNone(record)

    def test_record_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changes.jsonl"
            record = diff.append_changes(
                path,
                "src",
                "Src",
                {"added": [str(index) for index in range(80)], "removed": [], "added_count": 80},
                cap=50,
            )
            self.assertEqual(len(record["added"]), 50)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_history_keeps_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            for index in range(5):
                diff.append_history(path, {"n": index}, keep=3)
            rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(rows), 3)
            self.assertIn('"n": 4', rows[-1])


if __name__ == "__main__":
    unittest.main()
