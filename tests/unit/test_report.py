"""Report generator tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, AnalysisSummary, FigureManifest, ReportManifest,
)
from arm64_probe.analysis.report import ReportGenerator


class ReportGeneratorTests(unittest.TestCase):
    def setUp(self):
        stats = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=5, error_count=0,
            min_value=4.0, max_value=5.0, median=4.36,
            mad=0.12, mean=4.40, stddev=0.35,
        )
        self.ca = CaseAnalysis(
            case_id="l1@gb10.cpu-0", scenario_id="cache-latency.l1-latency",
            platform_id="gb10", status="ok", total_samples=5, ok_samples=5,
            error_samples=0, metric_stats=(("latency_ns", stats),),
            anomalies=(), source_run_ids=("run1",),
        )
        self.summary = AnalysisSummary(
            analysis_id="test", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(self.ca,), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        self.figures = (
            FigureManifest(
                figure_id="latency_comparison", path="latency_comparison.png",
                caption="Test figure", source_analysis_id="test",
                regeneration_command="test",
            ),
        )
        self.gen = ReportGenerator(self.summary, self.figures)
        self.tmpdir = Path(tempfile.mkdtemp())

    def test_generate_returns_markdown_string(self):
        md = self.gen.generate()
        self.assertIn("# ", md)
        self.assertIn("gb10", md)
        self.assertIn("abc123", md)

    def test_generate_has_required_sections(self):
        md = self.gen.generate()
        self.assertIn("Provenance", md)
        self.assertIn("Summary", md)
        self.assertIn("Figures", md)

    def test_write_creates_file_and_manifest(self):
        manifest = self.gen.write(self.tmpdir, "probe report --analysis test")
        report_path = self.tmpdir / "report.md"
        self.assertTrue(report_path.exists())
        self.assertIsInstance(manifest, ReportManifest)
        self.assertEqual(manifest.source_analysis_id, "test")

    def test_generate_is_deterministic(self):
        md1 = self.gen.generate()
        md2 = self.gen.generate()
        self.assertEqual(md1, md2)

    def test_empty_analysis_produces_warning(self):
        empty = AnalysisSummary(
            analysis_id="empty", schema_version=1,
            source_runs=(), platform_id="gb10",
            repository_id="x", repository_commit="abc", dirty_tree=False,
            toolchain=(), case_analyses=(), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        gen = ReportGenerator(empty, ())
        md = gen.generate()
        self.assertTrue(any(w in md.lower() for w in ["no data", "warning", "empty", "no cases"]))

    def test_failed_case_shows_in_report(self):
        fail_stats = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=0, error_count=5,
            min_value=None, max_value=None, median=None,
            mad=None, mean=None, stddev=None,
        )
        fail_ca = CaseAnalysis(
            case_id="fail@gb10", scenario_id="cache-latency.l1-latency",
            platform_id="gb10", status="failed", total_samples=5,
            ok_samples=0, error_samples=5,
            metric_stats=(("latency_ns", fail_stats),),
            anomalies=("all_errors",), source_run_ids=("run1",),
        )
        fail_summary = AnalysisSummary(
            analysis_id="fail", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="x", repository_commit="abc", dirty_tree=False,
            toolchain=(), case_analyses=(fail_ca,), cross_run_comparisons=(),
            anomalies=("all_errors",), generated_at="2026-06-17T12:00:00Z",
        )
        gen = ReportGenerator(fail_summary, ())
        md = gen.generate()
        self.assertIn("fail@gb10", md)
        self.assertIn("all_errors", md)


if __name__ == "__main__":
    unittest.main()
