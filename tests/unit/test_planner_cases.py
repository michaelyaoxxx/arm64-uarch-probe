import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog


ROOT = Path(__file__).resolve().parents[2]


class PlannerCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = Planner(Catalog.load(ROOT))

    def test_semantic_single_cpu_resolution(self):
        plan = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=("cache-latency.l1-latency",),
                cluster="c0",
                core_group="x925",
            )
        )

        case = plan.cases[0]
        self.assertEqual(case.cpu, 5)
        self.assertEqual(dict(case.selectors)["cpu"].source, "platform-selector:x925")
        self.assertEqual(
            case.id,
            "cache-latency.l1-latency@gb10.x925.c0.32kib.default",
        )

    def test_explicit_single_cpu_override_wins_and_is_recorded(self):
        plan = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=("cache-latency.l1-latency",),
                cluster="c0",
                core_group="x925",
                cpu=7,
            )
        )

        case = plan.cases[0]
        self.assertEqual(case.cpu, 7)
        self.assertEqual(dict(case.selectors)["cpu"].source, "cli")
        self.assertIn("@gb10.cpu-7.", case.id)

    def test_migration_pair_resolution(self):
        plan = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=(
                    "migration-latency.same-core",
                    "migration-latency.same-cluster",
                    "migration-latency.cross-cluster",
                ),
                cluster="c0",
                core_group="x925",
            )
        )

        pairs = {
            case.scenario_id: (case.src_cpu, case.dst_cpu) for case in plan.cases
        }
        self.assertEqual(pairs["migration-latency.same-core"], (5, 5))
        self.assertEqual(pairs["migration-latency.same-cluster"], (5, 6))
        self.assertEqual(pairs["migration-latency.cross-cluster"], (5, 15))

    def test_explicit_pair_override_wins_and_is_recorded(self):
        plan = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=("migration-latency.cross-cluster",),
                src_cpu=6,
                dst_cpu=16,
            )
        )

        case = plan.cases[0]
        self.assertEqual((case.src_cpu, case.dst_cpu), (6, 16))
        self.assertEqual(dict(case.selectors)["src-cpu"].source, "cli")
        self.assertEqual(dict(case.selectors)["dst-cpu"].source, "cli")

    def test_partial_pair_override_preserves_other_selector_source(self):
        plan = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=("migration-latency.cross-cluster",),
                cluster="c0",
                core_group="x925",
                src_cpu=6,
            )
        )

        selectors = dict(plan.cases[0].selectors)
        self.assertEqual(selectors["src-cpu"].source, "cli")
        self.assertEqual(selectors["dst-cpu"].source, "platform-selector:x925")

    def test_rejects_selectors_irrelevant_to_selected_scenarios(self):
        cases = (
            PlanRequest(
                platform_id="gb10",
                selections=("cache-latency.l1-latency",),
                src_cpu=0,
            ),
            PlanRequest(
                platform_id="gb10",
                selections=("migration-latency.same-core",),
                cpu=0,
            ),
        )
        for request in cases:
            with self.subTest(request=request):
                with self.assertRaises(ProbeError) as error:
                    self.planner.plan(request)
                self.assertEqual(error.exception.code, ExitCode.PLANNING)


if __name__ == "__main__":
    unittest.main()
