"""
Adapter output parsing tests.

Test that each adapter correctly parses its expected output format.
"""
import unittest

from arm64_probe.execution.adapters import (
    ChasePmuAdapter,
    ChaseMigrateAdapter,
    EvictSlcAdapter,
)
from arm64_probe.execution.adapters.base import ProbeOutput, ProbeError


class ChasePmuAdapterTests(unittest.TestCase):
    """Test ChasePmuAdapter output parsing."""

    def setUp(self):
        self.adapter = ChasePmuAdapter()

    def test_parse_success_output(self):
        """Parse successful chase_pmu output."""
        output = """=== chase_pmu v2.7.3 ===
size=1024 KB  n_lines=16384  warm=5  meas_rounds=50  seed=42  hugepage=0
Warming 5 pass(es)...
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
"""
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 4.36, places=2)
        self.assertEqual(result.accesses, 819200)
        self.assertEqual(result.elapsed_ns, 3568832)
        self.assertEqual(result.sink_address, "0x437530c3e000")

    def test_parse_error_output(self):
        """Parse chase_pmu error output."""
        output = """=== chase_pmu v2.7.3 ===
Error: Invalid working set size
"""
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertIsNone(result.exit_code)

    def test_parse_empty_output(self):
        """Parse empty chase_pmu output."""
        result = self.adapter.parse_output("", "")

        self.assertIsInstance(result, ProbeError)

    def test_build_argv_basic(self):
        """Build basic chase_pmu arguments."""
        argv = self.adapter.build_argv(
            cpu=0,
            working_set_kb=1024,
            warm_passes=5,
            measure_passes=50,
            seed=42,
        )

        self.assertIn("1024", argv)
        self.assertIn("5", argv)
        self.assertIn("50", argv)
        self.assertIn("42", argv)

    def test_characterize_output(self):
        """Characterize chase_pmu output."""
        fixtures = self.adapter.characterize_output()

        self.assertIsInstance(fixtures, dict)
        self.assertIn("l2_hit_warm", fixtures)
        self.assertIn("l3_hit_warm", fixtures)
        self.assertIn("dram_cold", fixtures)


class EvictSlcAdapterTests(unittest.TestCase):
    """Test EvictSlcAdapter output parsing."""

    def setUp(self):
        self.adapter = EvictSlcAdapter()

    def test_parse_success_output(self):
        """Parse successful evict_slc output."""
        output = """=== evict_slc v1.2 ===
evict_mb=32  n_lines=524288  seed=42
elapsed=4194304 ns  accesses=134217728
>>> latency = 0.031 ns/access  (sink=0x7f5678000000)
"""
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 0.031, places=3)
        self.assertEqual(result.accesses, 134217728)
        self.assertEqual(result.elapsed_ns, 4194304)
        self.assertEqual(result.sink_address, "0x7f5678000000")

    def test_parse_error_output(self):
        """Parse evict_slc error output."""
        output = """=== evict_slc v1.2 ===
Error: Failed to allocate memory
"""
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertIsNone(result.exit_code)

    def test_parse_empty_output(self):
        """Parse empty evict_slc output."""
        result = self.adapter.parse_output("", "")

        self.assertIsInstance(result, ProbeError)

    def test_build_argv_basic(self):
        """Build basic evict_slc arguments."""
        argv = self.adapter.build_argv(
            cpu=0,
            working_set_kb=32 * 1024,  # 32MB
            seed=42,
        )

        self.assertIn("32", argv)
        self.assertIn("42", argv)

    def test_characterize_output(self):
        """Characterize evict_slc output."""
        fixtures = self.adapter.characterize_output()

        self.assertIsInstance(fixtures, dict)
        self.assertIn("evict_32mb", fixtures)


class ChaseMigrateAdapterTests(unittest.TestCase):
    """Test ChaseMigrateAdapter output parsing."""

    def setUp(self):
        self.adapter = ChaseMigrateAdapter()

    def test_parse_same_cluster_output(self):
        """Parse same-cluster migration output."""
        output = """=== chase_migrate v1.0 ===
src_cpu=0  dst_cpu=5  size=1024 KB  n_lines=16384  warm_passes=5  measure_passes=50
Migration from cpu0 to cpu5
Before migration: elapsed=3568832 ns  accesses=819200  latency=4.36 ns/access
After migration: elapsed=4128768 ns  accesses=819200  latency=5.04 ns/access
>>> migration_penalty = 0.68 ns
"""
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 0.68, places=2)
        self.assertIn("before_latency_ns", result.additional_metrics)
        self.assertIn("after_latency_ns", result.additional_metrics)
        self.assertIn("migration_penalty_ns", result.additional_metrics)

    def test_parse_cross_cluster_output(self):
        """Parse cross-cluster migration output."""
        output = """=== chase_migrate v1.0 ===
src_cpu=0  dst_cpu=10  size=1024 KB  n_lines=16384  warm_passes=5  measure_passes=50
Migration from cpu0 to cpu10
Before migration: elapsed=3568832 ns  accesses=819200  latency=4.36 ns/access
After migration: elapsed=12582912 ns  accesses=819200  latency=15.36 ns/access
>>> migration_penalty = 11.00 ns
"""
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeOutput)
        self.assertAlmostEqual(result.latency_ns, 11.00, places=2)

    def test_parse_error_output(self):
        """Parse chase_migrate error output."""
        output = """=== chase_migrate v1.0 ===
Error: CPU affinity failed
"""
        result = self.adapter.parse_output(output, "")

        self.assertIsInstance(result, ProbeError)
        self.assertIsNone(result.exit_code)

    def test_parse_empty_output(self):
        """Parse empty chase_migrate output."""
        result = self.adapter.parse_output("", "")

        self.assertIsInstance(result, ProbeError)

    def test_build_argv_basic(self):
        """Build basic chase_migrate arguments."""
        argv = self.adapter.build_argv(
            cpu=0,
            working_set_kb=1024,
            src_cpu=0,
            dst_cpu=5,
        )

        self.assertIn("1024", argv)
        self.assertIn("0", argv)
        self.assertIn("5", argv)

    def test_characterize_output(self):
        """Characterize chase_migrate output."""
        fixtures = self.adapter.characterize_output()

        self.assertIsInstance(fixtures, dict)
        self.assertIn("same_cluster", fixtures)
        self.assertIn("cross_cluster", fixtures)


if __name__ == '__main__':
    unittest.main()
