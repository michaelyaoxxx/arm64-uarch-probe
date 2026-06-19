"""Deterministic statistics engine tests."""
import unittest

from arm64_probe.domain.models import Sample
from arm64_probe.analysis.models import MetricStats, CaseAnalysis
from arm64_probe.analysis.statistics import StatisticsEngine


def _sample(case_id, run_id, status, metrics, sample_index=0):
    """Helper to create a Sample with minimal boilerplate."""
    return Sample(
        run_id=run_id, case_id=case_id, sample_index=sample_index,
        status=status, metrics=tuple(sorted(metrics.items())),
    )


class ComputeMetricStatsTests(unittest.TestCase):
    def test_basic_stats(self):
        samples = (
            _sample("c1", "r1", "ok", {"latency_ns": 4.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 5.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 4.5}),
        )
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns", "ns")
        self.assertEqual(stats.metric_name, "latency_ns")
        self.assertEqual(stats.unit, "ns")
        self.assertEqual(stats.sample_count, 3)
        self.assertEqual(stats.success_count, 3)
        self.assertEqual(stats.error_count, 0)
        self.assertAlmostEqual(stats.min_value, 4.0)
        self.assertAlmostEqual(stats.max_value, 5.0)
        self.assertAlmostEqual(stats.median, 4.5)

    def test_error_samples_excluded(self):
        samples = (
            _sample("c1", "r1", "error", {"latency_ns": 999.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 4.0}),
        )
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns", "ns")
        self.assertEqual(stats.success_count, 1)
        self.assertEqual(stats.error_count, 1)
        self.assertAlmostEqual(stats.median, 4.0)

    def test_all_errors_returns_none_values(self):
        samples = (
            _sample("c1", "r1", "error", {}),
            _sample("c1", "r1", "error", {}),
        )
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns", "ns")
        self.assertIsNone(stats.median)
        self.assertIsNone(stats.min_value)
        self.assertIsNone(stats.max_value)
        self.assertEqual(stats.error_count, 2)

    def test_single_sample_basic(self):
        samples = (_sample("c1", "r1", "ok", {"latency_ns": 4.36}),)
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns")
        self.assertEqual(stats.sample_count, 1)
        self.assertAlmostEqual(stats.median, 4.36)
        self.assertEqual(stats.stddev, 0.0)

    def test_unit_inference(self):
        samples = (_sample("c1", "r1", "ok", {"latency_ns": 1.0}),)
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns")
        self.assertEqual(stats.unit, "ns")

        samples2 = (_sample("c1", "r1", "ok", {"accesses": 100}),)
        stats2 = StatisticsEngine.compute_metric_stats(samples2, "accesses")
        self.assertEqual(stats2.unit, "count")

        samples3 = (_sample("c1", "r1", "ok", {"elapsed_cycles": 1000}),)
        stats3 = StatisticsEngine.compute_metric_stats(samples3, "elapsed_cycles")
        self.assertEqual(stats3.unit, "cycles")

        samples4 = (_sample("c1", "r1", "ok", {"read_bytes": 4096}),)
        stats4 = StatisticsEngine.compute_metric_stats(samples4, "read_bytes")
        self.assertEqual(stats4.unit, "bytes")

    def test_mad_computation(self):
        samples = (
            _sample("c1", "r1", "ok", {"latency_ns": 1.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 2.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 3.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 4.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 100.0}),
        )
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns")
        # median=3.0, abs deviations = [2,1,0,1,97] -> sorted=[0,1,1,2,97] -> median of deviations = 1.0
        self.assertAlmostEqual(stats.mad, 1.0)
        self.assertAlmostEqual(stats.median, 3.0)

    def test_empty_samples(self):
        stats = StatisticsEngine.compute_metric_stats((), "latency_ns", "ns")
        self.assertEqual(stats.sample_count, 0)
        self.assertEqual(stats.success_count, 0)
        self.assertEqual(stats.error_count, 0)
        self.assertIsNone(stats.median)
        self.assertIsNone(stats.min_value)
        self.assertIsNone(stats.max_value)
        self.assertIsNone(stats.mad)
        self.assertIsNone(stats.mean)
        self.assertIsNone(stats.stddev)


