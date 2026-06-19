"""Figure generator tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, AnalysisSummary, FigureManifest,
)
from arm64_probe.analysis.figures import FigureGenerator


class FigureGeneratorTests(unittest.TestCase):
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
            repository_id="x", repository_commit="abc", dirty_tree=False,
            toolchain=(), case_analyses=(self.ca,),
            cross_run_comparisons=(), anomalies=(),
            generated_at="2026-06-17T12:00:00Z",
        )
        self.gen = FigureGenerator(self.summary)
        self.tmpdir = Path(tempfile.mkdtemp())

    def test_latency_bar_chart_creates_png(self):
        manifest = self.gen.latency_bar_chart(self.tmpdir)
        png_path = self.tmpdir / f"{manifest.figure_id}.png"
        self.assertTrue(png_path.exists())
        self.assertGreater(png_path.stat().st_size, 100)

    def test_manifest_has_required_fields(self):
        manifest = self.gen.latency_bar_chart(self.tmpdir)
        self.assertEqual(manifest.source_analysis_id, "test")
        self.assertIsInstance(manifest.figure_id, str)
        self.assertIsInstance(manifest.caption, str)
        self.assertIsInstance(manifest.path, str)
        self.assertIsInstance(manifest.regeneration_command, str)

    def test_generate_all_produces_figures(self):
        manifests = self.gen.generate_all(self.tmpdir)
        self.assertGreater(len(manifests), 0)
        for m in manifests:
            path = self.tmpdir / f"{m.figure_id}.png"
            self.assertTrue(path.exists(), f"missing: {path}")

    def test_empty_analysis_handles_gracefully(self):
        empty = AnalysisSummary(
            analysis_id="empty", schema_version=1,
            source_runs=(), platform_id="gb10",
            repository_id="x", repository_commit="abc", dirty_tree=False,
            toolchain=(), case_analyses=(), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        gen = FigureGenerator(empty)
        manifests = gen.generate_all(self.tmpdir)
        # Should still produce figures (possibly with "no data" text)
        for m in manifests:
            path = self.tmpdir / f"{m.figure_id}.png"
            self.assertTrue(path.exists(), f"Empty analysis figure missing: {path}")


if __name__ == "__main__":
    unittest.main()
