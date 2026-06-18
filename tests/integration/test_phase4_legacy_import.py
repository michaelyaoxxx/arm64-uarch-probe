"""Legacy import end-to-end test."""
import unittest
from pathlib import Path

from arm64_probe.analysis.adapters.legacy_chase_pmu import (
    LegacyChasePmuImporter,
)


class LegacyImportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.importer = LegacyChasePmuImporter()

    def test_parses_real_legacy_output(self):
        legacy_path = (
            Path(__file__).resolve().parents[2]
            / "data" / "20260611_v2.7.3" / "raw" / "run_20260611_123112.txt"
        )
        if not legacy_path.exists():
            self.skipTest("legacy data not available")
        self.assertTrue(self.importer.can_handle(legacy_path))
        record = self.importer.import_log(legacy_path)
        self.assertIsNotNone(record)
        self.assertGreater(len(record.metrics), 0)
        self.assertIn("latency_ns", dict(record.metrics))