class ComputeCaseAnalysisTests(unittest.TestCase):
    def test_compute_case_analysis_ok(self):
        samples = (
            _sample("c1", "r1", "ok", {"latency_ns": 4.0, "accesses": 100}),
            _sample("c1", "r1", "ok", {"latency_ns": 5.0, "accesses": 120}),
        )
        ca = StatisticsEngine.compute_case_analysis(
            case_id="c1", samples=samples,
            scenario_id="cache-latency.l1-latency", platform_id="gb10",
        )
        self.assertEqual(ca.case_id, "c1")
        self.assertEqual(ca.status, "ok")
        self.assertEqual(ca.total_samples, 2)
        self.assertEqual(ca.ok_samples, 2)
        self.assertEqual(ca.error_samples, 0)
        self.assertEqual(len(ca.metric_stats), 2)
        # Metric names sorted alphabetically
        self.assertEqual(ca.metric_stats[0][0], "accesses")
        self.assertEqual(ca.metric_stats[1][0], "latency_ns")

    def test_compute_case_analysis_partial(self):
        samples = (
            _sample("c1", "r1", "ok", {"latency_ns": 4.0}),
            _sample("c1", "r1", "error", {}),
        )
        ca = StatisticsEngine.compute_case_analysis(
            case_id="c1", samples=samples,
            scenario_id="test", platform_id="gb10",
        )
        self.assertEqual(ca.status, "partial")
        self.assertEqual(ca.ok_samples, 1)
        self.assertEqual(ca.error_samples, 1)

    def test_compute_case_analysis_failed(self):
        samples = (
            _sample("c1", "r1", "error", {}),
            _sample("c1", "r1", "error", {}),
        )
        ca = StatisticsEngine.compute_case_analysis(
            case_id="c1", samples=samples,
            scenario_id="test", platform_id="gb10",
        )
        self.assertEqual(ca.status, "failed")

    def test_source_run_ids_collected(self):
        samples = (
            _sample("c1", "run1", "ok", {"latency_ns": 4.0}),
            _sample("c1", "run2", "ok", {"latency_ns": 5.0}),
        )
        ca = StatisticsEngine.compute_case_analysis(
            case_id="c1", samples=samples,
            scenario_id="test", platform_id="gb10",
        )
        self.assertEqual(ca.source_run_ids, ("run1", "run2"))

    def test_case_analysis_propagates_anomalies(self):
        """Anomalies from individual metrics should appear in CaseAnalysis.anomalies."""
        samples = (_sample("c1", "r1", "ok", {"latency_ns": 4.0}),)
        ca = StatisticsEngine.compute_case_analysis(
            case_id="c1", samples=samples,
            scenario_id="test", platform_id="gb10",
        )
        self.assertIn("single_sample", ca.anomalies)

    def test_case_analysis_deduplicates_anomalies(self):
        """Same anomaly type across multiple metrics should be deduplicated."""
        samples = (_sample("c1", "r1", "ok", {"latency_ns": 4.0, "accesses": 100}),)
        ca = StatisticsEngine.compute_case_analysis(
            case_id="c1", samples=samples,
            scenario_id="test", platform_id="gb10",
        )
        self.assertEqual(ca.anomalies.count("single_sample"), 1)


class AnomalyDetectionTests(unittest.TestCase):
    def test_single_sample(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=1,
            success_count=1, error_count=0,
            min_value=4.0, max_value=4.0, median=4.0,
            mad=0.0, mean=4.0, stddev=0.0,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertEqual(anomalies, ("single_sample",))

    def test_all_errors(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=5,
            success_count=0, error_count=5,
            min_value=None, max_value=None, median=None,
            mad=None, mean=None, stddev=None,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertEqual(anomalies, ("all_errors",))

    def test_zero_variance(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=5,
            success_count=5, error_count=0,
            min_value=4.0, max_value=4.0, median=4.0,
            mad=0.0, mean=4.0, stddev=0.0,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertEqual(anomalies, ("zero_variance",))

    def test_high_variance(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=10,
            success_count=10, error_count=0,
            min_value=1.0, max_value=1000.0, median=10.0,
            mad=5.0, mean=100.0, stddev=500.0,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertEqual(anomalies, ("high_variance",))

    def test_extreme_outlier(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=100,
            success_count=100, error_count=0,
            min_value=4.0, max_value=9999.0, median=4.5,
            mad=0.2, mean=5.0, stddev=1.0,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertEqual(anomalies, ("extreme_outlier",))

    def test_no_anomalies(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=10,
            success_count=10, error_count=0,
            min_value=4.0, max_value=5.0, median=4.36,
            mad=0.12, mean=4.40, stddev=0.35,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertEqual(anomalies, ())


if __name__ == "__main__":
    unittest.main()
