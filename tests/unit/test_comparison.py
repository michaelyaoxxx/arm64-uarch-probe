"""Phase 4 ComparisonEngine stub tests."""
import unittest

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, CrossRunComparison,
)
from arm64_probe.analysis.comparison import ComparisonEngine


class ComparisonEngineStubTests(unittest.TestCase):
    def setUp(self):
        self.stats = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=5, error_count=0,
            min_value=4.0, max_value=5.0, median=4.36,
            mad=0.12, mean=4.40, stddev=0.35,
        )
        self.ca = CaseAnalysis(
            case_id="test@gb10", scenario_id="test", platform_id="gb10",
            status="ok", total_samples=5, ok_samples=5, error_samples=0,
            metric_stats=(("latency_ns", self.stats),),
            anomalies=(), source_run_ids=("run1",),
        )

    def test_stub_returns_incompatible_with_note(self):
        result = ComparisonEngine.compare_runs(self.ca, self.ca)
        self.assertEqual(result.classification, "incompatible")
        self.assertIn("Phase 5", result.note)
        self.assertEqual(result.case_id, "test@gb10")

    def test_stub_is_deterministic(self):
        r1 = ComparisonEngine.compare_runs(self.ca, self.ca)
        r2 = ComparisonEngine.compare_runs(self.ca, self.ca)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
