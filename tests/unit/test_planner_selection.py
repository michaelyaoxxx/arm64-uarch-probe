import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog


ROOT = Path(__file__).resolve().parents[2]


class PlannerSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = Planner(Catalog.load(ROOT))

    def scenario_ids(self, request: PlanRequest) -> tuple[str, ...]:
        return tuple(item.scenario.id for item in self.planner.resolve(request))

    def test_expands_experiment_in_catalog_order(self):
        self.assertEqual(
            self.scenario_ids(
                PlanRequest(platform_id="gb10", selections=("cache-latency",))
            ),
            (
                "cache-latency.l1-latency",
                "cache-latency.l2-latency",
                "cache-latency.l3-latency",
                "cache-latency.slc-latency",
                "cache-latency.dram-latency",
            ),
        )

    def test_profile_and_explicit_selections_form_deduplicated_union(self):
        request = PlanRequest(
            platform_id="gb10",
            profile_id="smoke",
            selections=(
                "migration-latency.cross-cluster",
                "cache-latency.l2-latency",
            ),
        )

        self.assertEqual(
            self.scenario_ids(request),
            (
                "cache-latency.l1-latency",
                "cache-latency.l2-latency",
                "migration-latency.cross-cluster",
            ),
        )

    def test_requires_a_profile_or_selection(self):
        with self.assertRaises(ProbeError) as error:
            self.planner.resolve(PlanRequest(platform_id="gb10"))

        self.assertEqual(error.exception.code, ExitCode.PLANNING)

    def test_unknown_selection_is_planning_error_with_hint(self):
        with self.assertRaises(ProbeError) as error:
            self.planner.resolve(
                PlanRequest(platform_id="gb10", selections=("unknown",))
            )

        self.assertEqual(error.exception.code, ExitCode.PLANNING)
        self.assertIsNotNone(error.exception.hint)


if __name__ == "__main__":
    unittest.main()
