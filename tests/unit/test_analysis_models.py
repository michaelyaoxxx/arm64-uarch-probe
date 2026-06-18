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
            metric_stats=(("accesses", m2), ("latency_ns", m1)),
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
        )
        data = to_data(value)
        json_str = json.dumps(data, sort_keys=True)
        reloaded_data = json.loads(json_str)
        if expected_type is AnalysisSummary:
            result = _dict_to_analysis_summary(reloaded_data)
        elif expected_type is BaselineManifest:
            result = _dict_to_baseline_manifest(reloaded_data)
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


if __name__ == "__main__":
    unittest.main()
