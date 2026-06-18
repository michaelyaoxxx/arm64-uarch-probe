"""Frozen invariants and serialization round-trip for analysis domain models."""
import json
import unittest

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, CrossRunMetricDelta, CrossRunComparison,
    AnalysisSummary, FigureManifest, ReportManifest, ImportedRecord,
    BaselineManifest,
)


class MetricStatsTests(unittest.TestCase):
    def test_frozen(self):
        s = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=5, error_count=0, min_value=4.0, max_value=5.0,
            median=4.36, mad=0.12, mean=4.40, stddev=0.35,
        )
        with self.assertRaises(Exception):
            s.median = 99.0

    def test_none_values_when_no_successes(self):
        s = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=0, error_count=5, min_value=None, max_value=None,
            median=None, mad=None, mean=None, stddev=None,
        )
        self.assertIsNone(s.median)
        self.assertEqual(s.success_count, 0)


class CaseAnalysisTests(unittest.TestCase):
    def test_metric_stats_sorted_by_name(self):
        m1 = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=1,
            success_count=1, error_count=0, min_value=4.0, max_value=4.0,
            median=4.0, mad=0.0, mean=4.0, stddev=0.0,
        )
        m2 = MetricStats(
            metric_name="accesses", unit="count", sample_count=1,
            success_count=1, error_count=0, min_value=100.0, max_value=100.0,
            median=100.0, mad=0.0, mean=100.0, stddev=0.0,
        )
        ca = CaseAnalysis(
            case_id="test@gb10.x", scenario_id="test", platform_id="gb10",
            status="ok", total_samples=1, ok_samples=1, error_samples=0,
            # Pass in reverse alphabetical order to verify sorting.
            metric_stats=(("latency_ns", m1), ("accesses", m2)),
            anomalies=(), source_run_ids=("run1",),
        )
        names = [k for k, _ in ca.metric_stats]
        self.assertEqual(names, ["accesses", "latency_ns"])


class AnalysisSummaryTests(unittest.TestCase):
    def test_frozen_and_fields(self):
        s = AnalysisSummary(
            analysis_id="20260617T120000Z-a1b2c3d4", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        self.assertEqual(s.schema_version, 1)
        self.assertEqual(s.platform_id, "gb10")


class SerializationRoundTripTests(unittest.TestCase):
    """Verify to_data -> JSON -> _dict_to round-trip for all models."""

    def _round_trip(self, value, expected_type):
        from arm64_probe.serialization.model_json import (
            to_data,
            _dict_to_analysis_summary,
            _dict_to_baseline_manifest,
            _dict_to_cross_run_comparison,
            _dict_to_figure_manifest,
            _dict_to_report_manifest,
            _dict_to_imported_record,
        )
        data = to_data(value)
        json_str = json.dumps(data, sort_keys=True)
        reloaded_data = json.loads(json_str)
        if expected_type is AnalysisSummary:
            result = _dict_to_analysis_summary(reloaded_data)
        elif expected_type is BaselineManifest:
            result = _dict_to_baseline_manifest(reloaded_data)
        elif expected_type is FigureManifest:
            result = _dict_to_figure_manifest(reloaded_data)
        elif expected_type is ReportManifest:
            result = _dict_to_report_manifest(reloaded_data)
        elif expected_type is ImportedRecord:
            result = _dict_to_imported_record(reloaded_data)
        elif expected_type is CrossRunComparison:
            result = _dict_to_cross_run_comparison(reloaded_data)
        else:
            self.skipTest(f"no _dict_to_* for {expected_type}")
        self.assertEqual(value, result)

    def test_analysis_summary_round_trip(self):
        ms = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=1,
            success_count=1, error_count=0, min_value=4.36, max_value=4.36,
            median=4.36, mad=0.0, mean=4.36, stddev=0.0,
        )
        ca = CaseAnalysis(
            case_id="l1@gb10.cpu-0", scenario_id="cache-latency.l1-latency",
            platform_id="gb10", status="ok", total_samples=1, ok_samples=1,
            error_samples=0,
            metric_stats=(("latency_ns", ms),),
            anomalies=(), source_run_ids=("run1",),
        )
        summary = AnalysisSummary(
            analysis_id="20260617T120000Z-a1b2c3d4", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(ca,), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        self._round_trip(summary, AnalysisSummary)

    def test_figure_manifest_round_trip(self):
        fm = FigureManifest(
            figure_id="latency_comparison", path="latency_comparison.png",
            caption="Test", source_analysis_id="analysis1",
            regeneration_command="probe report --analysis test",
        )
        self._round_trip(fm, FigureManifest)

    def test_report_manifest_round_trip(self):
        fm = FigureManifest(
            figure_id="f1", path="f1.png", caption="Fig",
            source_analysis_id="a1", regeneration_command="cmd",
        )
        rm = ReportManifest(
            report_id="r1", report_path="report.md",
            source_analysis_id="a1", figure_manifests=(fm,),
            claim_count=5, section_count=3,
            generated_at="2026-06-17T12:00:00Z",
            regeneration_command="cmd",
        )
        self._round_trip(rm, ReportManifest)

    def test_imported_record_round_trip(self):
        ir = ImportedRecord(
            source_path="/tmp/test.log", parser_version="1.0",
            format="chase_pmu_text", case_id="test@gb10",
            platform_id="gb10",
            metrics=(("latency_ns", 4.36),),
            loss_notes=(),
        )
        self._round_trip(ir, ImportedRecord)

    def test_cross_run_comparison_round_trip(self):
        delta = CrossRunMetricDelta(
            metric_name="latency_ns", unit="ns",
            baseline_value=4.0, current_value=4.5, delta_pct=12.5,
        )
        crc = CrossRunComparison(
            case_id="test@gb10",
            runs_compared=("run1", "run2"),
            classification="improved",
            metric_deltas=(("latency_ns", delta),),
            note=None,
        )
        self._round_trip(crc, CrossRunComparison)


if __name__ == "__main__":
    unittest.main()
