"""
Characterization tests for probe adapters.

These tests verify that each adapter correctly parses its expected output format
using the captured fixtures in tests/fixtures/probe_output/.
"""
import unittest
from pathlib import Path

from arm64_probe.execution.adapters import (
    ChasePmuAdapter,
    EvictSlcAdapter,
    ChaseMigrateAdapter,
)
from arm64_probe.execution.adapters.base import ProbeOutput, ProbeError


class ChasePmuCharacterizationTests(unittest.TestCase):
    """Characterization tests for chase_pmu adapter."""

    def setUp(self):
        self.adapter = ChasePmuAdapter()
        self.fixtures_dir = (
            Path(__file__).parent.parent.parent
            / "tests"
            / "fixtures"
            / "probe_output"
            / "chase_pmu"
            / "chase_pmu_v2_7_3"
        )

    def test_parse_l2_hit_warm(self):
        """Parse L2 hit latency with warm cache."""
        fixture_path = self.fixtures_dir / "l2_hit_warm.stdout"
        if not fixture_path.exists():
            self.skipTest(f"Fixture not found: {fixture_path}")

        output = fixture_path.read_text()
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 4.36, places=2)
        self.assertEqual(result.accesses, 819200)
        self.assertEqual(result.elapsed_ns, 3568832)
        self.assertEqual(result.sink_address, "0x437530c3e000")

    def test_parse_l3_hit_warm(self):
        """Parse L3 hit latency with warm cache."""
        fixture_path = self.fixtures_dir / "l3_hit_warm.stdout"
        if not fixture_path.exists():
            self.skipTest(f"Fixture not found: {fixture_path}")

        output = fixture_path.read_text()
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 6.02, places=2)
        self.assertEqual(result.accesses, 3276800)
        self.assertEqual(result.elapsed_ns, 19738432)

    def test_parse_dram_cold(self):
        """Parse DRAM latency with cold cache."""
        fixture_path = self.fixtures_dir / "dram_cold.stdout"
        if not fixture_path.exists():
            self.skipTest(f"Fixture not found: {fixture_path}")

        output = fixture_path.read_text()
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 12.00, places=2)
        self.assertEqual(result.accesses, 13107200)
        self.assertEqual(result.elapsed_ns, 157286400)

    def test_parse_failure_no_latency(self):
        """Return ProbeError when latency marker is missing."""
        bad_output = "=== chase_pmu v2.7.3 ===\nsize=1024 KB\n"
        result = self.adapter.parse_output(bad_output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertEqual(result.error_type, "parse_failure")
        self.assertIn("latency", result.message)

    def test_parse_failure_no_perf_metrics(self):
        """Return ProbeError when elapsed/accesses is missing."""
        bad_output = ">>> latency = 4.36 ns/access  (sink=0x437530c3e000)\n"
        result = self.adapter.parse_output(bad_output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertEqual(result.error_type, "parse_failure")
        self.assertIn("elapsed", result.message)

    def test_characterize_output(self):
        """characterize_output returns dict of fixture scenarios."""
        fixtures = self.adapter.characterize_output()

        self.assertIsInstance(fixtures, dict)
        if self.fixtures_dir.exists():
            # Should have at least one fixture
            self.assertGreater(len(fixtures), 0)


class EvictSlcCharacterizationTests(unittest.TestCase):
    """Characterization tests for evict_slc adapter."""

    def setUp(self):
        self.adapter = EvictSlcAdapter()
        self.fixtures_dir = (
            Path(__file__).parent.parent.parent
            / "tests"
            / "fixtures"
            / "probe_output"
            / "evict_slc"
            / "evict_slc_v1_2"
        )

    def test_parse_evict_32mb(self):
        """Parse 32MB SLC eviction."""
        fixture_path = self.fixtures_dir / "evict_32mb.stdout"
        if not fixture_path.exists():
            self.skipTest(f"Fixture not found: {fixture_path}")

        output = fixture_path.read_text()
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 0.031, places=3)
        self.assertEqual(result.accesses, 134217728)
        self.assertEqual(result.elapsed_ns, 4194304)

    def test_parse_failure_no_latency(self):
        """Return ProbeError when latency marker is missing."""
        bad_output = "=== evict_slc v1.2 ===\n"
        result = self.adapter.parse_output(bad_output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertEqual(result.error_type, "parse_failure")

    def test_characterize_output(self):
        """characterize_output returns dict of fixture scenarios."""
        fixtures = self.adapter.characterize_output()

        self.assertIsInstance(fixtures, dict)
        if self.fixtures_dir.exists():
            self.assertGreater(len(fixtures), 0)


class ChaseMigrateCharacterizationTests(unittest.TestCase):
    """Characterization tests for chase_migrate adapter."""

    def setUp(self):
        self.adapter = ChaseMigrateAdapter()
        self.fixtures_dir = (
            Path(__file__).parent.parent.parent
            / "tests"
            / "fixtures"
            / "probe_output"
            / "chase_migrate"
            / "chase_migrate_v1_0"
        )

    def test_parse_same_cluster(self):
        """Parse same-cluster migration penalty."""
        fixture_path = self.fixtures_dir / "same_cluster.stdout"
        if not fixture_path.exists():
            self.skipTest(f"Fixture not found: {fixture_path}")

        output = fixture_path.read_text()
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        # Migration penalty should be in additional_metrics
        self.assertIn("migration_penalty_ns", result.additional_metrics)
        self.assertAlmostEqual(
            result.additional_metrics["migration_penalty_ns"],
            0.68,
            places=2,
        )
        self.assertAlmostEqual(
            result.additional_metrics["before_latency_ns"],
            4.36,
            places=2,
        )
        self.assertAlmostEqual(
            result.additional_metrics["after_latency_ns"],
            5.04,
            places=2,
        )

    def test_parse_cross_cluster(self):
        """Parse cross-cluster migration penalty."""
        fixture_path = self.fixtures_dir / "cross_cluster.stdout"
        if not fixture_path.exists():
            self.skipTest(f"Fixture not found: {fixture_path}")

        output = fixture_path.read_text()
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertIn("migration_penalty_ns", result.additional_metrics)
        self.assertAlmostEqual(
            result.additional_metrics["migration_penalty_ns"],
            11.00,
            places=2,
        )

    def test_parse_failure_no_penalty(self):
        """Return ProbeError when migration_penalty is missing."""
        bad_output = "=== chase_migrate v1.0 ===\n"
        result = self.adapter.parse_output(bad_output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertEqual(result.error_type, "parse_failure")
        self.assertIn("migration_penalty", result.message)

    def test_parse_failure_no_before_after(self):
        """Return ProbeError when before/after latency is missing."""
        bad_output = ">>> migration_penalty = 1.00 ns\n"
        result = self.adapter.parse_output(bad_output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertEqual(result.error_type, "parse_failure")
        self.assertIn("before/after", result.message)

    def test_characterize_output(self):
        """characterize_output returns dict of fixture scenarios."""
        fixtures = self.adapter.characterize_output()

        self.assertIsInstance(fixtures, dict)
        if self.fixtures_dir.exists():
            self.assertGreater(len(fixtures), 0)


if __name__ == "__main__":
    unittest.main()
