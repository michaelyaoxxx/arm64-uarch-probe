import unittest
from pathlib import Path

from arm64_probe.registry.catalog import Catalog


ROOT = Path(__file__).resolve().parents[2]


class ScenarioCatalogContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT)

    def test_cache_scenarios_use_single_cpu_mode(self):
        scenarios = self.catalog.expand_selection("cache-latency")

        self.assertEqual(len(scenarios), 5)
        self.assertEqual({item.cpu_mode for item in scenarios}, {"single"})

    def test_migration_scenarios_expose_three_pair_modes(self):
        scenarios = self.catalog.expand_selection("migration-latency")

        self.assertEqual(
            tuple(item.cpu_mode for item in scenarios),
            ("pair-same-core", "pair-same-cluster", "pair-cross-cluster"),
        )

    def test_every_scenario_has_common_parameters_and_capability(self):
        for scenario in self.catalog.scenarios():
            with self.subTest(scenario=scenario.id):
                self.assertEqual(
                    tuple(item.id for item in scenario.parameters),
                    ("samples", "working-set", "page-policy"),
                )
                self.assertIn("cpu-binding", scenario.required_capabilities)

    def test_profiles_reference_catalog_targets(self):
        target_ids = {
            *(item.id for item in self.catalog.experiments()),
            *(item.id for item in self.catalog.scenarios()),
        }
        for profile in self.catalog.profiles():
            with self.subTest(profile=profile.id):
                self.assertTrue(set(profile.selections).issubset(target_ids))


if __name__ == "__main__":
    unittest.main()
