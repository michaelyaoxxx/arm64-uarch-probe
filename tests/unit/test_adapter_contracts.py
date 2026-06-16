"""
Adapter contract tests.

Verify that all adapters conform to the ProbeAdapter protocol contract.
"""
import unittest

from arm64_probe.execution.adapters import (
    ChasePmuAdapter,
    ChaseMigrateAdapter,
    EvictSlcAdapter,
)
from arm64_probe.execution.adapters.base import ProbeAdapter


class AdapterContractTests(unittest.TestCase):
    """Test that all adapters conform to the contract."""

    def test_chase_pmu_conforms_to_protocol(self):
        """ChasePmuAdapter must implement ProbeAdapter protocol."""
        adapter = ChasePmuAdapter()
        self.assertIsInstance(adapter, ProbeAdapter)

    def test_chase_migrate_conforms_to_protocol(self):
        """ChaseMigrateAdapter must implement ProbeAdapter protocol."""
        adapter = ChaseMigrateAdapter()
        self.assertIsInstance(adapter, ProbeAdapter)

    def test_evict_slc_conforms_to_protocol(self):
        """EvictSlcAdapter must implement ProbeAdapter protocol."""
        adapter = EvictSlcAdapter()
        self.assertIsInstance(adapter, ProbeAdapter)

    def test_adapters_have_required_attributes(self):
        """All adapters must have probe_name and version attributes."""
        adapters = [
            ChasePmuAdapter(),
            ChaseMigrateAdapter(),
            EvictSlcAdapter(),
        ]

        for adapter in adapters:
            with self.subTest(adapter=adapter.__class__.__name__):
                # Check required attributes exist
                self.assertTrue(hasattr(adapter, 'probe_name'))
                self.assertTrue(hasattr(adapter, 'version'))

                # Check they are strings
                self.assertIsInstance(adapter.probe_name, str)
                self.assertIsInstance(adapter.version, str)

                # Check they are non-empty
                self.assertTrue(len(adapter.probe_name) > 0)
                self.assertTrue(len(adapter.version) > 0)

    def test_adapters_have_required_methods(self):
        """All adapters must have build_argv and parse_output methods."""
        adapters = [
            ChasePmuAdapter(),
            ChaseMigrateAdapter(),
            EvictSlcAdapter(),
        ]

        for adapter in adapters:
            with self.subTest(adapter=adapter.__class__.__name__):
                # Check required methods exist
                self.assertTrue(hasattr(adapter, 'build_argv'))
                self.assertTrue(hasattr(adapter, 'parse_output'))
                self.assertTrue(hasattr(adapter, 'characterize_output'))

                # Check they are callable
                self.assertTrue(callable(adapter.build_argv))
                self.assertTrue(callable(adapter.parse_output))
                self.assertTrue(callable(adapter.characterize_output))

    def test_characterize_output_returns_dict(self):
        """characterize_output must return a dict of scenario -> fixture."""
        adapters = [
            ChasePmuAdapter(),
            ChaseMigrateAdapter(),
            EvictSlcAdapter(),
        ]

        for adapter in adapters:
            with self.subTest(adapter=adapter.__class__.__name__):
                result = adapter.characterize_output()
                self.assertIsInstance(result, dict)


if __name__ == '__main__':
    unittest.main()
