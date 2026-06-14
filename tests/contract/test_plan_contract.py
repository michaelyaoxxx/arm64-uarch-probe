import inspect
import unittest
from pathlib import Path

from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog
from arm64_probe.serialization.json_io import dump_json
from arm64_probe.serialization.model_json import to_data


ROOT = Path(__file__).resolve().parents[2]


class PlanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = Planner(Catalog.load(ROOT))

    def test_capability_gate_marks_m4_unsupported_without_failing_plan(self):
        plan = self.planner.plan(
            PlanRequest(platform_id="m4", profile_id="smoke")
        )

        self.assertTrue(plan.cases)
        self.assertEqual({case.status for case in plan.cases}, {"unsupported"})
        self.assertTrue(all("cpu-binding" in case.reason for case in plan.cases))

    def test_skip_unavailable_changes_plan_decision_not_case_status(self):
        base = self.planner.plan(PlanRequest(platform_id="m4", profile_id="smoke"))
        skipped = self.planner.plan(
            PlanRequest(
                platform_id="m4",
                profile_id="smoke",
                skip_unavailable=True,
            )
        )

        self.assertFalse(base.skip_unavailable)
        self.assertTrue(skipped.skip_unavailable)
        self.assertEqual(
            tuple(case.status for case in base.cases),
            tuple(case.status for case in skipped.cases),
        )

    def test_selection_order_does_not_change_plan_json(self):
        first = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=(
                    "cache-latency.l2-latency",
                    "migration-latency.cross-cluster",
                ),
            )
        )
        second = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=(
                    "migration-latency.cross-cluster",
                    "cache-latency.l2-latency",
                ),
            )
        )

        self.assertEqual(dump_json(to_data(first)), dump_json(to_data(second)))
        self.assertNotIn("timestamp", to_data(first))
        self.assertNotIn("run_id", to_data(first))

    def test_environment_phases_are_explicit_and_side_effect_free(self):
        default = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=("cache-latency.l1-latency",),
            )
        )
        hugepage = self.planner.plan(
            PlanRequest(
                platform_id="gb10",
                selections=("cache-latency.l1-latency",),
                overrides=(("page-policy", "hugepage"),),
            )
        )
        baseline = self.planner.plan(
            PlanRequest(platform_id="gb10", profile_id="baseline")
        )

        self.assertEqual(
            dict(default.environment_phases[0].requirements)["page-policy"],
            "default",
        )
        self.assertEqual(
            dict(hugepage.environment_phases[0].requirements)["page-policy"],
            "hugepage",
        )
        self.assertEqual(
            dict(baseline.environment_phases[0].requirements)["cpu-governor"],
            "performance",
        )
        source = inspect.getsourcefile(Planner)
        self.assertIsNotNone(source)
        planner_text = Path(source).read_text()
        for forbidden in ("/sys/", "/proc/", "subprocess", "taskset"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, planner_text)


if __name__ == "__main__":
    unittest.main()
