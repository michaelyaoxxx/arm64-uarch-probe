"""Baseline promoter tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import BaselineManifest
from arm64_probe.analysis.baseline import BaselinePromoter


class BaselinePromoterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.promoter = BaselinePromoter(baseline_root=self.tmpdir)

    def _make_manifest(self, commit="abc123", dirty=False):
        return BaselineManifest(
            baseline_id="v1.0-test", version="v1.0",
            source_run_ids=("run1",), analysis_id="analysis1",
            report_id=None, figure_ids=(),
            commands=("probe run --profile baseline",),
            repository_commit=commit, dirty_tree=dirty,
            toolchain=(("python", "3.13.13"),),
            promoted_at="2026-06-17T12:00:00Z", approved_by=None,
        )

    def test_validate_rejects_dirty_tree(self):
        errors = self.promoter.validate_candidate(
            run_ids=("run1",), analysis_id="analysis1",
            report_id=None, figure_ids=(),
            repository_commit="abc123", dirty_tree=True,
        )
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("dirty" in e.lower() for e in errors))

    def test_validate_rejects_missing_run_ids(self):
        errors = self.promoter.validate_candidate(
            run_ids=(), analysis_id="analysis1",
            report_id=None, figure_ids=(),
            repository_commit="abc123", dirty_tree=False,
        )
        self.assertGreater(len(errors), 0)

    def test_validate_rejects_missing_analysis_id(self):
        errors = self.promoter.validate_candidate(
            run_ids=("run1",), analysis_id="",
            report_id=None, figure_ids=(),
            repository_commit="abc123", dirty_tree=False,
        )
        self.assertGreater(len(errors), 0)

    def test_validate_accepts_clean_candidate(self):
        errors = self.promoter.validate_candidate(
            run_ids=("run1",), analysis_id="analysis1",
            report_id=None, figure_ids=(),
            repository_commit="abc123", dirty_tree=False,
        )
        self.assertEqual(errors, ())

    def test_promote_writes_manifest(self):
        manifest = self._make_manifest()
        output = self.promoter.promote(manifest, approved_by="test-user")
        self.assertTrue(output.exists())
        manifest_file = output / "baseline-manifest.json"
        self.assertTrue(manifest_file.exists())

    def test_promote_copies_artifacts(self):
        manifest = self._make_manifest()
        # Create a fake artifact
        art_path = self.tmpdir / "artifact.txt"
        art_path.write_text("test artifact")
        output = self.promoter.promote(manifest, (art_path,), approved_by="test-user")
        copied = output / "artifact.txt"
        self.assertTrue(copied.exists())
        self.assertEqual(copied.read_text(), "test artifact")


if __name__ == "__main__":
    unittest.main()
