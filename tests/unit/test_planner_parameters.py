import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog


ROOT = Path(__file__).resolve().parents[2]


class PlannerParameterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = Planner(Catalog.load(ROOT))

    def resolved_parameters(
        self,
        request: PlanRequest,
        scenario_id: str | None = None,
    ) -> dict[str, object]:
        resolved = self.planner.resolve(request)
        if scenario_id is None:
            self.assertEqual(len(resolved), 1)
            return dict(resolved[0].parameters)
        return dict(
            next(item for item in resolved if item.scenario.id == scenario_id).parameters
        )

    def test_parameter_precedence_and_sources(self):
        parameters = self.resolved_parameters(
            PlanRequest(
                platform_id="gb10",
                profile_id="smoke",
                selections=("cache-latency.l1-latency",),
                overrides=(("samples", 3),),
            ),
            "cache-latency.l1-latency",
        )

        self.assertEqual(parameters["samples"].value, 3)
        self.assertEqual(parameters["samples"].source, "cli")
        self.assertEqual(parameters["page-policy"].value, "default")
        self.assertEqual(parameters["page-policy"].source, "profile")
        self.assertEqual(parameters["working-set"].value, "32KiB")
        self.assertEqual(parameters["working-set"].source, "platform-default")

    def test_scoped_platform_default_is_used(self):
        parameters = self.resolved_parameters(
            PlanRequest(
                platform_id="gb10",
                selections=("cache-latency.dram-latency",),
            )
        )

        self.assertEqual(parameters["working-set"].value, "64MiB")
        self.assertEqual(parameters["working-set"].source, "platform-default")

    def test_rejects_invalid_parameter_values(self):
        cases = (
            ("samples", 0),
            ("page-policy", "unknown"),
            ("working-set", "64MB"),
            ("unknown", 1),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value):
                request = PlanRequest(
                    platform_id="gb10",
                    selections=("cache-latency.l1-latency",),
                    overrides=((key, value),),
                )
                with self.assertRaises(ProbeError) as error:
                    self.planner.resolve(request)
                self.assertEqual(error.exception.code, ExitCode.PLANNING)


if __name__ == "__main__":
    unittest.main()
