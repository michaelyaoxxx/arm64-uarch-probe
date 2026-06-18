"""Atomic persistence tests for AnalysisStore."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import AnalysisSummary
from arm64_probe.analysis.store import AnalysisStore
from arm64_probe.errors import ProbeError


class AnalysisStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = AnalysisStore(analysis_dir=self.tmpdir)

    def _make_summary(self, analysis_id="20260617T120000Z-a1b2c3d4"):
        return AnalysisSummary(
            analysis_id=analysis_id, schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )

    def test_write_creates_json_file(self):
        summary = self._make_summary()
        path = self.store.write_analysis(summary)
        self.assertTrue(path.exists())
        self.assertTrue(path.suffix == ".json")

    def test_read_returns_identical_summary(self):
        summary = self._make_summary()
        self.store.write_analysis(summary)
        loaded = self.store.read_analysis(summary.analysis_id)
        self.assertEqual(loaded, summary)

    def test_list_analyses_returns_ids(self):
        s1 = self._make_summary("20260617T120000Z-a1b2c3d4")
        s2 = self._make_summary("20260617T130000Z-b5c6d7e8")
        self.store.write_analysis(s1)
        self.store.write_analysis(s2)
        ids = self.store.list_analyses()
        self.assertIn(s1.analysis_id, ids)
        self.assertIn(s2.analysis_id, ids)

    def test_read_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.read_analysis("nonexistent")

    def test_list_analyses_excludes_temp_files(self):
        s1 = self._make_summary("analysis1")
        self.store.write_analysis(s1)
        # Create a temp file that should be excluded
        (self.tmpdir / ".tempfile.tmp").write_text("{}")
        ids = self.store.list_analyses()
        self.assertIn("analysis1", ids)
        self.assertNotIn(".tempfile", ids)

    def test_read_corrupted_json_raises(self):
        bad_path = self.tmpdir / "corrupt.json"
        bad_path.write_text("not valid json")
        with self.assertRaises(ProbeError):
            self.store.read_analysis("corrupt")

    def test_rejects_oversize_file(self):
        big_path = self.tmpdir / "big.json"
        big_path.write_text("x" * (2 * 1024 * 1024 + 1))  # > 2 MiB
        with self.assertRaises(ValueError):
            self.store.read_analysis("big")

    def test_analysis_dir_is_created_if_missing(self):
        new_dir = self.tmpdir / "new_analysis"
        store = AnalysisStore(analysis_dir=new_dir)
        self.assertTrue(new_dir.exists())
        self.assertTrue(new_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
